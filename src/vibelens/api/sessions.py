"""Session endpoints."""

from fastapi import APIRouter, HTTPException

from vibelens.api.deps import get_local_source
from vibelens.models.session import SessionDetail, SessionSummary

router = APIRouter(tags=["sessions"])


@router.get("/sessions")
async def list_sessions(
    project_name: str | None = None, limit: int = 500, offset: int = 0
) -> list[SessionSummary]:
    """List sessions with optional project filter and pagination."""
    source = get_local_source()
    return source.list_sessions(project_name=project_name, limit=limit, offset=offset)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> SessionDetail:
    """Get full session detail by ID."""
    source = get_local_source()
    detail = source.get_session(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return detail


@router.get("/projects")
async def list_projects() -> list[str]:
    """List all known project names."""
    source = get_local_source()
    return source.list_projects()
