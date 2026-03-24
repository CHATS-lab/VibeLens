"""Friction analysis endpoints — multi-session LLM-powered friction detection."""

from fastapi import APIRouter, Header, HTTPException

from vibelens.deps import get_friction_store, is_demo_mode, is_test_mode
from vibelens.llm.backend import InferenceError
from vibelens.models.analysis.friction import (
    FrictionAnalysisRequest,
    FrictionAnalysisResult,
)
from vibelens.schemas.friction import FrictionMeta
from vibelens.services.friction_service import analyze_friction
from vibelens.services.insight_service import is_inference_available
from vibelens.services.mock import build_mock_friction_result

router = APIRouter(prefix="/analysis", tags=["friction"])

SERVICE_UNAVAILABLE_DETAIL = "No inference backend configured. Set llm.backend in config."


@router.post("/friction")
async def friction_analysis(
    body: FrictionAnalysisRequest, x_session_token: str | None = Header(None)
) -> FrictionAnalysisResult:
    """Run multi-session friction analysis on specified sessions.

    Args:
        body: Request with session IDs to analyze.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        FrictionAnalysisResult with events, suggestions, and mode summary.
    """
    if not body.session_ids:
        raise HTTPException(status_code=400, detail="session_ids must not be empty")

    if is_test_mode() or is_demo_mode():
        return build_mock_friction_result(body.session_ids)

    _require_available()
    try:
        return await analyze_friction(body.session_ids, session_token=x_session_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InferenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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


def _require_available() -> None:
    """Raise 503 if no inference backend is configured."""
    if not is_inference_available():
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)
