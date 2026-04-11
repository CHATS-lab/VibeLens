"""Pre-flight cost estimation for LLM inference.

Estimates the cost of an analysis run before calling the LLM,
using the pricing table and token counts from session batches.

Estimation formula per batch:
  input_cost  = (system_tokens + user_tokens) × input_rate / 1M
  output_cost = max_output_tokens × output_rate / 1M
  batch_cost  = input_cost + output_cost

Total estimated cost = sum(batch_costs) + synthesis_cost (if >1 batch).

Output tokens use the configured max_tokens as a pessimistic upper bound.
Actual cost will typically be 30-60% of the estimate since LLMs rarely
produce max_tokens of output.
"""

from dataclasses import dataclass

from vibelens.llm.pricing import TOKENS_PER_MTOK, lookup_pricing
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.llm.pricing import ModelPricing
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Assumed input tokens for the synthesis step (batch summaries are small)
SYNTHESIS_INPUT_TOKENS_ESTIMATE = 2000

# Output ratio bounds — LLMs rarely produce max_tokens of output.
# Min: optimistic (short, concise replies). Max: pessimistic (verbose output).
OUTPUT_RATIO_MIN = 0.25
OUTPUT_RATIO_MAX = 0.6


@dataclass(frozen=True)
class CostEstimate:
    """Pre-flight cost estimate for an analysis run."""

    model: str
    batch_count: int
    total_input_tokens: int
    total_output_tokens_budget: int
    cost_min_usd: float
    cost_max_usd: float
    pricing_found: bool

    @property
    def estimated_cost_usd(self) -> float:
        """Midpoint of the cost range for backward compatibility."""
        return round((self.cost_min_usd + self.cost_max_usd) / 2, 6)

    @property
    def formatted_cost(self) -> str:
        """Human-readable cost range string."""
        if not self.pricing_found:
            return "unknown (model not in pricing table)"
        return f"${self._fmt(self.cost_min_usd)} – ${self._fmt(self.cost_max_usd)}"

    @staticmethod
    def _fmt(value: float) -> str:
        """Format a dollar amount with appropriate precision."""
        if value < 0.01:
            return f"{value:.4f}"
        return f"{value:.2f}"


def estimate_analysis_cost(
    batch_token_counts: list[int],
    system_prompt: str,
    model: str,
    max_output_tokens: int,
    synthesis_output_tokens: int,
    synthesis_threshold: int = 1,
    extra_calls: list[tuple[int, int]] | None = None,
) -> CostEstimate:
    """Estimate cost for an LLM analysis pipeline.

    Covers batch inference, optional synthesis, and optional extra calls
    (e.g. deep generation/edit steps in multi-phase pipelines).

    Args:
        batch_token_counts: Token count of user prompt content per batch.
        system_prompt: System prompt text (shared across batches).
        model: Model name (e.g. "anthropic/claude-haiku-4-5").
        max_output_tokens: Max output tokens per batch call.
        synthesis_output_tokens: Max output tokens for synthesis call.
        synthesis_threshold: Synthesis added when batch_count > this value.
            Friction uses 0 (always synthesize), skill modes use 1.
        extra_calls: Additional LLM calls beyond batch+synthesis, as
            (input_tokens, output_budget) tuples. Used for deep generation
            or edit steps whose count is estimated upfront.

    Returns:
        CostEstimate with projected cost range.
    """
    pricing = lookup_pricing(model)
    system_tokens = count_tokens(system_prompt)
    batch_count = len(batch_token_counts)

    total_input = 0
    total_output_budget = 0

    for user_tokens in batch_token_counts:
        total_input += system_tokens + user_tokens
        total_output_budget += max_output_tokens

    if batch_count > synthesis_threshold:
        total_input += system_tokens + SYNTHESIS_INPUT_TOKENS_ESTIMATE
        total_output_budget += synthesis_output_tokens

    for extra_input, extra_output in extra_calls or []:
        total_input += extra_input
        total_output_budget += extra_output

    cost_min = _compute_cost(pricing, total_input, total_output_budget, OUTPUT_RATIO_MIN)
    cost_max = _compute_cost(pricing, total_input, total_output_budget, OUTPUT_RATIO_MAX)

    estimate = CostEstimate(
        model=model,
        batch_count=batch_count,
        total_input_tokens=total_input,
        total_output_tokens_budget=total_output_budget,
        cost_min_usd=cost_min,
        cost_max_usd=cost_max,
        pricing_found=pricing is not None,
    )

    logger.info(
        "Cost estimate: %d batches, %d input tokens, %d output budget → %s",
        batch_count,
        total_input,
        total_output_budget,
        estimate.formatted_cost,
    )
    return estimate



def _compute_cost(
    pricing: ModelPricing | None,
    total_input_tokens: int,
    total_output_budget: int,
    output_ratio: float,
) -> float:
    """Compute estimated USD cost from token counts, pricing, and output ratio.

    Args:
        pricing: Model pricing rates (None if model unknown).
        total_input_tokens: Total input tokens across all calls.
        total_output_budget: Total max_output_tokens across all calls.
        output_ratio: Fraction of output budget expected to be used.

    Returns:
        Estimated cost in USD. Returns 0.0 if pricing is unknown.
    """
    if not pricing:
        return 0.0

    input_cost = total_input_tokens * pricing.input_per_mtok / TOKENS_PER_MTOK
    expected_output = int(total_output_budget * output_ratio)
    output_cost = expected_output * pricing.output_per_mtok / TOKENS_PER_MTOK
    return round(input_cost + output_cost, 6)
