"""Backend registry and factory for inference backends.

The create_backend_from_config() factory reads InferenceConfig and
instantiates the configured backend, or returns None if inference is disabled.
CLI backends are registered in _CLI_BACKEND_REGISTRY and lazy-imported.
"""

import importlib

from vibelens.config.settings import InferenceConfig
from vibelens.llm.backend import InferenceBackend
from vibelens.models.llm.inference import BackendType
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Registry mapping BackendType → (module_path, class_name)
_CLI_BACKEND_REGISTRY: dict[BackendType, tuple[str, str]] = {
    BackendType.AIDER: ("vibelens.llm.backends.aider_cli", "AiderCliBackend"),
    BackendType.AMP: ("vibelens.llm.backends.amp_cli", "AmpCliBackend"),
    BackendType.CLAUDE_CODE: ("vibelens.llm.backends.claude_cli", "ClaudeCliBackend"),
    BackendType.CODEX: ("vibelens.llm.backends.codex_cli", "CodexCliBackend"),
    BackendType.CURSOR: ("vibelens.llm.backends.cursor_cli", "CursorCliBackend"),
    BackendType.GEMINI: ("vibelens.llm.backends.gemini_cli", "GeminiCliBackend"),
    BackendType.KIMI: ("vibelens.llm.backends.kimi_cli", "KimiCliBackend"),
    BackendType.OPENCODE: ("vibelens.llm.backends.opencode_cli", "OpenCodeCliBackend"),
    BackendType.OPENCLAW: ("vibelens.llm.backends.openclaw_cli", "OpenClawCliBackend"),
}

# All CLI backends that run as subprocesses
CLI_BACKENDS = frozenset(_CLI_BACKEND_REGISTRY.keys())
# Complete set of valid backend identifiers (CLI + API + special)
KNOWN_BACKENDS = CLI_BACKENDS | {BackendType.LITELLM, BackendType.DISABLED, BackendType.MOCK}


def create_backend_from_config(config: InferenceConfig) -> InferenceBackend | None:
    """Factory: create the configured backend, or None if disabled.

    Args:
        config: Inference configuration with backend, model, api_key, etc.

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


def _create_litellm_backend(model: str, config: InferenceConfig) -> InferenceBackend:
    """Create a LiteLLM backend instance.

    Args:
        model: Model name in litellm format (e.g. 'anthropic/claude-sonnet-4-5').
        config: LLM configuration.

    Returns:
        Configured LiteLLMBackend instance.
    """
    from vibelens.llm.backends.litellm import LiteLLMBackend

    # Pass model_override when legacy alias rewrote the model name
    override = model if model != config.model else None
    return LiteLLMBackend(config=config, model_override=override)


# Cheapest model used when no model is explicitly configured for litellm
LITELLM_DEFAULT_MODEL = "anthropic/claude-haiku-4-5"


def _create_cli_backend(backend_id: BackendType, config: InferenceConfig) -> InferenceBackend:
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
    resolved_model = _resolve_cli_model_for_backend(config.model, backend_id)
    cli_config = config.model_copy(update={"model": resolved_model or ""})
    return backend_cls(config=cli_config)


def _strip_provider_prefix(model: str) -> str:
    """Remove provider prefix from a litellm-format model name.

    CLI backends expect bare model names (e.g. 'claude-sonnet-4-5'),
    but the config may store litellm-format names with a provider
    prefix (e.g. 'anthropic/claude-sonnet-4-5').

    Args:
        model: Model name, possibly with provider prefix.

    Returns:
        Bare model name without provider prefix.
    """
    if "/" in model:
        return model.rsplit("/", 1)[-1]
    return model


def _resolve_cli_model_for_backend(config_model: str, backend_id: BackendType) -> str | None:
    """Pick the right model for a CLI backend by backend_id.

    Backends that accept free-form ``provider/model`` strings (aider,
    opencode, openclaw) get the user's choice verbatim; the others get the
    provider prefix stripped so they receive bare model names.

    Args:
        config_model: Model string from InferenceConfig.
        backend_id: Backend type to resolve defaults for.

    Returns:
        Resolved model name, or None for backends without model support.
    """
    from vibelens.llm.model_catalog import default_model

    is_default = not config_model or config_model == LITELLM_DEFAULT_MODEL
    if is_default:
        return default_model(backend_id)
    if backend_id in _FREEFORM_MODEL_BACKENDS:
        return config_model
    return _strip_provider_prefix(config_model)


# Backends whose CLI accepts free-form ``provider/model`` strings verbatim.
# Keep in sync with the ``supports_freeform_model`` property on each subclass.
_FREEFORM_MODEL_BACKENDS: frozenset[BackendType] = frozenset(
    {BackendType.AIDER, BackendType.OPENCODE, BackendType.OPENCLAW}
)
