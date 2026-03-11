"""System endpoints for settings and status."""

from fastapi import APIRouter

from vibelens import __version__
from vibelens.api.deps import get_settings

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
    }


@router.get("/sources")
async def list_sources() -> list:
    """List configured data sources.

    Not yet implemented.
    """
    return [{"type": "local", "name": "Local Claude Code"}]


@router.get("/targets")
async def list_targets() -> list:
    """List configured data targets.

    Not yet implemented.
    """
    return []
