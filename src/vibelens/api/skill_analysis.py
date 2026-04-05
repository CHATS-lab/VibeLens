"""Skill analysis endpoints — LLM-powered workflow pattern detection and skill recommendations."""

import asyncio
import secrets

from fastapi import APIRouter, Header, HTTPException

from vibelens.deps import get_skill_analysis_store, is_demo_mode, is_test_mode
from vibelens.models.skill import SkillAnalysisResult
from vibelens.schemas.analysis import AnalysisJobResponse, AnalysisJobStatus
from vibelens.schemas.skills import (
    SkillAnalysisMeta,
    SkillAnalysisRequest,
    SkillDeepCreateRequest,
    SkillProposalRequest,
)
from vibelens.services.job_tracker import (
    cancel_job,
    get_job,
    mark_completed,
    mark_failed,
    submit_job,
)
from vibelens.services.skill import (
    analyze_skill_creation_proposals,
    analyze_skills,
    infer_skill_creation,
)
from vibelens.services.skill.mock import (
    build_mock_deep_creation,
    build_mock_proposal_result,
    build_mock_skill_result,
)
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/skills/analysis", tags=["skill-analysis"])


async def _run_skill_analysis(
    job_id: str, session_ids: list[str], mode: str, token: str | None
) -> None:
    """Background wrapper for skill analysis."""
    try:
        result = await analyze_skills(session_ids, mode, session_token=token)
        mark_completed(job_id, result.analysis_id or "")
    except asyncio.CancelledError:
        logger.info("Skill analysis job %s was cancelled", job_id)
        raise
    except Exception as exc:
        mark_failed(job_id, f"{type(exc).__name__}: {exc}")
        logger.exception("Skill analysis job %s failed", job_id)


async def _run_proposals(job_id: str, session_ids: list[str], token: str | None) -> None:
    """Background wrapper for skill proposal generation."""
    try:
        result = await analyze_skill_creation_proposals(session_ids, session_token=token)
        mark_completed(job_id, result.proposal_id or "")
    except asyncio.CancelledError:
        logger.info("Proposal job %s was cancelled", job_id)
        raise
    except Exception as exc:
        mark_failed(job_id, f"{type(exc).__name__}: {exc}")
        logger.exception("Proposal job %s failed", job_id)


async def _run_deep_create(
    job_id: str,
    proposal_name: str,
    proposal_description: str,
    proposal_rationale: str,
    addressed_patterns: list[str],
    session_ids: list[str],
    token: str | None,
) -> None:
    """Background wrapper for deep skill creation."""
    try:
        result = await infer_skill_creation(
            proposal_name=proposal_name,
            proposal_description=proposal_description,
            proposal_rationale=proposal_rationale,
            addressed_patterns=addressed_patterns,
            session_ids=session_ids,
            session_token=token,
        )
        mark_completed(job_id, result.name)
    except asyncio.CancelledError:
        logger.info("Deep create job %s was cancelled", job_id)
        raise
    except Exception as exc:
        mark_failed(job_id, f"{type(exc).__name__}: {exc}")
        logger.exception("Deep create job %s failed", job_id)


@router.post("")
async def skill_analysis(
    body: SkillAnalysisRequest, x_session_token: str | None = Header(None)
) -> AnalysisJobResponse:
    """Run skill analysis on specified sessions.

    Args:
        body: Request with session IDs and analysis mode.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        AnalysisJobResponse with job_id and status.
    """
    if not body.session_ids:
        raise HTTPException(status_code=400, detail="session_ids must not be empty")

    if is_test_mode() or is_demo_mode():
        result = build_mock_skill_result(body.session_ids, body.mode)
        return AnalysisJobResponse(
            job_id="mock", status="completed", analysis_id=result.analysis_id
        )

    job_id = secrets.token_urlsafe(12)
    try:
        submit_job(
            job_id, _run_skill_analysis(job_id, body.session_ids, body.mode, x_session_token)
        )
    except ValueError as exc:
        status = 503 if "inference backend" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    return AnalysisJobResponse(job_id=job_id, status="running")


