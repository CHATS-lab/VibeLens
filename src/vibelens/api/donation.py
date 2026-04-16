"""Donation endpoints — send donations (self-use) and receive them (demo)."""

from fastapi import APIRouter, Header, UploadFile

from vibelens.schemas.session import DonateRequest, DonateResult
from vibelens.services.donation.receiver import receive_donation
from vibelens.services.session.donation import donate_sessions
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["donation"])


@router.post("/sessions/donate")
async def donate_sessions_endpoint(
    request: DonateRequest, x_session_token: str | None = Header(None)
) -> DonateResult:
    """Donate selected sessions.

    In self-use mode, packages raw files + parsed trajectories into a ZIP
    and sends to the configured donation server. In demo mode, copies
    parsed session JSON to a local donation subdirectory.

    Args:
        request: DonateRequest with session_ids to donate.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        DonateResult with counts and per-session errors.
    """
    token_prefix = x_session_token[:8] if x_session_token else "none"
    logger.info(
        "Donate request: sessions=%d token_prefix=%s",
        len(request.session_ids),
        token_prefix,
    )
    result = await donate_sessions(request.session_ids, session_token=x_session_token)
    logger.info(
        "Donate result: donated=%d total=%d errors=%d",
        result.donated,
        result.total,
        len(result.errors),
    )
    return result


@router.post("/donation/receive")
async def receive_donation_endpoint(file: UploadFile) -> dict:
    """Receive a donated ZIP archive from a self-use VibeLens instance.

    Args:
        file: Uploaded ZIP containing raw session files and parsed trajectories.

    Returns:
        Dict with donation_id, session_count, and zip_size_bytes.
    """
    logger.info("Donation received: filename=%s", file.filename)
    result = await receive_donation(file)
    logger.info(
        "Donation processed: donation_id=%s sessions=%d size=%d",
        result.get("donation_id"),
        result.get("session_count", 0),
        result.get("zip_size_bytes", 0),
    )
    return result
