"""System endpoints for settings, status, and LLM configuration."""

from fastapi import APIRouter, HTTPException

from vibelens import __version__
from vibelens.config.llm_config import LLMConfig, mask_api_key
from vibelens.deps import (
    get_inference_backend,
    get_llm_config,
    get_settings,
    is_demo_mode,
    is_test_mode,
    set_llm_config,
)
from vibelens.models.inference import BackendType
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
    """Return current LLM inference backend status and configuration.

    Returns:
        Dict with available, backend_id, model, and config fields.
    """
    if is_test_mode():
        return {"available": True, "backend_id": BackendType.MOCK, "model": "mock/test-model"}

    config = get_llm_config()
    backend = get_inference_backend()
    masked_key = mask_api_key(config.api_key) if config.api_key else None
    if not backend:
        return {
            "available": False,
            "backend_id": BackendType.DISABLED,
            "model": None,
            "api_key_masked": masked_key,
            "base_url": config.base_url,
            "timeout": config.timeout,
            "max_tokens": config.max_tokens,
        }
    return {
        "available": True,
        "backend_id": backend.backend_id,
        "model": getattr(backend, "_model", "unknown"),
        "api_key_masked": masked_key,
        "base_url": config.base_url,
        "timeout": config.timeout,
        "max_tokens": config.max_tokens,
    }


@router.post("/llm/configure")
async def configure_llm(body: LLMConfigureRequest) -> dict:
    """Hot-swap the LLM inference backend at runtime and persist config.

    Args:
        body: Full LLM configuration to apply.

    Returns:
        Updated LLM status dict.
    """
    # If no new key provided, keep the existing one
    api_key = body.api_key
    if not api_key:
        api_key = get_llm_config().api_key

    config = LLMConfig(
        backend=body.backend,
        api_key=api_key,
        model=body.model,
        base_url=body.base_url,
        timeout=body.timeout,
        max_tokens=body.max_tokens,
    )

    try:
        set_llm_config(config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to create backend: {exc}") from exc

    logger.info("LLM backend hot-swapped: backend=%s model=%s", config.backend, config.model)

    backend = get_inference_backend()
    return {
        "available": backend is not None,
        "backend_id": config.backend,
        "model": config.model,
        "base_url": config.base_url,
        "timeout": config.timeout,
        "max_tokens": config.max_tokens,
    }
