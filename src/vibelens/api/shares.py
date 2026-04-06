"""Share endpoints for creating and retrieving shareable session links."""

from fastapi import APIRouter, Header, HTTPException, Request

from vibelens.deps import get_settings, get_share_service
from vibelens.schemas.share import ShareMeta, ShareRequest, ShareResponse
from vibelens.services.session.crud import get_session
from vibelens.services.session.flow import compute_flow_from_trajectories
from vibelens.services.session.share import extract_title

router = APIRouter(prefix="/shares", tags=["shares"])

# Demo URL for share links when running in demo mode
DEMO_PUBLIC_URL = "https://vibelens.chats-lab.org"
# Local URL patterns that indicate the app is running on a developer's machine
LOCAL_HOSTS = ("127.0.0.1", "0.0.0.0", "localhost")


def _build_share_url(request: Request, session_id: str) -> str:
    """Build the full shareable URL from the current request context."""
    settings = get_settings()
    if settings.public_url:
        base = settings.public_url.rstrip("/")
    elif settings.app_mode.value == "demo":
        base = DEMO_PUBLIC_URL
    elif settings.host in LOCAL_HOSTS:
        base = f"http://localhost:{settings.port}"
    else:
        base = str(request.base_url).rstrip("/")
    return f"{base}/?share={session_id}"


@router.post("")
async def create_share(
    body: ShareRequest, request: Request, x_session_token: str | None = Header(None)
) -> ShareResponse:
    """Mark a session as shared and return the shareable URL.

    Args:
        body: ShareRequest with session_id.
        request: FastAPI request for URL construction.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        ShareResponse with session_id, URL, title, and created_at.
    """
    trajectories = get_session(body.session_id, session_token=x_session_token)
    if not trajectories:
        raise HTTPException(status_code=404, detail="Session not found")

    title = extract_title(trajectories)
    share_service = get_share_service()
    meta = share_service.share(body.session_id, title)
    url = _build_share_url(request, meta.session_id)

    return ShareResponse(
        session_id=meta.session_id, url=url, title=meta.title, created_at=meta.created_at
    )


@router.get("")
async def list_shares() -> list[ShareMeta]:
    """List all shared sessions.

    Returns:
        List of ShareMeta sorted by creation time (newest first).
    """
    return get_share_service().list_shared()


@router.get("/{session_id}")
async def get_share(session_id: str) -> list[dict]:
    """Get shared trajectory data by session ID (public, no auth).

    Loads from the normal trajectory store, gated by the share registry.

    Args:
        session_id: Shared session identifier.

    Returns:
        JSON array of trajectory dicts.
    """
    share_service = get_share_service()
    if not share_service.is_shared(session_id):
        raise HTTPException(status_code=404, detail="Share not found")

    trajectories = get_session(session_id)
    if not trajectories:
        raise HTTPException(status_code=404, detail="Session data not found")

    return [t.model_dump(mode="json") for t in trajectories]


@router.get("/{session_id}/meta")
async def get_share_meta(session_id: str) -> ShareMeta:
    """Get share metadata by session ID (public, no auth).

    Args:
        session_id: Shared session identifier.

    Returns:
        ShareMeta with session_id, title, created_at.
    """
    meta = get_share_service().get_meta(session_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Share not found")
    return meta


@router.get("/{session_id}/flow")
async def share_flow(session_id: str) -> dict:
    """Compute flow diagram data from a shared session.

    Args:
        session_id: Shared session identifier.

    Returns:
        Dict with session_id, tool_graph, and phase_segments.
    """
    share_service = get_share_service()
    if not share_service.is_shared(session_id):
        raise HTTPException(status_code=404, detail="Share not found")

    trajectories = get_session(session_id)
    if not trajectories:
        raise HTTPException(status_code=404, detail="Session data not found")

    return compute_flow_from_trajectories(trajectories, session_id)


@router.delete("/{session_id}")
async def delete_share(session_id: str) -> dict:
    """Revoke a share by removing it from the registry.

    Args:
        session_id: Session identifier to unshare.

    Returns:
        Status dict indicating success or not found.
    """
    removed = get_share_service().unshare(session_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Share not found")
    return {"status": "deleted", "session_id": session_id}
