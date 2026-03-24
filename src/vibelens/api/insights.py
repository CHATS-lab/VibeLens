"""Insight endpoints — LLM-powered single-session analysis."""

from fastapi import APIRouter, Header, HTTPException

from vibelens.llm.backend import InferenceError
from vibelens.models.analysis.insights import (
    FrictionReport,
    InsightReport,
    SessionHighlights,
)
from vibelens.services.insight_service import (
    analyze_session,
    estimate_cost,
    get_session_report,
    is_inference_available,
)

router = APIRouter(prefix="/analysis", tags=["insights"])

SERVICE_UNAVAILABLE_DETAIL = "No inference backend configured. Set llm.backend in config."


@router.get("/sessions/{session_id}/report")
async def session_report(
    session_id: str, x_session_token: str | None = Header(None)
) -> InsightReport:
    """Run full insight analysis (highlights + friction) on a session.

    Args:
        session_id: Session to analyze.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        Combined InsightReport.
    """
    _require_available()
    try:
        return await get_session_report(session_id, session_token=x_session_token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InferenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/highlights")
async def session_highlights(
    session_id: str, x_session_token: str | None = Header(None)
) -> SessionHighlights:
    """Run highlights analysis on a session.

    Args:
        session_id: Session to analyze.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        SessionHighlights with summary, highlights list, and effectiveness score.
    """
    _require_available()
    from vibelens.llm.prompts import get_prompt

    prompt = get_prompt("highlights")
    if not prompt:
        raise HTTPException(status_code=500, detail="Highlights prompt not registered")
    try:
        return await analyze_session(session_id, prompt, session_token=x_session_token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InferenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/friction")
async def session_friction(
    session_id: str, x_session_token: str | None = Header(None)
) -> FrictionReport:
    """Run friction analysis on a session.

    Args:
        session_id: Session to analyze.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        FrictionReport with friction points, wasted steps, and recommendations.
    """
    _require_available()
    from vibelens.llm.prompts import get_prompt

    prompt = get_prompt("friction")
    if not prompt:
        raise HTTPException(status_code=500, detail="Friction prompt not registered")
    try:
        return await analyze_session(session_id, prompt, session_token=x_session_token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InferenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/report/estimate")
async def report_estimate(session_id: str, x_session_token: str | None = Header(None)) -> dict:
    """Estimate analysis cost for a session.

    Args:
        session_id: Session to estimate cost for.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        Dict with estimated_cost_usd (null for free backends).
    """
    try:
        cost = await estimate_cost(session_id, session_token=x_session_token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"estimated_cost_usd": cost}


def _require_available() -> None:
    """Raise 503 if no inference backend is configured."""
    if not is_inference_available():
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)
