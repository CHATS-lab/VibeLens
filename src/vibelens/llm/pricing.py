"""LLM pricing lookup.

Pricing comes from ``litellm.model_cost`` (a curated table of ~2700 models
maintained upstream by the LiteLLM project, refreshed on every package
release). New model versions land via ``uv lock`` bumping ``litellm``;
no hand-edit needed.

The local ``PRICING_OVERRIDES`` table is a tiny escape hatch for cases
where the LiteLLM data is wrong, missing, or doesn't capture a tier
nuance we want to model (e.g. Anthropic's 1M-context surcharge). Lookup
checks overrides first, then falls back to LiteLLM.

Cost computation that operates on trajectory models lives in
``vibelens.services.dashboard.pricing``.
"""

import litellm

from vibelens.llm.normalizer import normalize_model_name
from vibelens.models.llm.pricing import ModelPricing
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Divisor to convert token counts to the "per million" unit used in pricing.
TOKENS_PER_MTOK = 1_000_000

# Local overrides — populate only when LiteLLM is wrong or missing a model.
# LiteLLM covers Anthropic, OpenAI, and Google ≤2.5 directly; non-Western
# providers (DeepSeek, Moonshot, MiniMax, Qwen, Zhipu, ByteDance) are only
# present under provider-prefixed keys, and recent Gemini 3.x is preview-only.
# Add overrides here for the bare canonical names our session metadata uses.
#
# Sources (verify before editing):
#   Google   — https://ai.google.dev/gemini-api/docs/pricing
#   DeepSeek — https://api-docs.deepseek.com/quick_start/pricing
#   Moonshot — https://platform.moonshot.cn/docs/pricing
#   MiniMax  — https://platform.minimaxi.com/document/Price
#   Qwen     — https://help.aliyun.com/model-studio/models
#   Zhipu    — https://open.bigmodel.cn/pricing
#   ByteDance— https://www.volcengine.com/docs/82379/1263482
def _mp(input_: float, output: float, cache_read: float, cache_write: float) -> ModelPricing:
    """Compact constructor — overrides are dense; keep them readable."""
    return ModelPricing(
        input_per_mtok=input_,
        output_per_mtok=output,
        cache_read_per_mtok=cache_read,
        cache_write_per_mtok=cache_write,
    )


PRICING_OVERRIDES: dict[str, ModelPricing] = {
    # Google Gemini 3.x — LiteLLM only ships preview keys.
    "gemini-3-pro": _mp(2.00, 12.00, 0.20, 2.00),
    "gemini-3.1-pro": _mp(2.00, 12.00, 0.20, 2.00),
    # DeepSeek
    "deepseek-v3": _mp(0.28, 0.42, 0.028, 0.28),
    "deepseek-v3.2": _mp(0.27, 0.41, 0.027, 0.27),
    "deepseek-chat": _mp(0.32, 0.89, 0.032, 0.32),
    # Moonshot Kimi
    "kimi-k2": _mp(0.60, 2.50, 0.15, 0.60),
    "kimi-k2-0905": _mp(0.40, 2.00, 0.10, 0.40),
    "kimi-k2-thinking": _mp(0.60, 2.50, 0.15, 0.60),
    "kimi-k2.5": _mp(0.45, 2.20, 0.225, 0.45),
    # MiniMax
    "minimax-m2.5": _mp(0.30, 1.20, 0.03, 0.375),
    "minimax-m2.7": _mp(0.30, 1.20, 0.06, 0.375),
    # Qwen (Alibaba Cloud)
    "qwen3-max": _mp(0.78, 3.90, 0.156, 0.78),
    "qwen3.5-plus": _mp(0.26, 1.56, 0.26, 0.26),
    "qwen3-coder-next": _mp(0.12, 0.75, 0.06, 0.12),
    # Zhipu GLM
    "glm-5": _mp(1.00, 3.20, 0.20, 1.00),
    "glm-5-code": _mp(1.20, 5.00, 0.30, 1.20),
    "glm-4.7": _mp(0.60, 2.20, 0.11, 0.60),
    "glm-4.7-flashx": _mp(0.07, 0.40, 0.01, 0.07),
    # ByteDance Seed (Doubao)
    "seed-2.0-pro": _mp(0.47, 2.37, 0.47, 0.47),
    "seed-2.0-lite": _mp(0.09, 0.53, 0.09, 0.09),
    "seed-2.0-mini": _mp(0.03, 0.31, 0.03, 0.03),
    "seed-2.0-code": _mp(0.47, 2.37, 0.47, 0.47),
    # Mistral — bare canonical names; LiteLLM only stores versioned/-latest forms.
    "mistral-large": _mp(0.50, 1.50, 0.05, 0.50),
    "mistral-medium-3.1": _mp(0.40, 2.00, 0.04, 0.40),
    "mistral-small-4": _mp(0.15, 0.60, 0.015, 0.15),
    "magistral-medium": _mp(2.00, 5.00, 2.00, 2.00),
    "codestral": _mp(0.30, 0.90, 0.03, 0.30),
    # Meta Llama 4 — hosted pricing varies by provider; rates approximate Together.
    "llama-4-maverick": _mp(0.15, 0.60, 0.15, 0.15),
    "llama-4-scout": _mp(0.08, 0.30, 0.08, 0.08),
}

