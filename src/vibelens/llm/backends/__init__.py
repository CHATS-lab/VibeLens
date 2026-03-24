"""Backend registry and factory for inference backends.

The create_backend() factory reads settings and instantiates the
configured backend, or returns None if inference is disabled.
"""

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


def create_backend(settings) -> InferenceBackend | None:
    """Factory: create the configured backend, or None if disabled.

    Args:
        settings: Application settings with llm_* fields.

    Returns:
        Configured InferenceBackend instance, or None if disabled.
    """
    backend_id = settings.llm_backend
    if backend_id == DISABLED_BACKEND_ID:
        logger.info("LLM inference disabled")
        return None

    if backend_id not in KNOWN_BACKENDS:
        logger.warning(
            "Unknown LLM backend: %s (available: %s)", backend_id, sorted(KNOWN_BACKENDS)
        )
        return None

    if backend_id == LITELLM_BACKEND:
        return _create_litellm_backend(settings.llm_model, settings)

    if backend_id in LEGACY_HTTP_ALIASES:
        provider = LEGACY_PROVIDER_MAP[backend_id]
        model = settings.llm_model
        # Prepend provider prefix if not already present
        if "/" not in model:
            model = f"{provider}/{model}"
            logger.info(
                "Legacy backend '%s': prepending provider prefix → model='%s'",
                backend_id,
                model,
            )
        return _create_litellm_backend(model, settings)

    return _create_subprocess_backend(backend_id, settings)


def _create_litellm_backend(model: str, settings) -> InferenceBackend:
    """Create a LiteLLM backend instance.

    Args:
        model: Model name in litellm format (e.g. 'anthropic/claude-sonnet-4-5').
        settings: Application settings.

    Returns:
        Configured LiteLLMBackend instance.
    """
    from vibelens.llm.backends.litellm_backend import LiteLLMBackend

    return LiteLLMBackend(
        model=model,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout,
        max_tokens=settings.llm_max_tokens,
    )


def _create_subprocess_backend(backend_id: str, settings) -> InferenceBackend:
    """Create a subprocess CLI backend instance.

    Args:
        backend_id: One of 'claude-cli' or 'codex-cli'.
        settings: Application settings.

    Returns:
        Configured SubprocessBackend instance.
    """
    from vibelens.llm.backends.subprocess import SubprocessBackend

    cli_name = "claude" if backend_id == "claude-cli" else "codex"
    return SubprocessBackend(
        cli_name=cli_name,
        backend_type=backend_id,
        model=settings.llm_model or None,
        timeout=settings.llm_timeout,
    )
