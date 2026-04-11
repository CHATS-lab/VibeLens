"""Cost computation for steps and trajectories.

Bridges per-step token metrics with the pricing table in llm/pricing
to produce USD cost estimates.
"""

from typing import Optional

from vibelens.llm.pricing import TOKENS_PER_MTOK, lookup_pricing
from vibelens.models.trajectories.step import Step
from vibelens.models.trajectories.trajectory import Trajectory


def compute_cost_from_tokens(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> Optional[float]:
    """Compute estimated USD cost from aggregate token counts.

    Used by metadata-based dashboard stats to estimate cost without
    loading full trajectories.

    Args:
        model: Model name for pricing lookup.
        input_tokens: Total prompt tokens (includes cached).
        output_tokens: Total completion tokens.
        cache_read_tokens: Total tokens read from cache.
        cache_creation_tokens: Total tokens written to cache.

    Returns:
        Cost in USD or None if model is unrecognized.
    """
    pricing = lookup_pricing(model)
    if not pricing:
        return None
    non_cached_input = input_tokens - cache_read_tokens
    cost = (
        non_cached_input * pricing.input_per_mtok
        + cache_read_tokens * pricing.cached_input_per_mtok
        + cache_creation_tokens * pricing.cache_write_per_mtok
        + output_tokens * pricing.output_per_mtok
    ) / TOKENS_PER_MTOK
    return cost


def compute_step_cost(step: Step, session_model: Optional[str] = None) -> Optional[float]:
    """Compute the estimated USD cost for a single step.

    Uses step.model_name with fallback to session_model for pricing
    lookup. Returns None if no metrics or model is unrecognized.

    Formula:
        (prompt - cached) * input_rate
        + cached * cache_hit_rate
        + cache_creation * cache_write_rate
        + completion * output_rate

    Args:
        step: A conversation step with optional metrics.
        session_model: Fallback model name from the trajectory agent.

    Returns:
        Cost in USD or None if cost cannot be determined.
    """
    if not step.metrics:
        return None

    model = step.model_name or session_model
    pricing = lookup_pricing(model)
    if not pricing:
        return None

    m = step.metrics
    non_cached_input = m.prompt_tokens - m.cached_tokens

    cost = (
        non_cached_input * pricing.input_per_mtok
        + m.cached_tokens * pricing.cached_input_per_mtok
        + m.cache_creation_tokens * pricing.cache_write_per_mtok
        + m.completion_tokens * pricing.output_per_mtok
    ) / TOKENS_PER_MTOK
    return cost


def compute_trajectory_cost(trajectory: Trajectory) -> Optional[float]:
    """Compute the total estimated USD cost for a trajectory.

    Sums compute_step_cost() across all steps. Returns None if no
    steps have computable costs (e.g., all unknown models).

    Args:
        trajectory: A full trajectory with steps.

    Returns:
        Total cost in USD or None if no costs could be computed.
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