# session_id -> True for models we've already warned about; keeps the log
# from spamming "no pricing for X" once per request.
_warned_models: set[str] = set()


def lookup_pricing(model_name: str | None) -> ModelPricing | None:
    """Return per-million-token pricing for ``model_name``, or None.

    Lookup order:
        1. ``PRICING_OVERRIDES`` for the raw model name.
        2. ``PRICING_OVERRIDES`` for the normalized canonical form.
        3. ``litellm.model_cost`` for the raw model name.
        4. ``litellm.model_cost`` for the normalized canonical form.

    On a miss, logs once per model and returns ``None``.

    Args:
        model_name: Raw model id from session metadata (e.g.
            ``"claude-opus-4-7-20260101"``, ``"anthropic/claude-haiku-4-5"``).

    Returns:
        ModelPricing or ``None`` if no pricing is known.
    """
    if not model_name:
        return None

    if model_name in PRICING_OVERRIDES:
        return PRICING_OVERRIDES[model_name]

    canonical = normalize_model_name(model_name)
    if canonical and canonical in PRICING_OVERRIDES:
        return PRICING_OVERRIDES[canonical]

    pricing = _from_litellm(model_name) or (_from_litellm(canonical) if canonical else None)
    if pricing is not None:
        return pricing

    if model_name not in _warned_models:
        _warned_models.add(model_name)
        logger.info(
            "No pricing for model %r (canonical: %r); cost will be 0.",
            model_name,
            canonical,
        )
    return None


# LiteLLM keys are sometimes provider-prefixed (e.g. ``xai/grok-4``,
# ``anthropic/claude-...``) for first-party rates. Try these prefixes in
# order when the bare name misses; the first match wins.
_LITELLM_PROVIDER_PREFIXES: tuple[str, ...] = (
    "anthropic/",
    "xai/",
    "openai/",
    "mistral/",
    "vertex_ai/",
    "fireworks_ai/",
    "together_ai/",
)


def _from_litellm(model_name: str) -> ModelPricing | None:
    """Build a ModelPricing from litellm.model_cost if the entry is usable.

    Tries the bare ``model_name`` first, then each entry in
    ``_LITELLM_PROVIDER_PREFIXES`` to cover keys LiteLLM only stores
    under provider-prefixed forms.
    """
    candidates = [model_name] + [prefix + model_name for prefix in _LITELLM_PROVIDER_PREFIXES]
    for key in candidates:
        info = litellm.model_cost.get(key)
        if not info or not isinstance(info, dict):
            continue
        if "input_cost_per_token" not in info or "output_cost_per_token" not in info:
            continue
        input_per_token = info["input_cost_per_token"]
        output_per_token = info["output_cost_per_token"]
        # LiteLLM sometimes stores explicit ``None`` for cache fields when
        # the model doesn't support caching; fall back to the input rate.
        cache_read = info.get("cache_read_input_token_cost") or input_per_token
        cache_write = info.get("cache_creation_input_token_cost") or input_per_token
        return ModelPricing(
            input_per_mtok=input_per_token * TOKENS_PER_MTOK,
            output_per_mtok=output_per_token * TOKENS_PER_MTOK,
            cache_read_per_mtok=cache_read * TOKENS_PER_MTOK,
            cache_write_per_mtok=cache_write * TOKENS_PER_MTOK,
        )
    return None
