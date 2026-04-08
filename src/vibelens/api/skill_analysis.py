"""Skill analysis endpoints — LLM-powered workflow pattern detection and skill recommendations."""

import asyncio
import secrets

from fastapi import APIRouter, Header, HTTPException

from vibelens.deps import get_skill_analysis_store, is_demo_mode, is_test_mode
from vibelens.models.skill import SkillAnalysisResult
from vibelens.schemas.analysis import AnalysisJobResponse, AnalysisJobStatus
from vibelens.schemas.cost_estimate import CostEstimateResponse
from vibelens.schemas.skills import SkillAnalysisMeta, SkillAnalysisRequest
from vibelens.services.job_tracker import (
    cancel_job,
    get_job,
    mark_completed,
    mark_failed,
    submit_job,
)
from vibelens.services.skill import analyze_skills, estimate_skill_analysis
from vibelens.services.skill.mock import build_mock_skill_result
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/skills/analysis", tags=["skill-analysis"])


async def _run_skill_analysis(
    job_id: str,
    session_ids: list[str],
    mode: str,
    token: str | None,
    skill_names: list[str] | None = None,
) -> None:
    """Background wrapper for skill analysis."""
    try:
        result = await analyze_skills(
            session_ids, mode, session_token=token, skill_names=skill_names
        )
        mark_completed(job_id, result.analysis_id or "")
    except asyncio.CancelledError:
        logger.info("Skill analysis job %s was cancelled", job_id)
        raise
    except Exception as exc:
        mark_failed(job_id, f"{type(exc).__name__}: {exc}")
        logger.exception("Skill analysis job %s failed", job_id)


@router.post("/estimate")
async def skill_estimate(
    body: SkillAnalysisRequest, x_session_token: str | None = Header(None)
) -> CostEstimateResponse:
    """Pre-flight cost estimate for skill analysis.

    Args:
        body: Request with session IDs and analysis mode.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        Cost estimate with model info and projected cost range.
    """
    if not body.session_ids:
        raise HTTPException(status_code=400, detail="session_ids must not be empty")

    try:
        est = estimate_skill_analysis(
            body.session_ids, body.mode, session_token=x_session_token, skill_names=body.skill_names
        )
    except ValueError as exc:
        status = 503 if "inference backend" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    return CostEstimateResponse(
        model=est.model,
        batch_count=est.batch_count,
        total_input_tokens=est.total_input_tokens,
        total_output_tokens_budget=est.total_output_tokens_budget,
        cost_min_usd=est.cost_min_usd,
        cost_max_usd=est.cost_max_usd,
        pricing_found=est.pricing_found,
        formatted_cost=est.formatted_cost,
    )


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
            job_id,
            _run_skill_analysis(
                job_id, body.session_ids, body.mode, x_session_token, body.skill_names
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
