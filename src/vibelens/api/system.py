"""System endpoints for settings and status."""

from fastapi import APIRouter

from vibelens import __version__
from vibelens.api.deps import get_settings, is_demo_mode

router = APIRouter(tags=["system"])


@router.get("/settings")
async def get_server_settings() -> dict:
    """Return server status and configuration."""
    settings = get_settings()
    return {
        "version": __version__,
        "host": settings.host,
        "port": settings.port,
        "claude_dir": str(settings.claude_dir),
        "db_path": str(settings.db_path),
        "mongodb_configured": bool(settings.mongodb_uri),
        "hf_configured": bool(settings.hf_token),
        "app_mode": settings.app_mode.value,
    }


@router.get("/sources")
async def list_sources() -> list:
    """List configured data sources."""
    settings = get_settings()
    demo = is_demo_mode()

    sources = []
    if not demo:
        sources.append({"type": "local", "name": "Local Claude Code"})
    if not demo and settings.mongodb_uri:
        sources.append({"type": "mongodb", "name": "MongoDB"})
    if not demo and settings.hf_token:
        sources.append({"type": "huggingface", "name": "HuggingFace"})
    # Upload source is always available
    sources.append({"type": "upload", "name": "File Upload"})
    return sources


@router.get("/targets")
async def list_targets() -> list:
    """List configured data targets."""
    settings = get_settings()
    demo = is_demo_mode()

    targets = []
    if not demo and settings.mongodb_uri:
        targets.append({"type": "mongodb", "name": "MongoDB"})
    if not demo and settings.hf_token:
        targets.append({"type": "huggingface", "name": "HuggingFace"})
    return targets
