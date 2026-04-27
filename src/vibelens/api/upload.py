"""File upload endpoints — thin HTTP layer delegating to services."""

import contextlib
from datetime import datetime

from fastapi import APIRouter, Form, Header, HTTPException, UploadFile

from vibelens.deps import share_prior_upload_with_token
from vibelens.models.enums import AgentType
from vibelens.schemas.upload import UploadResult
from vibelens.services.upload.agents import list_user_facing_specs
from vibelens.services.upload.processor import (
    find_prior_upload,
    load_prior_result,
    process_zip,
)
from vibelens.utils import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["upload"])


@router.get("/upload/agents")
async def get_upload_agents() -> dict:
    """Return the user-facing agent registry for the upload wizard.

    Each spec carries its per-OS commands inline so the wizard can render
    everything from a single fetch.
    """
    return {"agents": [s.model_dump() for s in list_user_facing_specs()]}


@router.post("/upload/zip")
async def upload_zip(
    file: UploadFile,
    agent_type: str = Form(...),
    x_session_token: str | None = Header(None),
    x_zip_sha256: str | None = Header(None),
) -> UploadResult:
    """Upload a zip archive of agent conversation data.

    Args:
        file: Uploaded zip file.
        agent_type: Agent CLI identifier (claude_code, codex, gemini).
        x_session_token: Browser tab token for upload ownership.
        x_zip_sha256: Optional client-computed SHA-256 of the zip bytes.
            When present, the server checks for prior uploads of the same
            content + agent and returns the cached result instantly,
            without consuming the request body.

    Returns:
        UploadResult with counts and any errors.
    """
    filename = file.filename or "upload.zip"
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")

    try:
        AgentType(agent_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown agent_type: {agent_type}") from None

    # Header-based early dedupe: skip reading the body entirely when the
    # client pre-hashed and we already have this content imported.
    if x_zip_sha256:
        prior = find_prior_upload(x_zip_sha256.lower(), agent_type)
        if prior is not None:
            cached = load_prior_result(prior)
            if cached is not None:
                cached.deduplicated = True
                cached.original_upload_id = prior.get("upload_id")
                uploaded_at = prior.get("uploaded_at")
                if uploaded_at:
                    with contextlib.suppress(TypeError, ValueError):
                        cached.original_uploaded_at = datetime.fromisoformat(uploaded_at)
                # Make the prior data visible to *this* token too — without
                # this, the dedup'd response is hollow because /api/sessions
                # filters by token.
                if x_session_token and prior.get("upload_id"):
                    share_prior_upload_with_token(prior["upload_id"], x_session_token)
                logger.info(
                    "Header dedupe hit: agent=%s prior_upload=%s",
                    agent_type,
                    prior.get("upload_id"),
                )
                return cached

    logger.info(
        "upload_zip: file=%s agent=%s token=%s",
        filename,
        agent_type,
        x_session_token[:8] if x_session_token else "none",
    )
    return await process_zip(
        file,
        agent_type,
        session_token=x_session_token,
        expected_sha256=x_zip_sha256.lower() if x_zip_sha256 else None,
    )
