"""Session endpoints — thin HTTP layer delegating to services."""

import io
import json
import zipfile

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from vibelens.models.requests import DonateRequest, DonateResult, DownloadRequest
from vibelens.services.search_service import search_sessions
from vibelens.services.session_service import (
    donate_sessions,
    get_session,
    list_projects,
    list_sessions,
)

router = APIRouter(tags=["sessions"])


@router.get("/sessions")
async def list_sessions_endpoint(
    project_name: str | None = None,
    limit: int = 500,
    offset: int = 0,
    x_session_token: str | None = Header(None),
) -> list[dict]:
    """List trajectory summaries (without steps).

    Args:
        project_name: Optional project path filter.
        limit: Max results.
        offset: Results to skip.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        List of trajectory summary dicts.
    """
    return list_sessions(project_name, limit, offset, session_token=x_session_token)


@router.get("/sessions/search")
async def search_sessions_endpoint(
    q: str = "", sources: str = "user_prompts", x_session_token: str | None = Header(None)
) -> list[str]:
    """Search sessions by query across selected text sources.

    Args:
        q: Search query string.
        sources: Comma-separated source names (user_prompts, agent_content, session_id).
        x_session_token: Browser tab token for upload scoping.

    Returns:
        List of matching session IDs.
    """
    if not q:
        return []
    source_list = [s.strip() for s in sources.split(",") if s.strip()]
    return search_sessions(q, source_list, session_token=x_session_token)


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
        raise HTTPException(status_code=404, detail="Session not found")

    payload = [t.model_dump(mode="json") for t in group]
    filename = f"vibelens-{session_id[:8]}.json"
    return JSONResponse(
        content=payload, headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


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


@router.post("/sessions/donate")
async def donate_sessions_endpoint(
    request: DonateRequest, x_session_token: str | None = Header(None)
) -> DonateResult:
    """Donate selected sessions by copying them to the donation directory.

    Args:
        request: DonateRequest with session_ids to donate.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        DonateResult with counts and per-session errors.
    """
    return donate_sessions(request.session_ids, session_token=x_session_token)


@router.get("/projects")
async def list_projects_endpoint() -> list[str]:
    """List all known project paths.

    Returns:
        Sorted list of project path strings.
    """
    return list_projects()
