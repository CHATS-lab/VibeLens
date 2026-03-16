"""Session endpoints."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from vibelens.api.deps import get_local_source
from vibelens.db import get_connection, query_session_detail, query_sessions
from vibelens.models.session import DataSourceType, SessionDetail, SessionSummary
from vibelens.targets.mongodb import flatten_messages, serialize_session

router = APIRouter(tags=["sessions"])

SQLITE_SOURCE_TYPES = (DataSourceType.UPLOAD.value, DataSourceType.HUGGINGFACE.value)


@router.get("/sessions")
async def list_sessions(
    project_name: str | None = None, limit: int = 500, offset: int = 0
) -> list[SessionSummary]:
    """List sessions from local source and SQLite, merged by timestamp."""
    local_sessions = get_local_source().list_sessions(
        project_name=project_name, limit=limit + offset, offset=0
    )
    sqlite_sessions = await _query_sqlite_sessions(project_name, limit + offset)
    merged = _merge_sessions(local_sessions, sqlite_sessions)
    return merged[offset : offset + limit]


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> SessionDetail:
    """Get full session detail by ID, checking local then SQLite."""
    source = get_local_source()
    detail = source.get_session(session_id)
    if detail is not None:
        return detail

    detail = await _query_sqlite_detail(session_id)
    if detail is not None:
        return detail

    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/sessions/{session_id}/export")
async def export_session(session_id: str) -> JSONResponse:
    """Export session in MongoDB document format as downloadable JSON."""
    source = get_local_source()
    detail = source.get_session(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found")

    payload = {
        "session": serialize_session(detail),
        "messages": flatten_messages(detail),
    }
    filename = f"vibelens-{session_id[:8]}.json"
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/projects")
async def list_projects() -> list[str]:
    """List all known project names from local source and SQLite."""
    source = get_local_source()
    local_projects = set(source.list_projects())
    sqlite_projects = await _query_sqlite_projects()
    return sorted(local_projects | sqlite_projects)


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
