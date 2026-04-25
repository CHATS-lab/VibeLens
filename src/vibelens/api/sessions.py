"""Session endpoints — thin HTTP layer delegating to services."""

import io
import json
import zipfile

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from vibelens.models.dashboard.dashboard import SessionAnalytics
from vibelens.schemas.session import DownloadRequest
from vibelens.services.dashboard.loader import get_session_analytics
from vibelens.services.session.crud import get_session, list_projects, list_sessions
from vibelens.services.session.flow import get_session_flow
from vibelens.services.session.search import search_sessions
from vibelens.utils import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["sessions"])


@router.get("/sessions")
async def list_sessions_endpoint(
    project_name: str | None = None,
    limit: int = 0,
    offset: int = 0,
    refresh: bool = False,
    x_session_token: str | None = Header(None),
) -> list[dict]:
    """List trajectory summaries (without steps).

    Args:
        project_name: Optional project path filter.
        limit: Max results.
        offset: Results to skip.
        refresh: If True, invalidate cached index to discover new sessions.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        List of trajectory summary dicts.
    """
    return list_sessions(
        project_name, limit, offset, session_token=x_session_token, refresh=refresh
    )


@router.get("/sessions/search")
async def search_sessions_endpoint(
    search_text: str = Query("", alias="q", description="Search query."),
    x_session_token: str | None = Header(None),
) -> list[dict]:
    """Search sessions by query, returning BM25F-ranked results.

    The engine scores across all four indexed fields (user_prompts,
    agent_messages, tool_calls, session_id) and lets BM25 weights do the
    selecting. Tier 2 is rebuilt in the background at startup; during
    the first ~24 s after launch, results fall back to Tier 1 metadata
    substring matching.

    Args:
        search_text: The user's search query. Exposed to clients as ``?q=``
            for URL compactness; internally addressed by its full name.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        List of ``{"session_id": str, "score": float}`` entries ordered
        best first. ``score`` is 0.0 for Tier 1 fallback matches.
    """
    if not search_text:
        return []
    hits = search_sessions(search_text, session_token=x_session_token)
    return [{"session_id": h.session_id, "score": h.composite_score} for h in hits]


@router.get("/sessions/{session_id}")
async def get_session_endpoint(
    session_id: str, x_session_token: str | None = Header(None)
) -> list[dict]:
    """Get full trajectory group (main + sub-agents) by session ID.

    Args:
        session_id: Main session identifier.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        JSON array of Trajectory dicts.
    """
    group = get_session(session_id, session_token=x_session_token)
    if not group:
        raise HTTPException(status_code=404, detail="Session not found")
    return [t.model_dump(mode="json") for t in group]


@router.get("/sessions/{session_id}/export")
async def export_session(
    session_id: str, x_session_token: str | None = Header(None)
) -> JSONResponse:
    """Export trajectory group as downloadable JSON.

    Args:
        session_id: Main session identifier.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        JSON response with Content-Disposition header.
    """
    group = get_session(session_id, session_token=x_session_token)
    if not group:
        logger.warning(
            "export_session: session %s not found (token=%s)",
            session_id,
            x_session_token[:8] if x_session_token else "none",
        )
        raise HTTPException(status_code=404, detail="Session not found")

    payload = [t.model_dump(mode="json") for t in group]
    filename = f"vibelens-{session_id[:8]}.json"
    logger.info("export_session: exporting %s (%d trajectories)", session_id[:8], len(payload))
    return JSONResponse(
        content=payload, headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/sessions/{session_id}/flow")
async def session_flow(session_id: str, x_session_token: str | None = Header(None)) -> dict:
    """Compute tool dependency graph and phase segments for a session flow diagram.

    Args:
        session_id: Main session identifier.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        Dict with session_id, tool_graph, and phase_segments.
    """
    result = get_session_flow(session_id, x_session_token)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.get("/sessions/{session_id}/stats")
def session_analytics(
    session_id: str, x_session_token: str | None = Header(None)
) -> SessionAnalytics:
    """Compute detailed analytics for a single session."""
    result = get_session_analytics(session_id, x_session_token)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.post("/sessions/download")
async def download_sessions(
    request: DownloadRequest, x_session_token: str | None = Header(None)
) -> StreamingResponse:
    """Export multiple sessions as a downloadable zip archive.

    Args:
        request: DownloadRequest with session_ids to export.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        StreamingResponse with application/zip content.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for session_id in request.session_ids:
            group = get_session(session_id, session_token=x_session_token)
            if not group:
                logger.warning(
                    "download_sessions: session %s not found, skipping (token=%s)",
                    session_id,
                    x_session_token[:8] if x_session_token else "none",
                )
                continue
            payload = [t.model_dump(mode="json") for t in group]
            filename = f"vibelens-{session_id[:8]}.json"
            zf.writestr(filename, json.dumps(payload, indent=2, default=str, ensure_ascii=False))

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="vibelens-export.zip"'},
    )


@router.get("/projects")
async def list_projects_endpoint(x_session_token: str | None = Header(None)) -> list[str]:
    """List all known project paths.

    Args:
        x_session_token: Browser tab token for per-user isolation.

    Returns:
        Sorted list of project path strings.
    """
    return list_projects(session_token=x_session_token)