@router.post("/proposals")
async def skill_proposals(
    body: SkillProposalRequest, x_session_token: str | None = Header(None)
) -> AnalysisJobResponse:
    """Generate lightweight skill proposals from session analysis.

    Args:
        body: Request with session IDs.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        AnalysisJobResponse with job_id and status.
    """
    if not body.session_ids:
        raise HTTPException(status_code=400, detail="session_ids must not be empty")

    if is_test_mode() or is_demo_mode():
        result = build_mock_proposal_result(body.session_ids)
        return AnalysisJobResponse(
            job_id="mock", status="completed", analysis_id=result.proposal_id
        )

    job_id = secrets.token_urlsafe(12)
    try:
        submit_job(job_id, _run_proposals(job_id, body.session_ids, x_session_token))
    except ValueError as exc:
        status = 503 if "inference backend" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    return AnalysisJobResponse(job_id=job_id, status="running")


@router.post("/create")
async def skill_deep_create(
    body: SkillDeepCreateRequest, x_session_token: str | None = Header(None)
) -> AnalysisJobResponse:
    """Generate full SKILL.md content for one approved proposal.

    Args:
        body: Request with proposal details and session IDs.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        AnalysisJobResponse with job_id and status.
    """
    if not body.session_ids:
        raise HTTPException(status_code=400, detail="session_ids must not be empty")

    if is_test_mode() or is_demo_mode():
        result = build_mock_deep_creation(body.proposal_name)
        return AnalysisJobResponse(job_id="mock", status="completed", analysis_id=result.name)

    job_id = secrets.token_urlsafe(12)
    try:
        submit_job(
            job_id,
            _run_deep_create(
                job_id,
                body.proposal_name,
                body.proposal_description,
                body.proposal_rationale,
                body.addressed_patterns,
                body.session_ids,
                x_session_token,
            ),
        )
    except ValueError as exc:
        status = 503 if "inference backend" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    return AnalysisJobResponse(job_id=job_id, status="running")


@router.get("/jobs/{job_id}")
async def skill_job_status(job_id: str) -> AnalysisJobStatus:
    """Poll the status of a background skill analysis job.

    Args:
        job_id: The job identifier returned by POST endpoints.

    Returns:
        Current job status with analysis_id on completion.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return AnalysisJobStatus(
        job_id=job.job_id,
        status=job.status.value,
        analysis_id=job.analysis_id,
        error_message=job.error_message,
    )


@router.post("/jobs/{job_id}/cancel")
async def skill_job_cancel(job_id: str) -> AnalysisJobStatus:
    """Cancel a running skill analysis job.

    Args:
        job_id: The job identifier to cancel.

    Returns:
        Updated job status.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    cancel_job(job_id)
    return AnalysisJobStatus(
        job_id=job.job_id,
        status=job.status.value,
        analysis_id=job.analysis_id,
        error_message=job.error_message,
    )


@router.get("/history")
async def skill_analysis_history() -> list[SkillAnalysisMeta]:
    """List all persisted skill analyses, newest first."""
    return get_skill_analysis_store().list_analyses()


@router.get("/{analysis_id}")
async def skill_analysis_load(analysis_id: str) -> SkillAnalysisResult:
    """Load a persisted skill analysis by ID.

    Args:
        analysis_id: Unique analysis identifier.

    Returns:
        Full SkillAnalysisResult.
    """
    result = get_skill_analysis_store().load(analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    return result


@router.delete("/{analysis_id}")
async def skill_analysis_delete(analysis_id: str) -> dict[str, bool]:
    """Delete a persisted skill analysis.

    Args:
        analysis_id: Unique analysis identifier.

    Returns:
        Success status.
    """
    deleted = get_skill_analysis_store().delete(analysis_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    return {"deleted": True}
