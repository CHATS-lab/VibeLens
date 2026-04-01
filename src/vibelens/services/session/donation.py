"""Session donation — package and send sessions to the donation server."""

from vibelens.deps import is_demo_mode
from vibelens.schemas.session import DonateResult
from vibelens.services.donation.sender import send_donation
from vibelens.services.session.store_resolver import get_metadata_from_stores
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
    visible_ids = _filter_donatable_ids(session_ids, session_token)
    if not visible_ids.valid:
        return DonateResult(total=len(session_ids), donated=0, errors=visible_ids.errors)

    return await send_donation(visible_ids.valid, session_token)


class _DonatableResult:
    """Result of filtering session IDs by donatability."""

    def __init__(self) -> None:
        self.valid: list[str] = []
        self.errors: list[dict] = []


def _filter_donatable_ids(session_ids: list[str], session_token: str | None) -> _DonatableResult:
    """Check accessibility and donatability for each session ID.

    Access is gated by store_resolver: if the session is not in any store
    accessible to this token, get_metadata_from_stores returns None.
    Example sessions (no _upload_id tag) cannot be donated.

    Args:
        session_ids: Session IDs to check.
        session_token: Browser tab token for upload scoping.

    Returns:
        Result with donatable IDs and error dicts for rejected ones.
    """
    demo = is_demo_mode()
    result = _DonatableResult()
    for session_id in session_ids:
        meta = get_metadata_from_stores(session_id, session_token)
        if not meta:
            result.errors.append({"session_id": session_id, "error": "Session not found"})
        elif demo and not meta.get("_upload_id"):
            result.errors.append(
                {"session_id": session_id, "error": "Example sessions cannot be donated"}
            )
        else:
            result.valid.append(session_id)
    return result
