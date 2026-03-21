"""Dashboard endpoints — aggregate stats, tool usage, session analytics, export."""

from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from vibelens.models.analysis.behavior import ToolUsageStat
from vibelens.models.analysis.dashboard import DashboardStats, SessionAnalytics
from vibelens.services.dashboard_service import (
    export_dashboard_csv,
    export_dashboard_json,
    get_dashboard_stats,
    get_session_analytics,
    get_tool_usage,
)

router = APIRouter(tags=["analysis"])


@router.get("/analysis/dashboard")
async def dashboard_stats(
    project_path: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    x_session_token: str | None = Header(None),
) -> DashboardStats:
    """Compute aggregate dashboard statistics from full trajectories."""
    return get_dashboard_stats(project_path, date_from, date_to, x_session_token)


@router.get("/analysis/tool-usage")
async def tool_usage(
    project_path: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    x_session_token: str | None = Header(None),
) -> list[ToolUsageStat]:
    """Compute per-tool usage statistics (cached)."""
    return get_tool_usage(project_path, date_from, date_to, x_session_token)


@router.get("/analysis/sessions/{session_id}/stats")
async def session_analytics(
    session_id: str, x_session_token: str | None = Header(None)
) -> SessionAnalytics:
    """Compute detailed analytics for a single session."""
    result = get_session_analytics(session_id, x_session_token)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.get("/analysis/dashboard/export")
async def export_dashboard(
    format: str = Query("csv", pattern="^(csv|json)$"),
    project_path: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    x_session_token: str | None = Header(None),
) -> StreamingResponse:
    """Export dashboard data as a downloadable file."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    if format == "json":
        return export_dashboard_json(project_path, date_from, date_to, x_session_token, timestamp)
    return export_dashboard_csv(project_path, date_from, date_to, x_session_token, timestamp)
