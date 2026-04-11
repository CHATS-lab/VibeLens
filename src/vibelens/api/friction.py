"""Friction analysis endpoints — user-centric multi-session LLM-powered friction detection."""

import asyncio
import secrets

from fastapi import APIRouter, Header, HTTPException

from vibelens.deps import get_friction_store, is_demo_mode, is_test_mode
from vibelens.models.analysis.friction import FrictionAnalysisResult
from vibelens.schemas.analysis import AnalysisJobResponse, AnalysisJobStatus
from vibelens.schemas.cost_estimate import CostEstimateResponse
from vibelens.schemas.friction import FrictionAnalysisRequest, FrictionMeta
from vibelens.services.friction.analysis import analyze_friction, estimate_friction
from vibelens.services.friction.mock import build_mock_friction_result
from vibelens.services.job_tracker import (
    cancel_job,
    get_job,
    mark_completed,
    mark_failed,
    submit_job,
)
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/analysis", tags=["friction"])


async def _run_friction(job_id: str, session_ids: list[str], token: str | None) -> None:
    """Background wrapper that runs friction analysis and updates job status."""
    try:
        result = await analyze_friction(session_ids, session_token=token)
        mark_completed(job_id, result.analysis_id or "")
    except asyncio.CancelledError:
        logger.info("Friction job %s was cancelled", job_id)
        raise
    except Exception as exc:
        mark_failed(job_id, f"{type(exc).__name__}: {exc}")
        logger.exception("Friction job %s failed", job_id)


@router.post("/friction")
async def friction_analysis(
    body: FrictionAnalysisRequest, x_session_token: str | None = Header(None)
) -> AnalysisJobResponse:
    """Run multi-session friction analysis on specified sessions.

    Args:
        body: Request with session IDs to analyze.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        AnalysisJobResponse with job_id and status.
    """
    if not body.session_ids:
        raise HTTPException(status_code=400, detail="session_ids must not be empty")

    if is_test_mode() or is_demo_mode():
        result = build_mock_friction_result(body.session_ids)
        return AnalysisJobResponse(
            job_id="mock",
            status="completed",
            analysis_id=result.analysis_id,
        )

    job_id = secrets.token_urlsafe(12)
    try:
        submit_job(
            job_id,
            _run_friction(job_id, body.session_ids, x_session_token),
        )
    except ValueError as exc:
        status = 503 if "inference backend" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    return AnalysisJobResponse(job_id=job_id, status="running")


@router.get("/friction/jobs/{job_id}")
async def friction_job_status(job_id: str) -> AnalysisJobStatus:
    """Poll the status of a background friction analysis job.

    Args:
        job_id: The job identifier returned by POST /friction.

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


@router.post("/friction/jobs/{job_id}/cancel")
async def friction_job_cancel(job_id: str) -> AnalysisJobStatus:
    """Cancel a running friction analysis job.

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


@router.post("/friction/estimate")
async def friction_estimate(
    body: FrictionAnalysisRequest, x_session_token: str | None = Header(None)
) -> CostEstimateResponse:
    """Pre-flight cost estimate for friction analysis.

    Args:
        body: Request with session IDs.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        Cost estimate with model info and token counts.
    """
    if not body.session_ids:
        raise HTTPException(status_code=400, detail="session_ids must not be empty")

    try:
        est = estimate_friction(body.session_ids, session_token=x_session_token)
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


@router.get("/friction/history")
async def friction_history() -> list[FrictionMeta]:
    """List all persisted friction analyses, newest first."""
    return get_friction_store().list_analyses()


@router.get("/friction/{analysis_id}")
async def friction_load(analysis_id: str) -> FrictionAnalysisResult:
    """Load a persisted friction analysis by ID.

    Args:
        analysis_id: Unique analysis identifier.

    Returns:
        Full FrictionAnalysisResult.
    """
    result = get_friction_store().load(analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    return result


@router.delete("/friction/{analysis_id}")
async def friction_delete(analysis_id: str) -> dict[str, bool]:
    """Delete a persisted friction analysis.

    Args:
        analysis_id: Unique analysis identifier.

    Returns:
        Success status.
    """
    deleted = get_friction_store().delete(analysis_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    return {"deleted": True}
