"""LLM pricing table and lookup.

Per-million-token rates for supported models, plus a lookup function
that bridges model name normalization with the pricing table.

Cost computation that operates on trajectory models lives in
vibelens.analysis.pricing.
"""

from vibelens.llm.normalizer import normalize_model_name
from vibelens.models.analysis.pricing import ModelPricing

TOKENS_PER_MTOK = 1_000_000

# Prices are USD per million tokens.
# Sources:
#   Anthropic — https://platform.claude.com/docs/en/about-claude/pricing
#   OpenAI   — https://openai.com/api/pricing/
#   Google   — https://ai.google.dev/gemini-api/docs/pricing
#   xAI      — https://docs.x.ai/docs/models#models-and-pricing
#   DeepSeek — https://api-docs.deepseek.com/quick_start/pricing
#   Mistral  — https://mistral.ai/products/pricing
#   Qwen     — https://help.aliyun.com/model-studio/models
#   Moonshot — https://platform.moonshot.cn/docs/pricing
#   MiniMax  — https://platform.minimaxi.com/document/Price
#   Zhipu    — https://open.bigmodel.cn/pricing
#   ByteDance— https://www.volcengine.com/docs/82379/1263482
#   Meta     — via Together/Fireworks hosted pricing
PRICING_TABLE: dict[str, ModelPricing] = {
    # Anthropic
    "claude-opus-4-6": ModelPricing(
        input_per_mtok=5.00,
        output_per_mtok=25.00,
        cached_input_per_mtok=0.50,
        cache_write_per_mtok=6.25,
    ),
    "claude-opus-4-1": ModelPricing(
        input_per_mtok=15.00,
        output_per_mtok=75.00,
        cached_input_per_mtok=1.50,
        cache_write_per_mtok=18.75,
    ),
    "claude-sonnet-4-6": ModelPricing(
        input_per_mtok=3.00,
        output_per_mtok=15.00,
        cached_input_per_mtok=0.30,
        cache_write_per_mtok=3.75,
    ),
    "claude-sonnet-4-5": ModelPricing(
        input_per_mtok=3.00,
        output_per_mtok=15.00,
        cached_input_per_mtok=0.30,
        cache_write_per_mtok=3.75,
    ),
    "claude-3-5-sonnet": ModelPricing(
        input_per_mtok=3.00,
        output_per_mtok=15.00,
        cached_input_per_mtok=0.30,
        cache_write_per_mtok=3.75,
    ),
    "claude-haiku-4-5": ModelPricing(
        input_per_mtok=1.00,
        output_per_mtok=5.00,
        cached_input_per_mtok=0.10,
        cache_write_per_mtok=1.25,
    ),
    "claude-3-5-haiku": ModelPricing(
        input_per_mtok=0.80,
        output_per_mtok=4.00,
        cached_input_per_mtok=0.08,
        cache_write_per_mtok=1.00,
    ),
    # OpenAI (cache_write = input rate; auto-caching has no write surcharge)
    "gpt-5.4-pro": ModelPricing(
        input_per_mtok=30.00,
        output_per_mtok=180.00,
        cached_input_per_mtok=3.00,
        cache_write_per_mtok=30.00,
    ),
    "gpt-5.4": ModelPricing(
        input_per_mtok=2.50,
        output_per_mtok=15.00,
        cached_input_per_mtok=0.25,
        cache_write_per_mtok=2.50,
    ),
    "gpt-5.4-mini": ModelPricing(
        input_per_mtok=0.75,
        output_per_mtok=4.50,
        cached_input_per_mtok=0.075,
        cache_write_per_mtok=0.75,
    ),
    "gpt-5.4-nano": ModelPricing(
        input_per_mtok=0.20,
        output_per_mtok=1.25,
        cached_input_per_mtok=0.02,
        cache_write_per_mtok=0.20,
    ),
    "o3-pro": ModelPricing(
        input_per_mtok=20.00,
        output_per_mtok=80.00,
        cached_input_per_mtok=5.00,
        cache_write_per_mtok=20.00,
    ),
    "o3": ModelPricing(
        input_per_mtok=2.00,
        output_per_mtok=8.00,
        cached_input_per_mtok=0.50,
        cache_write_per_mtok=2.00,
    ),
    "o4-mini": ModelPricing(
        input_per_mtok=1.10,
        output_per_mtok=4.40,
        cached_input_per_mtok=0.275,
        cache_write_per_mtok=1.10,
    ),
    "gpt-4.1": ModelPricing(
        input_per_mtok=2.00,
        output_per_mtok=8.00,
        cached_input_per_mtok=0.50,
        cache_write_per_mtok=2.00,
    ),
    "gpt-4.1-mini": ModelPricing(
        input_per_mtok=0.40,
        output_per_mtok=1.60,
        cached_input_per_mtok=0.10,
        cache_write_per_mtok=0.40,
    ),
    "gpt-4.1-nano": ModelPricing(
        input_per_mtok=0.10,
        output_per_mtok=0.40,
        cached_input_per_mtok=0.025,
        cache_write_per_mtok=0.10,
    ),
    # Google Gemini (<=200k context pricing; cache_write = input rate)
    "gemini-3.1-pro": ModelPricing(
        input_per_mtok=2.00,
        output_per_mtok=12.00,
        cached_input_per_mtok=0.20,
        cache_write_per_mtok=2.00,
    ),
    "gemini-2.5-pro": ModelPricing(
        input_per_mtok=1.25,
        output_per_mtok=10.00,
        cached_input_per_mtok=0.125,
        cache_write_per_mtok=1.25,
    ),
    "gemini-2.5-flash": ModelPricing(
        input_per_mtok=0.30,
        output_per_mtok=2.50,
        cached_input_per_mtok=0.03,
        cache_write_per_mtok=0.30,
    ),
    "gemini-2.5-flash-lite": ModelPricing(
        input_per_mtok=0.10,
        output_per_mtok=0.40,
        cached_input_per_mtok=0.01,
        cache_write_per_mtok=0.10,
    ),
    "gemini-2.0-flash": ModelPricing(
        input_per_mtok=0.10,
        output_per_mtok=0.40,
        cached_input_per_mtok=0.025,
        cache_write_per_mtok=0.10,
    ),
    # xAI Grok
    "grok-4.20-beta": ModelPricing(
        input_per_mtok=2.00,
        output_per_mtok=6.00,
        cached_input_per_mtok=0.20,
        cache_write_per_mtok=2.00,
    ),
    "grok-4": ModelPricing(
        input_per_mtok=3.00,
        output_per_mtok=15.00,
        cached_input_per_mtok=0.75,
        cache_write_per_mtok=3.00,
    ),
    "grok-4.1-fast": ModelPricing(
        input_per_mtok=0.20,
        output_per_mtok=0.50,
        cached_input_per_mtok=0.05,
        cache_write_per_mtok=0.20,
    ),
    # DeepSeek
    "deepseek-v3": ModelPricing(
        input_per_mtok=0.28,
        output_per_mtok=0.42,
        cached_input_per_mtok=0.028,
        cache_write_per_mtok=0.28,
    ),
    # Mistral
    "magistral-medium": ModelPricing(
        input_per_mtok=2.00,
        output_per_mtok=5.00,
        cached_input_per_mtok=2.00,
        cache_write_per_mtok=2.00,
    ),
    "mistral-large": ModelPricing(
        input_per_mtok=0.50,
        output_per_mtok=1.50,
        cached_input_per_mtok=0.05,
        cache_write_per_mtok=0.50,
    ),
    "mistral-medium-3.1": ModelPricing(
        input_per_mtok=0.40,
        output_per_mtok=2.00,
        cached_input_per_mtok=0.04,
        cache_write_per_mtok=0.40,
    ),
    "codestral": ModelPricing(
        input_per_mtok=0.30,
        output_per_mtok=0.90,
        cached_input_per_mtok=0.03,
        cache_write_per_mtok=0.30,
    ),
    "mistral-small-4": ModelPricing(
        input_per_mtok=0.15,
        output_per_mtok=0.60,
        cached_input_per_mtok=0.015,
        cache_write_per_mtok=0.15,
    ),
    # Qwen (Alibaba Cloud)
    "qwen3-max": ModelPricing(
        input_per_mtok=0.78,
        output_per_mtok=3.90,
        cached_input_per_mtok=0.156,
        cache_write_per_mtok=0.78,
    ),
    "qwen3.5-plus": ModelPricing(
        input_per_mtok=0.26,
        output_per_mtok=1.56,
        cached_input_per_mtok=0.26,
        cache_write_per_mtok=0.26,
    ),
    "qwen3-coder-next": ModelPricing(
        input_per_mtok=0.12,
        output_per_mtok=0.75,
        cached_input_per_mtok=0.06,
        cache_write_per_mtok=0.12,
    ),
    # Moonshot Kimi
    "kimi-k2.5": ModelPricing(
        input_per_mtok=0.45,
        output_per_mtok=2.20,
        cached_input_per_mtok=0.225,
        cache_write_per_mtok=0.45,
    ),
    "kimi-k2": ModelPricing(
        input_per_mtok=0.60,
        output_per_mtok=2.50,
        cached_input_per_mtok=0.15,
        cache_write_per_mtok=0.60,
    ),
    # MiniMax
    "minimax-m2.5": ModelPricing(
        input_per_mtok=0.30,
        output_per_mtok=1.20,
        cached_input_per_mtok=0.03,
        cache_write_per_mtok=0.375,
    ),
    "minimax-m2.7": ModelPricing(
        input_per_mtok=0.30,
        output_per_mtok=1.20,
        cached_input_per_mtok=0.06,
        cache_write_per_mtok=0.375,
    ),
    # Zhipu GLM
    "glm-5": ModelPricing(
        input_per_mtok=1.00,
        output_per_mtok=3.20,
        cached_input_per_mtok=0.20,
        cache_write_per_mtok=1.00,
    ),
    "glm-5-code": ModelPricing(
        input_per_mtok=1.20,
        output_per_mtok=5.00,
        cached_input_per_mtok=0.30,
        cache_write_per_mtok=1.20,
    ),
    "glm-4.7": ModelPricing(
        input_per_mtok=0.60,
        output_per_mtok=2.20,
        cached_input_per_mtok=0.11,
        cache_write_per_mtok=0.60,
    ),
    "glm-4.7-flashx": ModelPricing(
        input_per_mtok=0.07,
        output_per_mtok=0.40,
        cached_input_per_mtok=0.01,
        cache_write_per_mtok=0.07,
    ),
    # ByteDance Seed
    "seed-2.0-pro": ModelPricing(
        input_per_mtok=0.47,
        output_per_mtok=2.37,
        cached_input_per_mtok=0.47,
        cache_write_per_mtok=0.47,
    ),
    "seed-2.0-lite": ModelPricing(
        input_per_mtok=0.09,
        output_per_mtok=0.53,
        cached_input_per_mtok=0.09,
        cache_write_per_mtok=0.09,
    ),
    "seed-2.0-mini": ModelPricing(
        input_per_mtok=0.03,
        output_per_mtok=0.31,
        cached_input_per_mtok=0.03,
        cache_write_per_mtok=0.03,
    ),
    "seed-2.0-code": ModelPricing(
        input_per_mtok=0.47,
        output_per_mtok=2.37,
        cached_input_per_mtok=0.47,
        cache_write_per_mtok=0.47,
    ),
    # Meta Llama 4 (hosted pricing via Together/Fireworks)
    "llama-4-maverick": ModelPricing(
        input_per_mtok=0.15,
        output_per_mtok=0.60,
        cached_input_per_mtok=0.15,
        cache_write_per_mtok=0.15,
    ),
    "llama-4-scout": ModelPricing(
        input_per_mtok=0.08,
        output_per_mtok=0.30,
        cached_input_per_mtok=0.08,
        cache_write_per_mtok=0.08,
    ),
}


def lookup_pricing(model_name: str | None) -> ModelPricing | None:
    """Look up pricing for a model name.

    Tries exact match in PRICING_TABLE first, then normalizes.

    Args:
        model_name: Model name (raw or canonical).

    Returns:
        ModelPricing or None if model is unrecognized.
    """
    if not model_name:
        return None

    pricing = PRICING_TABLE.get(model_name)
    if pricing:
        return pricing

    canonical = normalize_model_name(model_name)
    if canonical:
        return PRICING_TABLE.get(canonical)

    return None
