"""Session retrieval and export business logic."""

from vibelens.deps import get_example_store, get_store, get_upload_stores, is_demo_mode
from vibelens.models.trajectories import Trajectory
from vibelens.services.session.store_resolver import (
    get_metadata_from_stores,
    list_all_metadata,
    load_from_stores,
)
from vibelens.utils import get_logger

logger = get_logger(__name__)


def list_sessions(
    project_name: str | None, limit: int, offset: int, session_token: str | None = None
) -> list[dict]:
    """Return trajectory summaries from the active store.

    Args:
        project_name: Optional project path filter.
        limit: Max results.
        offset: Results to skip.
        session_token: Browser tab token for upload scoping (demo mode).

    Returns:
        List of trajectory summary dicts (no steps).
    """
    summaries = list_all_metadata(session_token)
    logger.info(
        "list_sessions: metadata=%d token=%s",
        len(summaries),
        session_token[:8] if session_token else "none",
    )
    summaries.sort(key=lambda s: s.get("timestamp") or "", reverse=True)
    if project_name:
        summaries = [s for s in summaries if s.get("project_path") == project_name]
    if limit > 0:
        return summaries[offset : offset + limit]
    return summaries[offset:] if offset else summaries


def get_session(session_id: str, session_token: str | None = None) -> list[Trajectory] | None:
    """Load a trajectory group by session ID.

    Access is gated by store_resolver: if the session is not in any store
    accessible to this token, get_metadata_from_stores returns None.

    Args:
        session_id: Main session identifier.
        session_token: Browser tab token for upload scoping (demo mode).

    Returns:
        List of Trajectory objects, or None if not found.
    """
    if get_metadata_from_stores(session_id, session_token) is None:
        return None
    return load_from_stores(session_id, session_token)


def list_projects(session_token: str | None = None) -> list[str]:
    """List all known project paths from stores accessible to this token.

    Args:
        session_token: Browser tab token for per-user isolation.

    Returns:
        Sorted list of unique project path strings.
    """
    if not is_demo_mode():
        return sorted(get_store().list_projects())

    projects: set[str] = set()
    user_stores = get_upload_stores(session_token)
    if user_stores:
        for store in user_stores:
            projects.update(store.list_projects())
    else:
        projects.update(get_example_store().list_projects())
    return sorted(projects)
