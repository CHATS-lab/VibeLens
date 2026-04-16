"""Score-and-rank session sampling to fit within a token budget.

Scores each session by recency, richness (step count), and project diversity,
then greedily packs top-scored sessions until the budget is exhausted.
"""

import math
from datetime import datetime, timezone

from vibelens.models.context import SessionContext, SessionContextBatch
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Scoring weights for session sampling
RECENCY_WEIGHT = 0.4
RICHNESS_WEIGHT = 0.3
DIVERSITY_WEIGHT = 0.3
# Recency half-life in days (score halves every 30 days)
RECENCY_HALF_LIFE_DAYS = 30
# Max step count for richness normalization (prevents outlier distortion)
RICHNESS_STEP_CEILING = 200
# Approximate chars per token for budget estimation
CHARS_PER_TOKEN = 4
# Default token budget for sampling
DEFAULT_TOKEN_BUDGET = 100_000
# Sessions below this step count are typically false starts or one-shot
# queries with insufficient behavioral signal to guide skill recommendation.
MIN_STEPS_FOR_SAMPLING = 10


def sample_contexts(
    batch: SessionContextBatch,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    min_steps: int = MIN_STEPS_FOR_SAMPLING,
) -> SessionContextBatch:
    """Select a diverse, recent, high-quality subset of sessions within token budget.

    Filters out sessions below ``min_steps`` first (trivial / false-start
    sessions add noise without signal), then scores each remaining session
    by recency (0.4), richness (0.3), and project diversity (0.3), and
    greedily packs top-scored sessions until the token budget is exhausted.

    Args:
        batch: Full SessionContextBatch from extract_all_contexts.
        token_budget: Maximum tokens for the combined digest.
        min_steps: Minimum step count to qualify for sampling. Sessions below
            this threshold are moved to skipped_session_ids.

    Returns:
        New SessionContextBatch with sampled and re-indexed contexts.
    """
    if not batch.contexts:
        return batch

    eligible: list[SessionContext] = []
    step_filtered_ids: list[str] = []
    for ctx in batch.contexts:
        step_count = len(ctx.trajectory_group[0].steps) if ctx.trajectory_group else 0
        if step_count < min_steps:
            step_filtered_ids.append(ctx.session_id)
        else:
            eligible.append(ctx)

    if step_filtered_ids:
        logger.info(
            "Filtered %d/%d sessions below %d steps",
            len(step_filtered_ids),
            len(batch.contexts),
            min_steps,
        )

    skipped_ids = list(batch.skipped_session_ids) + step_filtered_ids

    if not eligible:
        return SessionContextBatch(
            contexts=[],
            session_ids=[],
            skipped_session_ids=skipped_ids,
        )

    estimated_total = sum(len(ctx.context_text) for ctx in eligible) // CHARS_PER_TOKEN
    if estimated_total <= token_budget:
        # Re-index eligible sessions so session_index reflects the filtered batch.
        for i, ctx in enumerate(eligible):
            ctx.reindex(i)
        return SessionContextBatch(
            contexts=eligible,
            session_ids=[ctx.session_id for ctx in eligible],
            skipped_session_ids=skipped_ids,
        )

    scores = _score_sessions(eligible)
    ranked = sorted(zip(eligible, scores, strict=True), key=lambda pair: pair[1], reverse=True)

    selected: list[SessionContext] = []
    running_chars = 0
    budget_chars = token_budget * CHARS_PER_TOKEN

    for ctx, _score in ranked:
        candidate_chars = running_chars + len(ctx.context_text)
        if candidate_chars > budget_chars:
            continue
        selected.append(ctx)
        running_chars = candidate_chars

    # Re-index selected sessions sequentially (updates both session_index and context_text)
    for i, ctx in enumerate(selected):
        ctx.reindex(i)

    logger.info(
        "Sampled %d/%d sessions (est. %d tokens within %d budget)",
        len(selected),
        len(eligible),
        running_chars // CHARS_PER_TOKEN,
        token_budget,
    )

    return SessionContextBatch(
        contexts=selected,
        session_ids=[ctx.session_id for ctx in selected],
        skipped_session_ids=skipped_ids,
    )


def _score_sessions(contexts: list[SessionContext]) -> list[float]:
    """Compute composite scores for session sampling.

    Args:
        contexts: List of SessionContext to score.

    Returns:
        List of float scores, same order as input.
    """
    now = datetime.now(timezone.utc)

    # Project frequency for diversity scoring
    project_counts: dict[str, int] = {}
    for ctx in contexts:
        key = ctx.project_path or "unknown"
        project_counts[key] = project_counts.get(key, 0) + 1

    # Step counts for richness scoring
    step_counts = [
        len(ctx.trajectory_group[0].steps) if ctx.trajectory_group else 0 for ctx in contexts
    ]
    max_steps = min(max(step_counts) if step_counts else 1, RICHNESS_STEP_CEILING)

    scores: list[float] = []
    for ctx, steps in zip(contexts, step_counts, strict=True):
        recency = _recency_score(ctx.timestamp, now)
        richness = min(steps, RICHNESS_STEP_CEILING) / max(max_steps, 1)
        diversity = 1.0 / project_counts.get(ctx.project_path or "unknown", 1)
        composite = (
            RECENCY_WEIGHT * recency + RICHNESS_WEIGHT * richness + DIVERSITY_WEIGHT * diversity
        )
        scores.append(composite)

    return scores


def _recency_score(timestamp: datetime | None, now: datetime) -> float:
    """Exponential decay score based on session age.

    Args:
        timestamp: Session timestamp (None returns 0).
        now: Current time for age calculation.

    Returns:
        Score between 0 and 1.
    """
    if timestamp is None:
        return 0.0
    age_days = max((now - timestamp).total_seconds() / 86400, 0)
    return math.exp(-age_days / RECENCY_HALF_LIFE_DAYS)
