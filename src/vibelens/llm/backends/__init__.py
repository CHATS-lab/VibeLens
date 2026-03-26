"""Backend registry and factory for inference backends.

The create_backend_from_llm_config() factory reads LLMConfig and
instantiates the configured backend, or returns None if inference is disabled.
"""

from vibelens.config.llm_config import LLMConfig
from vibelens.llm.backend import InferenceBackend
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

DISABLED_BACKEND_ID = "disabled"

CLI_BACKENDS = {"claude-cli", "codex-cli"}
LITELLM_BACKEND = "litellm"
# Legacy aliases — route to LiteLLMBackend with provider prefix
LEGACY_HTTP_ALIASES = {"anthropic-api", "openai-api"}
KNOWN_BACKENDS = CLI_BACKENDS | LEGACY_HTTP_ALIASES | {LITELLM_BACKEND, DISABLED_BACKEND_ID}

# Maps legacy backend ID to litellm provider prefix
LEGACY_PROVIDER_MAP = {
    "anthropic-api": "anthropic",
    "openai-api": "openai",
}


def create_backend_from_llm_config(config: LLMConfig) -> InferenceBackend | None:
    """Factory: create the configured backend from LLMConfig, or None if disabled.

    Args:
        config: LLM configuration with backend, model, api_key, etc.

    Returns:
        Configured InferenceBackend instance, or None if disabled.
    """
    backend_id = config.backend
    if backend_id == DISABLED_BACKEND_ID:
        logger.info("LLM inference disabled")
        return None

    if backend_id not in KNOWN_BACKENDS:
        logger.warning(
            "Unknown LLM backend: %s (available: %s)", backend_id, sorted(KNOWN_BACKENDS)
        )
        return None

    if backend_id == LITELLM_BACKEND:
        return _create_litellm_backend(config.model, config)

    if backend_id in LEGACY_HTTP_ALIASES:
        provider = LEGACY_PROVIDER_MAP[backend_id]
        model = config.model
        # Prepend provider prefix if not already present
        if "/" not in model:
            model = f"{provider}/{model}"
            logger.info(
                "Legacy backend '%s': prepending provider prefix → model='%s'",
                backend_id,
                model,
            )
        return _create_litellm_backend(model, config)

    return _create_subprocess_backend(backend_id, config)


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


def _create_subprocess_backend(backend_id: str, config: LLMConfig) -> InferenceBackend:
    """Create a subprocess CLI backend instance.

    Args:
        backend_id: One of 'claude-cli' or 'codex-cli'.
        config: LLM configuration.

    Returns:
        Configured SubprocessBackend instance.
    """
    from vibelens.llm.backends.subprocess import SubprocessBackend
    from vibelens.models.inference import BackendType

    cli_name = "claude" if backend_id == "claude-cli" else "codex"
    bt = BackendType.CLAUDE_CLI if backend_id == "claude-cli" else BackendType.CODEX_CLI
    return SubprocessBackend(
        cli_name=cli_name,
        backend_type=bt,
        model=config.model or None,
        timeout=config.timeout,
    )
