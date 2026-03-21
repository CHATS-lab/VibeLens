"""System endpoints for settings and status."""

from fastapi import APIRouter

from vibelens import __version__
from vibelens.deps import get_settings, is_demo_mode

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
        "app_mode": settings.app_mode.value,
        "max_zip_bytes": settings.max_zip_bytes,
        "visible_agents": settings.visible_agents,
    }


@router.get("/sources")
async def list_sources() -> list:
    """List configured data sources."""
    demo = is_demo_mode()

    sources = []
    if not demo:
        sources.append({"type": "local", "name": "Local Claude Code"})
    # Upload source is always available
    sources.append({"type": "upload", "name": "File Upload"})
    return sources
