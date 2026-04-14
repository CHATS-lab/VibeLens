"""Shared infrastructure for LLM-powered analysis services.

Consolidates functions duplicated across friction, skill, and insight
analysis modules: backend retrieval, session context extraction, caching,
and log persistence.
"""

import asyncio
import json
import math
from collections.abc import Coroutine
from datetime import datetime, timezone
from pathlib import Path

from vibelens.context import ContextExtractor, DetailExtractor
from vibelens.deps import get_inference_backend
from vibelens.llm.backend import InferenceBackend, InferenceError
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.context import SessionContext, SessionContextBatch
from vibelens.models.llm.inference import BackendType
from vibelens.models.llm.prompts import AnalysisPrompt
from vibelens.services.session.store_resolver import (
    get_metadata_from_stores,
    load_from_stores,
)
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Time-to-live for analysis result caches (1 hour)
CACHE_TTL_SECONDS = 3600
# Maximum entries in each analysis result cache
CACHE_MAXSIZE = 64
# Instructions appended to system prompts when using CLI backends
CLI_BACKEND_RULES = """
## Backend Rules

You are running as a headless analysis backend. Follow these rules strictly:

1. Output ONLY a single JSON object. No markdown fences, no prose, no explanation.
2. Do NOT use any tools (Read, Edit, Bash, etc.). You are a pure text generator.
3. Do NOT ask clarifying questions. Work with the data provided.
4. Do NOT write or modify any files. Your only output is the JSON response.
5. Start your response with `{` and end with `}`.
"""

# Max tokens of session context to include in a single LLM prompt
CONTEXT_TOKEN_BUDGET = 100_000

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


def require_backend() -> InferenceBackend:
    """Get the inference backend or raise if unavailable.

    Returns:
        Configured inference backend.

    Raises:
        ValueError: If no backend is configured.
    """
    backend = get_inference_backend()
    if not backend:
        raise ValueError("No inference backend configured. Set llm.backend in config.")
    return backend


def extract_all_contexts(
    session_ids: list[str], session_token: str | None, extractor: ContextExtractor | None = None
) -> SessionContextBatch:
    """Load sessions and extract compressed contexts.

    Factory: loads sessions from stores, extracts each, returns a
    SessionContextBatch with all results.

    Args:
        session_ids: Sessions to load.
        session_token: Browser tab token for upload scoping.
        extractor: Context extractor to use; defaults to DetailExtractor.

    Returns:
        SessionContextBatch wrapping extracted contexts and load status.
    """
    if extractor is None:
        extractor = DetailExtractor()
    contexts: list[SessionContext] = []
    loaded_ids: list[str] = []
    skipped_ids: list[str] = []

    for sid in session_ids:
        if get_metadata_from_stores(sid, session_token) is None:
            skipped_ids.append(sid)
            continue
        try:
            trajectories = load_from_stores(sid, session_token)
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("Failed to load session %s, skipping: %s", sid, exc)
            skipped_ids.append(sid)
            continue
        if not trajectories:
            skipped_ids.append(sid)
            continue

        ctx = extractor.extract(trajectory_group=trajectories, session_index=len(contexts))
        contexts.append(ctx)
        loaded_ids.append(sid)

    return SessionContextBatch(
        contexts=contexts, session_ids=loaded_ids, skipped_session_ids=skipped_ids
    )


def format_context_batch(batch: SessionContextBatch) -> str:
    """Concatenate session context texts from a batch into a single digest string.

    Args:
        batch: SessionContextBatch containing extracted session contexts.

    Returns:
        Combined context text, or placeholder if empty.
    """
    if not batch.contexts:
        return "[no sessions]"
    return "\n\n".join(ctx.context_text for ctx in batch.contexts)


def build_system_kwargs(prompt: AnalysisPrompt, backend: InferenceBackend) -> dict[str, str]:
    """Build common kwargs for render_system(): output_schema + backend_rules.

    Args:
        prompt: AnalysisPrompt with output_model and optional exclude_fields.
        backend: Active inference backend.

    Returns:
        Dict with output_schema and backend_rules keys.
    """
    kwargs: dict[str, str] = {"output_schema": json.dumps(prompt.output_json_schema(), indent=2)}
    if backend.backend_id != BackendType.LITELLM:
        kwargs["backend_rules"] = CLI_BACKEND_RULES
    else:
        kwargs["backend_rules"] = ""
    return kwargs


def truncate_digest_to_fit(
    digest: str,
    system_prompt: str,
    other_user_content: str,
    budget_tokens: int = CONTEXT_TOKEN_BUDGET,
) -> str:
    """Truncate digest so the total prompt stays within budget.

    Preserves the first and last portions of the digest, cutting from the middle.

    Args:
        digest: Session digest text.
        system_prompt: Rendered system prompt.
        other_user_content: Non-digest portion of the user prompt.
        budget_tokens: Maximum token budget for the full prompt.

    Returns:
        Possibly truncated digest string.
    """
    overhead_tokens = count_tokens(system_prompt) + count_tokens(other_user_content)
    digest_tokens = count_tokens(digest)
    available = budget_tokens - overhead_tokens
    logger.info(
        "Token budget: overhead=%d, digest=%d, available=%d, budget=%d",
        overhead_tokens,
        digest_tokens,
        available,
        budget_tokens,
    )
    if available <= 0:
        return "[digest truncated -- no token budget remaining]"

    if digest_tokens <= available:
        return digest

    total_chars = len(digest)
    target_chars = int(total_chars * (available / digest_tokens))
    head_chars = int(target_chars * 0.7)
    tail_chars = target_chars - head_chars

    head = digest[:head_chars]
    tail = digest[-tail_chars:] if tail_chars > 0 else ""
    truncated_count = digest_tokens - available
    logger.info(
        "Digest truncated: %d → %d tokens (%d removed)",
        digest_tokens,
        available,
        truncated_count,
    )
    return f"{head}\n\n[... {truncated_count} tokens truncated ...]\n\n{tail}"


