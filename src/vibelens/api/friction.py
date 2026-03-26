"""Friction analysis endpoints — user-centric multi-session LLM-powered friction detection."""

from fastapi import APIRouter, Header, HTTPException

from vibelens.deps import get_friction_store, is_demo_mode, is_test_mode
from vibelens.llm.backend import InferenceError
from vibelens.models.analysis.friction import (
    FrictionAnalysisRequest,
    FrictionAnalysisResult,
)
from vibelens.schemas.friction import FrictionMeta
from vibelens.services.friction.analysis import analyze_friction
from vibelens.services.mock import build_mock_friction_result
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/analysis", tags=["friction"])


@router.post("/friction")
async def friction_analysis(
    body: FrictionAnalysisRequest, x_session_token: str | None = Header(None)
) -> FrictionAnalysisResult:
    """Run multi-session friction analysis on specified sessions.

    Args:
        body: Request with session IDs to analyze.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        FrictionAnalysisResult with events, mitigations, and type summary.
    """
    if not body.session_ids:
        raise HTTPException(status_code=400, detail="session_ids must not be empty")

    if is_test_mode() or is_demo_mode():
        return build_mock_friction_result(body.session_ids)

    try:
        return await analyze_friction(body.session_ids, session_token=x_session_token)
    except ValueError as exc:
        status = 503 if "inference backend" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except InferenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error in friction analysis")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {type(exc).__name__}: {exc}",
        ) from exc


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
