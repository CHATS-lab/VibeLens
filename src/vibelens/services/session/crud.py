"""Session retrieval and export business logic."""

from vibelens.deps import get_store
from vibelens.models.trajectories import Trajectory
from vibelens.services.session.store_resolver import (
    get_metadata_from_stores,
    list_all_metadata,
    load_from_stores,
)
from vibelens.services.upload.visibility import filter_visible, is_session_visible
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
    summaries = list_all_metadata()
    summaries = filter_visible(summaries, session_token)
    summaries.sort(key=lambda s: s.get("timestamp") or "", reverse=True)
    if project_name:
        summaries = [s for s in summaries if s.get("project_path") == project_name]
    if limit > 0:
        return summaries[offset : offset + limit]
    return summaries[offset:] if offset else summaries


def get_session(session_id: str, session_token: str | None = None) -> list[Trajectory] | None:
    """Load a trajectory group by session ID.

    Args:
        session_id: Main session identifier.
        session_token: Browser tab token for upload scoping (demo mode).

    Returns:
        List of Trajectory objects, or None if not found.
    """
    if not is_session_visible(get_metadata_from_stores(session_id), session_token):
        return None
    return load_from_stores(session_id)


def list_projects() -> list[str]:
    """List all known project paths from all active stores.

    Returns:
        Sorted list of unique project path strings.
    """
    from vibelens.deps import get_example_store, is_demo_mode

    projects = set(get_store().list_projects())
    if is_demo_mode():
        projects.update(get_example_store().list_projects())
    return sorted(projects)
