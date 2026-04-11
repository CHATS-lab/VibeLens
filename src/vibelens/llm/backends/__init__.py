"""Backend registry and factory for inference backends.

The create_backend_from_llm_config() factory reads LLMConfig and
instantiates the configured backend, or returns None if inference is disabled.
CLI backends are registered in _CLI_BACKEND_REGISTRY and lazy-imported.
"""

import importlib

from vibelens.config.llm_config import LLMConfig
from vibelens.llm.backend import InferenceBackend
from vibelens.models.llm.inference import BackendType
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Registry mapping BackendType → (module_path, class_name)
_CLI_BACKEND_REGISTRY: dict[BackendType, tuple[str, str]] = {
    BackendType.CLAUDE_CLI: ("vibelens.llm.backends.claude_cli", "ClaudeCliBackend"),
    BackendType.CODEX_CLI: ("vibelens.llm.backends.codex_cli", "CodexCliBackend"),
    BackendType.GEMINI_CLI: ("vibelens.llm.backends.gemini_cli", "GeminiCliBackend"),
    BackendType.CURSOR_CLI: ("vibelens.llm.backends.cursor_cli", "CursorCliBackend"),
    BackendType.KIMI_CLI: ("vibelens.llm.backends.kimi_cli", "KimiCliBackend"),
    BackendType.OPENCLAW_CLI: ("vibelens.llm.backends.openclaw_cli", "OpenClawCliBackend"),
    BackendType.OPENCODE_CLI: ("vibelens.llm.backends.opencode_cli", "OpenCodeCliBackend"),
    BackendType.AIDER_CLI: ("vibelens.llm.backends.aider_cli", "AiderCliBackend"),
    BackendType.AMP_CLI: ("vibelens.llm.backends.amp_cli", "AmpCliBackend"),
}

# All CLI backends that run as subprocesses
CLI_BACKENDS = frozenset(_CLI_BACKEND_REGISTRY.keys())
# Complete set of valid backend identifiers (CLI + API + special)
KNOWN_BACKENDS = CLI_BACKENDS | {BackendType.LITELLM, BackendType.DISABLED, BackendType.MOCK}


def create_backend_from_llm_config(config: LLMConfig) -> InferenceBackend | None:
    """Factory: create the configured backend from LLMConfig, or None if disabled.

    Args:
        config: LLM configuration with backend, model, api_key, etc.

    Returns:
        Configured InferenceBackend instance, or None if disabled.
    """
    backend_id = config.backend
    if backend_id == BackendType.DISABLED:
        logger.info("LLM inference disabled")
        return None

    if backend_id not in KNOWN_BACKENDS:
        logger.warning(
            "Unknown LLM backend: %s (available: %s)", backend_id, sorted(KNOWN_BACKENDS)
        )
        return None

    if backend_id == BackendType.LITELLM:
        backend = _create_litellm_backend(config.model, config)
        logger.info("LLM backend created: type=litellm model=%s", config.model)
        return backend

    if backend_id in _CLI_BACKEND_REGISTRY:
        backend = _create_cli_backend(backend_id, config)
        logger.info("LLM backend created: type=%s", backend_id)
        return backend

    return None


def _create_litellm_backend(model: str, config: LLMConfig) -> InferenceBackend:
    """Create a LiteLLM backend instance.

    Args:
        model: Model name in litellm format (e.g. 'anthropic/claude-sonnet-4-5').
        config: LLM configuration.

    Returns:
        Configured LiteLLMBackend instance.
    """
    from vibelens.llm.backends.litellm_backend import LiteLLMBackend

    # Pass model_override when legacy alias rewrote the model name
    override = model if model != config.model else None
    return LiteLLMBackend(config=config, model_override=override)


# Cheapest model used when no model is explicitly configured for litellm
LITELLM_DEFAULT_MODEL = "anthropic/claude-haiku-4-5"


def _create_cli_backend(backend_id: BackendType, config: LLMConfig) -> InferenceBackend:
    """Create a CLI backend instance via registry lookup and lazy import.

    Resolves the model: uses config.model if explicitly set by the user,
    otherwise falls back to the backend's cheapest default.

    Args:
        backend_id: CLI backend type from _CLI_BACKEND_REGISTRY.
        config: LLM configuration.

    Returns:
        Configured CliBackend subclass instance.
    """
    module_path, class_name = _CLI_BACKEND_REGISTRY[backend_id]
    module = importlib.import_module(module_path)
    backend_cls = getattr(module, class_name)
    backend = backend_cls(timeout=config.timeout)
    resolved_model = _resolve_cli_model(config.model, backend)
    backend._model = resolved_model
    return backend


def _resolve_cli_model(config_model: str, backend: InferenceBackend) -> str | None:
    """Pick the right model for a CLI backend.

    If the user left the model at the litellm default or empty, use the
    backend's own default. Otherwise pass the user's choice through.

    Args:
        config_model: Model string from LLMConfig.
        backend: Instantiated CLI backend with model metadata.

    Returns:
        Resolved model name, or None for backends without model support.
    """
    is_default = not config_model or config_model == LITELLM_DEFAULT_MODEL
    if is_default:
        return backend.default_model
    return config_model