def sample_contexts(
    batch: SessionContextBatch, token_budget: int = CONTEXT_TOKEN_BUDGET
) -> SessionContextBatch:
    """Select a diverse, recent, high-quality subset of sessions within token budget.

    Scores each session by recency (0.4), richness (0.3), and project diversity (0.3),
    then greedily packs top-scored sessions until the token budget is exhausted.

    Args:
        batch: Full SessionContextBatch from extract_all_contexts.
        token_budget: Maximum tokens for the combined digest.

    Returns:
        New SessionContextBatch with sampled and re-indexed contexts.
    """
    if not batch.contexts:
        return batch

    estimated_total = sum(len(ctx.context_text) for ctx in batch.contexts) // CHARS_PER_TOKEN
    if estimated_total <= token_budget:
        return batch

    scores = _score_sessions(batch.contexts)
    ranked = sorted(
        zip(batch.contexts, scores, strict=True), key=lambda pair: pair[1], reverse=True
    )

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
        len(batch.contexts),
        running_chars // CHARS_PER_TOKEN,
        token_budget,
    )

    return SessionContextBatch(
        contexts=selected,
        session_ids=[ctx.session_id for ctx in selected],
        skipped_session_ids=batch.skipped_session_ids,
    )


def _score_sessions(contexts: list[SessionContext]) -> list[float]:
    """Compute composite scores for session sampling.

    Args:
        contexts: List of SessionContext to score.

    Returns:
        List of float scores, same order as input.
    """
    now = datetime.now(timezone.utc)
    project_counts = _count_projects(contexts)
    step_counts = [_get_step_count(ctx) for ctx in contexts]
    max_steps = min(max(step_counts) if step_counts else 1, RICHNESS_STEP_CEILING)

    scores: list[float] = []
    for ctx, steps in zip(contexts, step_counts, strict=True):
        recency = _recency_score(ctx.timestamp, now)
        richness = min(steps, RICHNESS_STEP_CEILING) / max(max_steps, 1)
        diversity = 1.0 / project_counts.get(ctx.project_path or "unknown", 1)
        composite = (
            RECENCY_WEIGHT * recency
            + RICHNESS_WEIGHT * richness
            + DIVERSITY_WEIGHT * diversity
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


def _get_step_count(ctx: SessionContext) -> int:
    """Get step count from the main trajectory.

    Args:
        ctx: SessionContext with trajectory_group.

    Returns:
        Number of steps in the first trajectory, or 0.
    """
    if ctx.trajectory_group:
        return len(ctx.trajectory_group[0].steps)
    return 0


def _count_projects(contexts: list[SessionContext]) -> dict[str, int]:
    """Count sessions per project path.

    Args:
        contexts: List of SessionContext.

    Returns:
        Dict mapping project_path to session count.
    """
    counts: dict[str, int] = {}
    for ctx in contexts:
        key = ctx.project_path or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


async def run_batches_concurrent(
    tasks: list[Coroutine], label: str
) -> tuple[list[tuple], list[str]]:
    """Run batch coroutines concurrently, tolerating individual failures.

    Generic replacement for per-module _run_all_batches / _run_proposal_batches
    functions. Each task should return a tuple (output, cost_usd).

    Args:
        tasks: List of coroutines that each return (output, cost_usd).
        label: Human-readable label for log messages (e.g. "proposal", "friction").

    Returns:
        Tuple of (successful result tuples, warning messages).

    Raises:
        InferenceError: If every task fails.
    """
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    successes: list[tuple] = []
    warnings: list[str] = []
    for idx, result in enumerate(raw_results):
        if isinstance(result, BaseException):
            warnings.append(f"Batch {idx + 1}/{len(raw_results)} failed: {result}")
            logger.warning("%s batch %d failed: %s", label.capitalize(), idx, result)
        else:
            successes.append(result)

    if not successes:
        raise InferenceError(
            f"All {len(raw_results)} {label} batch(es) failed. Last error: {raw_results[-1]}"
        )

    return successes, warnings


def save_analysis_log(log_dir: Path, filename: str, content: str) -> None:
    """Save analysis log to a timestamped directory.

    Args:
        log_dir: Target directory (e.g. logs/friction/20260326153000).
        filename: File name within the directory.
        content: Text content to write.
    """
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / filename).write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to save analysis log %s/%s: %s", log_dir, filename, exc)


def log_analysis_summary(
    context_set: SessionContextBatch, batches: list[SessionContextBatch], backend: InferenceBackend
) -> None:
    """Log a structured summary of an analysis run.

    Args:
        context_set: SessionContextBatch with loaded/skipped session metadata.
        batches: Built session batches.
        backend: Inference backend in use.
    """
    total_tokens = sum(b.total_tokens for b in batches)
    logger.info(
        "Analysis run: %d loaded, %d skipped, %d batches, %d total tokens, model=%s, backend=%s",
        len(context_set.session_ids),
        len(context_set.skipped_session_ids),
        len(batches),
        total_tokens,
        backend.model,
        backend.backend_id,
    )
    for batch in batches:
        sids = [ctx.session_id for ctx in batch.contexts]
        logger.info(
            "Batch %s: %d sessions, %d tokens, ids=%s",
            batch.batch_id,
            len(sids),
            batch.total_tokens,
            sids,
        )
