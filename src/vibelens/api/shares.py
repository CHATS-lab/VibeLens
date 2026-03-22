"""Share endpoints for creating and retrieving shareable session links."""

from fastapi import APIRouter, Header, HTTPException, Request

from vibelens.deps import get_settings, get_share_service
from vibelens.models.share import ShareRequest, ShareResponse
from vibelens.models.trajectories import Trajectory
from vibelens.services.flow_service import compute_flow_from_trajectories
from vibelens.services.session_service import get_session
from vibelens.services.share_service import ShareMeta

router = APIRouter(prefix="/shares", tags=["shares"])


def _build_share_url(request: Request, token: str) -> str:
    """Build the full shareable URL from the current request context."""
    settings = get_settings()
    base = str(request.base_url).rstrip("/")
    # In self-use mode, use the configured host:port for stable URLs
    if settings.host in ("127.0.0.1", "0.0.0.0", "localhost"):
        base = f"http://localhost:{settings.port}"
    return f"{base}/?share={token}"


@router.post("")
async def create_share(
    body: ShareRequest,
    request: Request,
    x_session_token: str | None = Header(None),
) -> ShareResponse:
    """Create a shareable snapshot of a session.

    Args:
        body: ShareRequest with session_id.
        request: FastAPI request for URL construction.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        ShareResponse with token, URL, title, and created_at.
    """
    trajectories = get_session(body.session_id, session_token=x_session_token)
    if not trajectories:
        raise HTTPException(status_code=404, detail="Session not found")

    share_service = get_share_service()
    meta = share_service.create(body.session_id, trajectories)
    url = _build_share_url(request, meta.token)

    return ShareResponse(
        token=meta.token,
        url=url,
        title=meta.title,
        created_at=meta.created_at,
    )


@router.get("")
async def list_shares() -> list[ShareMeta]:
    """List all existing shares.

    Returns:
        List of ShareMeta sorted by creation time (newest first).
    """
    return get_share_service().list_shares()


@router.get("/{token}")
async def get_share(token: str) -> list[dict]:
    """Get shared trajectory data by token (public, no auth).

    Args:
        token: Share token.

    Returns:
        JSON array of trajectory dicts.
    """
    data = get_share_service().load(token)
    if data is None:
        raise HTTPException(status_code=404, detail="Share not found")
    return data


@router.get("/{token}/meta")
async def get_share_meta(token: str) -> ShareMeta:
    """Get share metadata by token (public, no auth).

    Args:
        token: Share token.

    Returns:
        ShareMeta with token, session_id, title, created_at.
    """
    meta = get_share_service().load_meta(token)
    if meta is None:
        raise HTTPException(status_code=404, detail="Share not found")
    return meta


@router.get("/{token}/flow")
async def share_flow(token: str) -> dict:
    """Compute flow diagram data (tool graph + phases) from a shared session.

    Args:
        token: Share token.

    Returns:
        Dict with session_id, tool_graph, and phase_segments.
    """
    raw = get_share_service().load(token)
    if raw is None:
        raise HTTPException(status_code=404, detail="Share not found")

    trajectories = [Trajectory(**t) for t in raw]
    return compute_flow_from_trajectories(trajectories, token)


@router.delete("/{token}")
async def delete_share(token: str) -> dict:
    """Revoke a share by deleting its snapshot.

    Args:
        token: Share token to revoke.

    Returns:
        Status dict indicating success or not found.
    """
    deleted = get_share_service().delete(token)
    if not deleted:
        raise HTTPException(status_code=404, detail="Share not found")
    return {"status": "deleted", "token": token}
