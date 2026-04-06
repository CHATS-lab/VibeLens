"""System endpoints for settings, status, and LLM configuration."""

import importlib

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
from vibelens.llm.backends import _CLI_BACKEND_REGISTRY
from vibelens.llm.pricing import lookup_pricing
from vibelens.models.llm.inference import BackendType
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
        "max_analysis_sessions": settings.max_analysis_sessions,
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
            "pricing": None,
        }

    model_name = getattr(backend, "_model", None) or "unknown"
    pricing = _format_pricing(model_name)
    return {
        "available": True,
        "backend_id": backend.backend_id,
        "model": model_name,
        "api_key_masked": masked_key,
        "base_url": config.base_url,
        "timeout": config.timeout,
        "max_tokens": config.max_tokens,
        "pricing": pricing,
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
    model_name = config.model
    pricing = _format_pricing(model_name)
    return {
        "available": backend is not None,
        "backend_id": config.backend,
        "model": model_name,
        "base_url": config.base_url,
        "timeout": config.timeout,
        "max_tokens": config.max_tokens,
        "pricing": pricing,
    }


@router.get("/llm/cli-models")
async def list_cli_models() -> dict:
    """Return model metadata and pricing for all CLI backends.

    Returns:
        Dict mapping backend_id to models, default, freeform flag, and pricing.
    """
    result: dict[str, dict] = {}
    for backend_type, (module_path, class_name) in _CLI_BACKEND_REGISTRY.items():
        module = importlib.import_module(module_path)
        backend_cls = getattr(module, class_name)
        backend = backend_cls()

        models_with_pricing = []
        for model_name in backend.available_models:
            entry: dict = {"name": model_name}
            pricing = lookup_pricing(model_name)
            if pricing:
                entry["input_per_mtok"] = pricing.input_per_mtok
                entry["output_per_mtok"] = pricing.output_per_mtok
            models_with_pricing.append(entry)

        result[str(backend_type)] = {
            "models": models_with_pricing,
            "default_model": backend.default_model,
            "supports_freeform": backend.supports_freeform_model,
        }
    return result


def _format_pricing(model_name: str) -> dict | None:
    """Look up pricing for a model and return a compact dict.

    Args:
        model_name: Model name to look up.

    Returns:
        Dict with input/output per-MTok prices, or None if not found.
    """
    pricing = lookup_pricing(model_name)
    if not pricing:
        return None
    return {
        "input_per_mtok": pricing.input_per_mtok,
        "output_per_mtok": pricing.output_per_mtok,
    }
