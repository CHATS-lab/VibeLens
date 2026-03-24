"""System endpoints for settings, status, and LLM configuration."""

from fastapi import APIRouter, HTTPException

from vibelens import __version__
from vibelens.deps import (
    get_inference_backend,
    get_settings,
    is_demo_mode,
    is_test_mode,
    set_inference_backend,
)
from vibelens.schemas.llm import LLMConfigureRequest
from vibelens.utils.log import get_logger

router = APIRouter(tags=["system"])

logger = get_logger(__name__)


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


@router.get("/llm/status")
async def llm_status() -> dict:
    """Return current LLM inference backend status.

    Returns:
        Dict with available, backend_id, and model fields.
    """
    if is_test_mode():
        return {"available": True, "backend_id": "mock", "model": "mock/test-model"}
    backend = get_inference_backend()
    if not backend:
        return {"available": False, "backend_id": "disabled", "model": None}
    return {
        "available": True,
        "backend_id": backend.backend_id,
        "model": getattr(backend, "_model", "unknown"),
    }


@router.post("/llm/configure")
async def configure_llm(body: LLMConfigureRequest) -> dict:
    """Hot-swap the LLM inference backend at runtime.

    Args:
        body: API key and model to configure.

    Returns:
        Updated LLM status dict.
    """
    from vibelens.llm.backends.litellm_backend import LiteLLMBackend

    try:
        backend = LiteLLMBackend(model=body.model, api_key=body.api_key)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to create backend: {exc}") from exc

    set_inference_backend(backend)
    logger.info("LLM backend hot-swapped to litellm model=%s", body.model)

    return {"available": True, "backend_id": backend.backend_id, "model": body.model}
