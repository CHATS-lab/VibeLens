"""Donation endpoints — send donations (self-use) and receive them (demo)."""

from fastapi import APIRouter, Header, UploadFile

from vibelens.schemas.session import DonateRequest, DonateResult
from vibelens.services.donation.receiver import receive_donation
from vibelens.services.session.donation import donate_sessions

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
    return await donate_sessions(request.session_ids, session_token=x_session_token)


@router.post("/donation/receive")
async def receive_donation_endpoint(file: UploadFile) -> dict:
    """Receive a donated ZIP archive from a self-use VibeLens instance.

    Args:
        file: Uploaded ZIP containing raw session files and parsed trajectories.

    Returns:
        Dict with upload_id, session_count, and zip_size_bytes.
    """
    return await receive_donation(file)
