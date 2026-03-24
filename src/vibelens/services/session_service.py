"""Session retrieval, export, and donation business logic."""

from vibelens.deps import get_store
from vibelens.models.trajectories import Trajectory
from vibelens.schemas.session import DonateResult
from vibelens.services.upload_visibility import filter_visible, is_session_visible
from vibelens.storage.disk import DiskStore
from vibelens.utils import get_logger

logger = get_logger(__name__)

DONATION_DIR_NAME = "donation"


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
    summaries = get_store().list_metadata()
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
    store = get_store()
    if not is_session_visible(store.get_metadata(session_id), session_token):
        return None
    return store.load(session_id)


def list_projects() -> list[str]:
    """List all known project paths.

    Returns:
        Sorted list of project path strings.
    """
    return get_store().list_projects()


def donate_sessions(session_ids: list[str], session_token: str | None = None) -> DonateResult:
    """Copy sessions to the donation directory.

    Args:
        session_ids: Session IDs to donate.
        session_token: Browser tab token for upload scoping (demo mode).

    Returns:
        DonateResult with counts and per-session errors.
    """
    store = get_store()
    # copy_to_dir is DiskStore-specific (efficient file copy without re-serialization)
    if not isinstance(store, DiskStore):
        return DonateResult(total=len(session_ids), donated=0, errors=[])
    donation_dir = store.root / DONATION_DIR_NAME
    donation_dir.mkdir(parents=True, exist_ok=True)

    donated = 0
    errors: list[dict] = []

    for session_id in session_ids:
        if not is_session_visible(store.get_metadata(session_id), session_token):
            errors.append({"session_id": session_id, "error": "Session not found"})
            continue
        try:
            store.copy_to_dir(session_id, donation_dir)
            donated += 1
        except FileNotFoundError:
            errors.append({"session_id": session_id, "error": "Session not found"})
        except OSError as exc:
            errors.append({"session_id": session_id, "error": str(exc)})

    return DonateResult(total=len(session_ids), donated=donated, errors=errors)
