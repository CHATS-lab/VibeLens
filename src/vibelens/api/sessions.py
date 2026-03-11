"""Session endpoints."""

from fastapi import APIRouter

router = APIRouter(tags=["sessions"])


@router.get("/sessions")
async def list_sessions() -> list:
    """List all sessions across configured sources.

    Not yet implemented.
    """
    return []


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    """Get full session detail by ID.

    Not yet implemented.
    """
    return {"session_id": session_id, "messages": []}


@router.get("/projects")
async def list_projects() -> list:
    """List all known projects.

    Not yet implemented.
    """
    return []
