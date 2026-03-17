"""Session endpoints."""

import io
import json
import zipfile

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from vibelens.api.deps import get_local_source, get_session_store, is_demo_mode
from vibelens.db import get_connection, query_session_detail, query_sessions
from vibelens.models.enums import DataSourceType
from vibelens.models.requests import DownloadRequest
from vibelens.models.session import SessionDetail, SessionSummary
from vibelens.targets.export import serialize_export

router = APIRouter(tags=["sessions"])

SQLITE_SOURCE_TYPES = (DataSourceType.UPLOAD.value, DataSourceType.HUGGINGFACE.value)


@router.get("/sessions")
async def list_sessions(
    project_name: str | None = None,
    limit: int = 500,
    offset: int = 0,
    x_session_token: str = Header(default=""),
) -> list[SessionSummary]:
    """List sessions from local source and SQLite, merged by timestamp."""
    if is_demo_mode():
        store = get_session_store()
        return await store.list_sessions(x_session_token)

    local_sessions = get_local_source().list_sessions(
        project_name=project_name, limit=limit + offset, offset=0
    )
    sqlite_sessions = await _query_sqlite_sessions(project_name, limit + offset)
    merged = _merge_sessions(local_sessions, sqlite_sessions)
    return merged[offset : offset + limit]


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str, x_session_token: str = Header(default="")
) -> SessionDetail:
    """Get full session detail by ID, checking local then SQLite."""
    if is_demo_mode():
        store = get_session_store()
        detail = await store.get_session(session_id, x_session_token)
        if detail is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return detail

    detail = await _resolve_session(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return detail


@router.get("/sessions/{session_id}/export")
async def export_session(
    session_id: str, x_session_token: str = Header(default="")
) -> JSONResponse:
    """Export session in VibeLens v1 format as downloadable JSON."""
    if is_demo_mode():
        store = get_session_store()
        detail = await store.get_session(session_id, x_session_token)
    else:
        detail = await _resolve_session(session_id)

    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found")

    payload = serialize_export(detail)
    filename = f"vibelens-{session_id[:8]}.json"
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/sessions/download")
async def download_sessions(
    request: DownloadRequest, x_session_token: str = Header(default="")
) -> StreamingResponse:
    """Export multiple sessions as a downloadable zip archive.

    Each session is serialized to VibeLens Export v1 format and placed as
    a separate file in the zip.

    Args:
        request: DownloadRequest with session_ids to export.
        x_session_token: Client isolation token for demo mode.

    Returns:
        StreamingResponse with application/zip content.
    """
    demo = is_demo_mode()
    store = get_session_store() if demo else None

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for session_id in request.session_ids:
            if demo and store:
                detail = await store.get_session(session_id, x_session_token)
            else:
                detail = await _resolve_session(session_id)
            if detail is None:
                continue
            payload = serialize_export(detail)
            filename = f"vibelens-{session_id[:8]}.json"
            zf.writestr(filename, json.dumps(payload, indent=2, default=str))

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="vibelens-export.zip"'},
    )


@router.get("/projects")
async def list_projects(x_session_token: str = Header(default="")) -> list[str]:
    """List all known project names from local source and SQLite."""
    if is_demo_mode():
        store = get_session_store()
        sessions = await store.list_sessions(x_session_token)
        return sorted({s.project_name for s in sessions if s.project_name})

    source = get_local_source()
    local_projects = set(source.list_projects())
    sqlite_projects = await _query_sqlite_projects()
    return sorted(local_projects | sqlite_projects)


async def _resolve_session(session_id: str) -> SessionDetail | None:
    """Look up a session by ID from LocalSource, then SQLite.

    Args:
        session_id: Session ID to look up.

    Returns:
        SessionDetail if found, None otherwise.
    """
    source = get_local_source()
    detail = source.get_session(session_id)
    if detail is not None:
        return detail
    return await _query_sqlite_detail(session_id)


async def _query_sqlite_sessions(project_name: str | None, limit: int) -> list[SessionSummary]:
    """Query SQLite for upload and huggingface sessions.

    Returns empty list if the database is not initialized.

    Args:
        project_name: Optional project filter.
        limit: Max results.

    Returns:
        List of SessionSummary from SQLite.
    """
    try:
        conn = await get_connection()
    except RuntimeError:
        return []
    try:
        results: list[SessionSummary] = []
        for source_type in SQLITE_SOURCE_TYPES:
            sessions = await query_sessions(
                conn, source_type=source_type, project=project_name, limit=limit
            )
            results.extend(sessions)
        return results
    finally:
        await conn.close()


async def _query_sqlite_detail(session_id: str) -> SessionDetail | None:
    """Query SQLite for a full session detail.

    Returns None if the database is not initialized.

    Args:
        session_id: Session ID to look up.

    Returns:
        SessionDetail if found, None otherwise.
    """
    try:
        conn = await get_connection()
    except RuntimeError:
        return None
    try:
        summary, messages = await query_session_detail(conn, session_id)
        if summary is None:
            return None
        return SessionDetail(summary=summary, messages=messages)
    finally:
        await conn.close()


async def _query_sqlite_projects() -> set[str]:
    """Query SQLite for distinct project names.

    Returns empty set if the database is not initialized.

    Returns:
        Set of project name strings.
    """
    try:
        conn = await get_connection()
    except RuntimeError:
        return set()
    try:
        cursor = await conn.execute(
            "SELECT DISTINCT project_name FROM sessions WHERE project_name != ''"
        )
        rows = await cursor.fetchall()
        return {row[0] for row in rows}
    finally:
        await conn.close()


def _merge_sessions(
    local: list[SessionSummary], sqlite: list[SessionSummary]
) -> list[SessionSummary]:
    """Merge and deduplicate sessions from two sources, sorted by timestamp desc.

    Args:
        local: Sessions from LocalSource.
        sqlite: Sessions from SQLite.

    Returns:
        Deduplicated, sorted session list.
    """
    seen: set[str] = set()
    merged: list[SessionSummary] = []

    for session in local:
        if session.session_id not in seen:
            seen.add(session.session_id)
            merged.append(session)

    for session in sqlite:
        if session.session_id not in seen:
            seen.add(session.session_id)
            merged.append(session)

    merged.sort(key=lambda s: s.timestamp or "", reverse=True)
    return merged
