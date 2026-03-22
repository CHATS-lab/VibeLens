"""File upload endpoints — thin HTTP layer delegating to services."""

from fastapi import APIRouter, Form, Header, HTTPException, UploadFile

from vibelens.models.enums import AgentType
from vibelens.models.upload import UploadResult
from vibelens.services.upload_service import get_upload_command, process_zip

router = APIRouter(tags=["upload"])


@router.get("/upload/commands")
async def get_upload_commands(agent_type: str, os_platform: str) -> dict:
    """Return a CLI command for zipping the agent's data directory.

    Args:
        agent_type: Agent CLI identifier (claude_code, codex, gemini).
        os_platform: Operating system (macos, linux, windows).

    Returns:
        Dict with 'command' and 'description' keys.
    """
    return get_upload_command(agent_type, os_platform)


@router.post("/upload/zip")
async def upload_zip(
    file: UploadFile, agent_type: str = Form(...), x_session_token: str | None = Header(None)
) -> UploadResult:
    """Upload a zip archive of agent conversation data.

    Args:
        file: Uploaded zip file.
        agent_type: Agent CLI identifier (claude_code, codex, gemini).
        x_session_token: Browser tab token for upload ownership.

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

    return await process_zip(file, agent_type, session_token=x_session_token)
