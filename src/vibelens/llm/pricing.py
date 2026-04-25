"""LLM pricing lookup and trajectory cost computation.

Pricing comes from ``litellm.model_cost`` (a curated table of ~2700 models
maintained upstream by the LiteLLM project, refreshed on every package
release). New model versions land via ``uv lock`` bumping ``litellm``;
no hand-edit needed.

The local ``PRICING_OVERRIDES`` table is a tiny escape hatch for cases
where the LiteLLM data is wrong, missing, or doesn't capture a tier
nuance we want to model (e.g. Anthropic's 1M-context surcharge). Lookup
checks overrides first, then falls back to LiteLLM.

:func:`compute_step_cost` and :func:`compute_trajectory_cost` apply the
looked-up rates to token counts stored on :class:`Step` / :class:`Trajectory`.
They live here (not in ``services/dashboard/``) so ingest parsers can
populate :attr:`Step.metrics.cost_usd` without violating the
``llm → services`` layering.
"""

import litellm

from vibelens.llm.normalizer import normalize_model_name
from vibelens.models.llm.pricing import ModelPricing
from vibelens.models.trajectories.step import Step
from vibelens.models.trajectories.trajectory import Trajectory
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
    # Verified 2026-04-18 against ai.google.dev/gemini-api/docs/pricing
    # (Gemini 3 Pro is not publicly listed; only 3.1 Pro Preview exists.)
    "gemini-3.1-pro": _mp(2.00, 12.00, 0.20, 2.00),
    # DeepSeek — verified 2026-04-18 against api-docs.deepseek.com/quick_start/pricing
    # v3 and v3.2 share the deepseek-chat rate.
    "deepseek-v3": _mp(0.28, 0.42, 0.028, 0.28),
    "deepseek-v3.2": _mp(0.28, 0.42, 0.028, 0.28),
    # Moonshot Kimi — verified 2026-04-18 against platform.kimi.com/docs/pricing/chat-k2,
    # chat-k25. K2 family unified pricing; K2.5 has higher output rate.
    "kimi-k2": _mp(0.556, 2.222, 0.139, 0.556),
    "kimi-k2-0905": _mp(0.556, 2.222, 0.139, 0.556),
    "kimi-k2-thinking": _mp(0.556, 2.222, 0.139, 0.556),
    "kimi-k2.5": _mp(0.556, 2.917, 0.097, 0.556),
    # MiniMax — unverified 2026-04-18 (pricing portal moved/JS-rendered).
    "minimax-m2.5": _mp(0.30, 1.20, 0.03, 0.375),
    "minimax-m2.7": _mp(0.30, 1.20, 0.06, 0.375),
    # Qwen (Alibaba Cloud) — verified 2026-04-18 against help.aliyun.com/zh/model-studio.
    # qwen3-max uses tier-based pricing; we quote the standard ≤32K tier.
    # qwen3.5-plus and qwen3-coder-next not verified (page only listed -plus variants).
    "qwen3-max": _mp(0.35, 1.39, 0.07, 0.35),
    "qwen3.5-plus": _mp(0.26, 1.56, 0.26, 0.26),
    "qwen3-coder-next": _mp(0.12, 0.75, 0.06, 0.12),
    # Zhipu GLM — unverified 2026-04-18 (open.bigmodel.cn loaded JS-only page).
    "glm-5": _mp(1.00, 3.20, 0.20, 1.00),
    "glm-5-code": _mp(1.20, 5.00, 0.30, 1.20),
    "glm-4.7": _mp(0.60, 2.20, 0.11, 0.60),
    "glm-4.7-flashx": _mp(0.07, 0.40, 0.01, 0.07),
    # ByteDance Seed (Doubao) — unverified 2026-04-18 (volcengine.com docs returned empty).
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


def compute_cost_from_tokens(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float | None:
    """Compute estimated USD cost from aggregate token counts.

    Used by metadata-based dashboard stats to estimate cost without
    loading full trajectories.
    """
    pricing = lookup_pricing(model)
    if not pricing:
        return None
    non_cached_input = max(0, input_tokens - cache_read_tokens)
    return (
        non_cached_input * pricing.input_per_mtok
        + cache_read_tokens * pricing.cache_read_per_mtok
        + cache_write_tokens * pricing.cache_write_per_mtok
        + output_tokens * pricing.output_per_mtok
    ) / TOKENS_PER_MTOK


def compute_step_cost(step: Step, session_model: str | None = None) -> float | None:
    """Compute the estimated USD cost for a single step.

    Uses ``step.model_name`` with fallback to ``session_model`` for pricing
    lookup. Returns ``None`` when the step has no metrics or the model is
    unrecognized.

    Formula:
        (prompt - cached) * input_rate
        + cached * cache_hit_rate
        + cache_creation * cache_write_rate
        + completion * output_rate
    """
    if not step.metrics:
        return None

    model = step.model_name or session_model
    pricing = lookup_pricing(model)
    if not pricing:
        return None

    metrics = step.metrics
    non_cached_input = max(0, metrics.prompt_tokens - metrics.cache_read_tokens)
    return (
        non_cached_input * pricing.input_per_mtok
        + metrics.cache_read_tokens * pricing.cache_read_per_mtok
        + metrics.cache_write_tokens * pricing.cache_write_per_mtok
        + metrics.completion_tokens * pricing.output_per_mtok
    ) / TOKENS_PER_MTOK


def compute_trajectory_cost(trajectory: Trajectory) -> float | None:
    """Compute the total estimated USD cost for a trajectory.

    Sums :func:`compute_step_cost` across all steps. Returns ``None``
    when no step has a computable cost (e.g. every model is unknown).
    """
    session_model = trajectory.agent.model_name if trajectory.agent else None
    total = 0.0
    has_any_cost = False
    for step in trajectory.steps:
        step_cost = compute_step_cost(step, session_model)
        if step_cost is not None:
            total += step_cost
            has_any_cost = True
    return total if has_any_cost else None
