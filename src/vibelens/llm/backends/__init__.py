"""Backend registry and factory for inference backends.

The create_backend_from_llm_config() factory reads LLMConfig and
instantiates the configured backend, or returns None if inference is disabled.
"""

from vibelens.config.llm_config import LLMConfig
from vibelens.llm.backend import InferenceBackend
from vibelens.models.inference import BackendType
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

CLI_BACKENDS = {BackendType.CLAUDE_CLI, BackendType.CODEX_CLI}
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
        return _create_litellm_backend(config.model, config)

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


def _create_subprocess_backend(backend_id: BackendType, config: LLMConfig) -> InferenceBackend:
    """Create a subprocess CLI backend instance.

    Args:
        backend_id: One of BackendType.CLAUDE_CLI or BackendType.CODEX_CLI.
        config: LLM configuration.

    Returns:
        Configured SubprocessBackend instance.
    """
    from vibelens.llm.backends.subprocess import SubprocessBackend

    cli_name = "claude" if backend_id == BackendType.CLAUDE_CLI else "codex"
    return SubprocessBackend(
        cli_name=cli_name,
        backend_type=backend_id,
        model=config.model or None,
        timeout=config.timeout,
    )
