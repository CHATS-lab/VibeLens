"""Shared infrastructure for LLM-powered analysis services.

Consolidates functions duplicated across friction, skill, and insight
analysis modules: backend retrieval, session context extraction, caching,
and log persistence.
"""

import asyncio
import json
from collections.abc import Coroutine
from pathlib import Path

from vibelens.context import ContextExtractor
from vibelens.deps import get_inference_backend
from vibelens.llm.backend import InferenceBackend, InferenceError
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.context import SessionContext, SessionContextBatch
from vibelens.models.llm.inference import BackendType, InferenceResult
from vibelens.models.llm.prompts import TEMPLATES_DIR, AnalysisPrompt
from vibelens.models.trajectories.final_metrics import FinalMetrics
from vibelens.models.trajectories.metrics import Metrics
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
# Instructions appended to system prompts when using CLI backends.
# Loaded from the shared partial so templates and this rule have a single source of truth.
CLI_BACKEND_RULES = (TEMPLATES_DIR / "_partials" / "_backend_rules.j2").read_text()

# Max tokens of session context to include in a single LLM prompt
CONTEXT_TOKEN_BUDGET = 100_000


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


def metrics_from_result(result: InferenceResult) -> Metrics:
    """Extract a Metrics snapshot from an LLM InferenceResult."""
    return result.metrics


def aggregate_final_metrics(
    batch_metrics: list[Metrics], duration_seconds: int = 0
) -> FinalMetrics:
    """Sum per-batch Metrics into a single FinalMetrics aggregate.

    Matches the canonical aggregation used by ingest parsers
    (see ``vibelens.ingest.parsers.base._compute_final_metrics``):
    cache tokens are rolled into ``total_prompt_tokens`` so the number
    reflects the true input volume, and also retained separately in
    ``total_cache_read`` / ``total_cache_write``. Anthropic CLIs report
    the cached portion as ``cache_read_input_tokens`` and the non-cached
    portion as ``input_tokens``; summing them here makes the aggregate
    consistent with ingest-side metrics.

    ``total_steps`` counts the LLM calls aggregated (one per batch).
    """
    total_prompt_new = sum(m.prompt_tokens for m in batch_metrics)
    total_cache_read = sum(m.cached_tokens for m in batch_metrics)
    total_cache_write = sum(m.cache_creation_tokens for m in batch_metrics)
    total_prompt = total_prompt_new + total_cache_read + total_cache_write
    total_completion = sum(m.completion_tokens for m in batch_metrics)
    total_cost = sum(m.cost_usd or 0.0 for m in batch_metrics)
    return FinalMetrics(
        total_prompt_tokens=total_prompt if total_prompt else None,
        total_completion_tokens=total_completion if total_completion else None,
        total_cache_read=total_cache_read,
        total_cache_write=total_cache_write,
        total_cost_usd=total_cost if total_cost > 0 else None,
        total_steps=len(batch_metrics) if batch_metrics else None,
        duration=duration_seconds,
    )


async def run_batches_concurrent(
    tasks: list[Coroutine], label: str
) -> tuple[list[tuple], list[str]]:
    """Run batch coroutines concurrently, tolerating individual failures.

    Generic replacement for per-module _run_all_batches / _run_proposal_batches
    functions. Each task should return a tuple (output, Metrics).

    Args:
        tasks: List of coroutines that each return (output, Metrics).
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


def extract_all_contexts(
    session_ids: list[str], session_token: str | None, extractor: ContextExtractor
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


def build_system_kwargs(prompt: AnalysisPrompt, backend: InferenceBackend) -> dict[str, object]:
    """Build common kwargs for render_system(): output_schema + backend_rules.

    Args:
        prompt: AnalysisPrompt with output_model and optional exclude_fields.
        backend: Active inference backend.

    Returns:
        Dict with output_schema, backend_rules, and any caller-added keys.
    """
    kwargs: dict[str, object] = {"output_schema": json.dumps(prompt.output_json_schema(), indent=2)}
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


def save_inference_log(log_dir: Path, filename: str, content: str) -> None:
    """Save inference log to a timestamped directory.

    Args:
        log_dir: Target directory (e.g. logs/friction/20260326153000).
        filename: File name within the directory.
        content: Text content to write.
    """
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / filename).write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to save inference log %s/%s: %s", log_dir, filename, exc)


def log_inference_summary(
    context_set: SessionContextBatch, batches: list[SessionContextBatch], backend: InferenceBackend
) -> None:
    """Log a structured summary of an inference run.

    Args:
        context_set: SessionContextBatch with loaded/skipped session metadata.
        batches: Built session batches.
        backend: Inference backend in use.
    """
    total_tokens = sum(b.total_tokens for b in batches)
    logger.info(
        "Inference run: %d loaded, %d skipped, %d batches, %d total tokens, model=%s, backend=%s",
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
