"""LLM provider URL registry and provider-name detection.

Provider-specific helpers that don't belong in the config model itself.
The config model (InferenceConfig) lives in settings.py.
"""

from vibelens.config.settings import InferenceConfig

PROVIDER_BASE_URLS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "openrouter": "https://openrouter.ai/api/v1",
    "mistral": "https://api.mistral.ai/v1",
    "groq": "https://api.groq.com/openai/v1",
    "deepseek": "https://api.deepseek.com",
    "minimax": "https://api.minimax.chat/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
}

# Aliases litellm uses for providers that we collapse into canonical family names.
_PROVIDER_ALIASES: dict[str, str] = {
    "bedrock": "anthropic",
    "azure": "openai",
    "azure_text": "openai",
    "vertex_ai": "google",
    "vertex_ai_beta": "google",
    "gemini": "google",
}

# Bare model-name prefixes that identify a provider when the model has no
# slash prefix and litellm cannot resolve it (e.g. 'claude-haiku-4-5').
_BARE_MODEL_PREFIXES: dict[str, str] = {
    "claude-": "anthropic",
    "gpt-": "openai",
    "o1-": "openai",
    "o3-": "openai",
    "gemini-": "google",
    "kimi-": "moonshotai",
    "grok-": "x-ai",
    "deepseek-": "deepseek",
    "mistral-": "mistral",
    "qwen-": "qwen",
}

API_KEY_MASK_SUFFIX_LEN = 4
API_KEY_MASK = "***"


def resolve_base_url(config: InferenceConfig) -> str | None:
    """Resolve base URL from config or provider registry.

    If ``config.base_url`` is set, returns it. Otherwise extracts the
    provider prefix from the model name and looks up PROVIDER_BASE_URLS.

    Args:
        config: Inference configuration.

    Returns:
        Resolved base URL, or None if provider is unknown.
    """
    if config.base_url:
        return config.base_url
    if "/" not in config.model:
        return None
    provider = config.model.split("/", 1)[0].lower()
    return PROVIDER_BASE_URLS.get(provider)


def detect_provider(model: str) -> str:
    """Detect the LLM provider family from a model name.

    Resolution order:
      1. ``litellm.get_llm_provider`` for accurate routing-table lookup.
      2. ``openrouter/<provider>/...`` — extract the nested provider.
      3. Slash-prefixed names (``anthropic/claude-...`` → ``anthropic``).
      4. Bare model names matched against ``_BARE_MODEL_PREFIXES``.

    Args:
        model: Model name, possibly with provider prefix.

    Returns:
        Normalized provider string (e.g. ``"anthropic"``, ``"openai"``,
        ``"google"``, ``"deepseek"``), or ``"unknown"``.
    """
    try:
        import litellm

        _, provider, _, _ = litellm.get_llm_provider(model)
        return _PROVIDER_ALIASES.get(provider, provider)
    except Exception:  # noqa: BLE001 - litellm raises many exception types for unknown models
        pass

    if "/" in model:
        parts = model.split("/")
        top = parts[0].lower()
        if top == "openrouter" and len(parts) >= 2:
            return parts[1].lower()
        return top

    lower = model.lower()
    for prefix, provider in _BARE_MODEL_PREFIXES.items():
        if lower.startswith(prefix):
            return provider
    return "unknown"


def mask_api_key(api_key: str) -> str:
    """Mask an API key for display, preserving the last 4 chars."""
    if not api_key or len(api_key) <= API_KEY_MASK_SUFFIX_LEN:
        return API_KEY_MASK
    return f"{API_KEY_MASK}{api_key[-API_KEY_MASK_SUFFIX_LEN:]}"
