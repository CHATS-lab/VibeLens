"""Recommendation endpoints -- personalized tool and skill recommendations."""

import asyncio
import secrets

from fastapi import APIRouter, Header, HTTPException

from vibelens.deps import get_recommendation_store, is_demo_mode, is_test_mode
from vibelens.models.recommendation.results import RecommendationResult
from vibelens.schemas.analysis import AnalysisJobResponse, AnalysisJobStatus
from vibelens.schemas.cost_estimate import CostEstimateResponse
from vibelens.schemas.recommendation import (
    CatalogStatusResponse,
    RecommendationAnalyzeRequest,
)
from vibelens.services.job_tracker import (
    cancel_job,
    get_job,
    mark_completed,
    mark_failed,
    submit_job,
)
from vibelens.services.recommendation import analyze_recommendation, estimate_recommendation
from vibelens.services.recommendation.catalog import load_catalog
from vibelens.services.recommendation.mock import build_mock_recommendation_result
from vibelens.services.recommendation.store import RecommendationMeta
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/recommendation", tags=["recommendation"])


async def _run_recommendation(
    job_id: str, session_ids: list[str], token: str | None
) -> None:
    """Background wrapper that runs recommendation analysis and updates job status."""
    try:
        result = await analyze_recommendation(session_ids, session_token=token)
        mark_completed(job_id, result.analysis_id or "")
    except asyncio.CancelledError:
        logger.info("Recommendation job %s was cancelled", job_id)
        raise
    except Exception as exc:
        mark_failed(job_id, f"{type(exc).__name__}: {exc}")
        logger.exception("Recommendation job %s failed", job_id)


@router.post("/estimate")
async def recommendation_estimate(
    body: RecommendationAnalyzeRequest, x_session_token: str | None = Header(None)
) -> CostEstimateResponse:
    """Pre-flight cost estimate for recommendation analysis.

    Args:
        body: Request with session IDs to analyze.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        Cost estimate with model info and projected cost range.
    """
    if not body.session_ids:
        raise HTTPException(status_code=400, detail="session_ids must not be empty")

    try:
        est = estimate_recommendation(body.session_ids, session_token=x_session_token)
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


@router.post("/analyze")
async def recommendation_analyze(
    body: RecommendationAnalyzeRequest, x_session_token: str | None = Header(None)
) -> AnalysisJobResponse:
    """Start recommendation analysis on specified sessions.

    Args:
        body: Request with session IDs to analyze.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        AnalysisJobResponse with job_id and status.
    """
    if not body.session_ids:
        raise HTTPException(status_code=400, detail="session_ids must not be empty")

    if is_test_mode() or is_demo_mode():
        result = build_mock_recommendation_result(body.session_ids)
        get_recommendation_store().save(result, result.analysis_id)
        return AnalysisJobResponse(
            job_id="mock", status="completed", analysis_id=result.analysis_id
        )

    job_id = secrets.token_urlsafe(12)
    try:
        submit_job(
            job_id,
            _run_recommendation(job_id, body.session_ids, x_session_token),
        )
    except ValueError as exc:
        status = 503 if "inference backend" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    return AnalysisJobResponse(job_id=job_id, status="running")


@router.get("/jobs/{job_id}")
async def recommendation_job_status(job_id: str) -> AnalysisJobStatus:
    """Poll the status of a background recommendation job.

    Args:
        job_id: The job identifier returned by POST /analyze.

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
async def recommendation_job_cancel(job_id: str) -> AnalysisJobStatus:
    """Cancel a running recommendation job.

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
async def recommendation_history() -> list[RecommendationMeta]:
    """List all persisted recommendation analyses, newest first."""
    return get_recommendation_store().list_analyses()


@router.get("/catalog/status")
async def catalog_status() -> CatalogStatusResponse:
    """Return catalog version and item count.

    Returns:
        CatalogStatusResponse with version, item_count, and schema_version.
    """
    catalog = load_catalog()
    if not catalog:
        raise HTTPException(status_code=404, detail="No catalog available")
    return CatalogStatusResponse(
        version=catalog.version,
        item_count=len(catalog.items),
        schema_version=catalog.schema_version,
    )


@router.get("/{analysis_id}")
async def recommendation_load(analysis_id: str) -> RecommendationResult:
    """Load a persisted recommendation analysis by ID.

    Args:
        analysis_id: Unique analysis identifier.

    Returns:
        Full RecommendationResult.
    """
    result = get_recommendation_store().load(analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    return result


@router.delete("/{analysis_id}")
async def recommendation_delete(analysis_id: str) -> dict[str, bool]:
    """Delete a persisted recommendation analysis.

    Args:
        analysis_id: Unique analysis identifier.

    Returns:
        Success status.
    """
    deleted = get_recommendation_store().delete(analysis_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    return {"deleted": True}
