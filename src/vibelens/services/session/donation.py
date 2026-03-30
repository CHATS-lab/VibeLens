"""Session donation — package and send sessions to the donation server."""

from vibelens.schemas.session import DonateResult
from vibelens.services.donation.sender import send_donation
from vibelens.services.session.store_resolver import get_metadata_from_stores
from vibelens.services.upload.visibility import is_session_visible
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


async def donate_sessions(session_ids: list[str], session_token: str | None = None) -> DonateResult:
    """Package sessions into a ZIP and send to the donation server.

    Collects session data from the active store (LocalStore or DiskStore),
    creates a ZIP with raw files + parsed trajectories, and POSTs it to
    the configured donation URL.

    Args:
        session_ids: Session IDs to donate.
        session_token: Browser tab token for upload scoping.

    Returns:
        DonateResult with counts and per-session errors.
    """
    visible_ids = _filter_visible_ids(session_ids, session_token)
    if not visible_ids.valid:
        return DonateResult(total=len(session_ids), donated=0, errors=visible_ids.errors)

    return await send_donation(visible_ids.valid, session_token)


class _VisibilityResult:
    """Result of filtering session IDs by visibility."""

    def __init__(self) -> None:
        self.valid: list[str] = []
        self.errors: list[dict] = []


def _filter_visible_ids(session_ids: list[str], session_token: str | None) -> _VisibilityResult:
    """Check visibility for each session ID and partition into valid/errors.

    Args:
        session_ids: Session IDs to check.
        session_token: Browser tab token for upload scoping.

    Returns:
        Result with visible IDs and error dicts for invisible ones.
    """
    result = _VisibilityResult()
    for session_id in session_ids:
        if is_session_visible(get_metadata_from_stores(session_id), session_token):
            result.valid.append(session_id)
        else:
            result.errors.append({"session_id": session_id, "error": "Session not found"})
    return result
