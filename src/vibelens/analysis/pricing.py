"""Model pricing data, name normalization, and cost computation.

Facade module: re-exports pricing data and name normalization from
sub-modules for backward compatibility. Cost computation functions
are defined here.
"""

from vibelens.llm.normalizer import normalize_model_name
from vibelens.llm.pricing import PRICING_TABLE, TOKENS_PER_MTOK, lookup_pricing
from vibelens.models.analysis.pricing import ModelPricing
from vibelens.models.trajectories.step import Step
from vibelens.models.trajectories.trajectory import Trajectory

__all__ = [
    "ModelPricing",
    "PRICING_TABLE",
    "TOKENS_PER_MTOK",
    "compute_step_cost",
    "compute_trajectory_cost",
    "lookup_pricing",
    "normalize_model_name",
]


def compute_step_cost(step: Step, session_model: str | None = None) -> float | None:
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


def compute_trajectory_cost(trajectory: Trajectory) -> float | None:
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
