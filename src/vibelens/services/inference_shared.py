"""Shared infrastructure for LLM-powered analysis services.

Consolidates functions duplicated across friction, skill, and insight
analysis modules: backend retrieval, session context extraction, caching,
and log persistence.
"""

import asyncio
import json
import time
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from cachetools import TTLCache
from pydantic import BaseModel

from vibelens.context import ContextExtractor
from vibelens.deps import get_inference_backend
from vibelens.llm.backend import InferenceBackend, InferenceError
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.context import SessionContext, SessionContextBatch
from vibelens.models.llm.inference import BackendType, InferenceRequest, InferenceResult
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

# Worker pool size for parallel session load + extract.
# 8 balances I/O concurrency against extractor CPU cost for JSON parse.
EXTRACT_MAX_WORKERS = 8

# Cache for extracted SessionContextBatch results. Keyed by
# (tuple(session_ids), session_token, extractor_class_name). Tuple (not
# frozenset) because input ordering defines SessionContext.session_index,
# which downstream step-ref resolution depends on.
#
# maxsize is smaller than other analysis caches because each entry holds
# full trajectory_group objects, which dominate memory for large session
# sets.
#
# Future-work candidates if the per-proposal deep-phase flow in
# creation/evolution becomes a bottleneck (each proposal uses a different
# session_ids subset, so the tuple key misses on those calls):
#   (b) per-sid cache: key individual SessionContext objects by
#       (sid, session_token, extractor_class) so subsets reuse per-session
#       work. Requires resetting session_index on assembly.
#   (c) hoisted extraction: call extract_all_contexts once at the top of
#       analyze_skill_creation / analyze_skill_evolution and slice the
#       batch per proposal in-memory. Requires reindexing via
#       SessionContext.reindex.
_CONTEXT_CACHE_MAXSIZE = 16
_CONTEXT_CACHE: TTLCache = TTLCache(maxsize=_CONTEXT_CACHE_MAXSIZE, ttl=CACHE_TTL_SECONDS)


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
    last_error: BaseException | None = None
    for idx, result in enumerate(raw_results):
        if isinstance(result, BaseException):
            warnings.append(f"Batch {idx + 1}/{len(raw_results)} failed: {result}")
            logger.warning("%s batch %d failed: %s", label.capitalize(), idx, result)
            last_error = result
        else:
            successes.append(result)

    if not successes:
        raise InferenceError(
            f"All {len(raw_results)} {label} batch(es) failed. Last error: {last_error}"
        )

    return successes, warnings


def _clone_batch(batch: SessionContextBatch) -> SessionContextBatch:
    """Clone a cached SessionContextBatch so downstream mutations (reindex)
    do not corrupt the cached entry.

    SessionContext is cloned shallow — session_index and context_text are
    the only mutable fields callers touch. trajectory_group is shared by
    reference; downstream code only reads it.
    """
    cloned_contexts = [ctx.model_copy() for ctx in batch.contexts]
    return SessionContextBatch(
        contexts=cloned_contexts,
        session_ids=list(batch.session_ids),
        skipped_session_ids=list(batch.skipped_session_ids),
    )


class _WorkerStatus(Enum):
    """Outcome of a single per-session load + extract worker."""

    LOADED = "loaded"
    SKIPPED = "skipped"


@dataclass
class _WorkerResult:
    """Outcome of _load_and_extract_one, assembled back in input order."""

    sid: str
    status: _WorkerStatus
    context: SessionContext | None = None


def _load_and_extract_one(
    sid: str, session_token: str | None, extractor: ContextExtractor
) -> _WorkerResult:
    """Load one session and extract its context, tolerating failures.

    Runs inside a ThreadPoolExecutor worker. Catches the same exception
    classes the previous sequential loop handled so one bad session never
    raises into the pool.

    Thread-safety assumptions (hold for current codebase):
      - ContextExtractor subclasses (Detail/Summary/MetadataExtractor) are
        stateless during .extract(); only self.params (read-only) and
        fresh per-call helpers are touched.
      - get_metadata_from_stores / load_from_stores are read-only against
        an already-warm index. Concurrent reads on LocalStore's metadata
        dict are safe.
    """
    if get_metadata_from_stores(sid, session_token) is None:
        return _WorkerResult(sid=sid, status=_WorkerStatus.SKIPPED)
    try:
        trajectories = load_from_stores(sid, session_token)
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("Failed to load session %s, skipping: %s", sid, exc)
        return _WorkerResult(sid=sid, status=_WorkerStatus.SKIPPED)
    if not trajectories:
        return _WorkerResult(sid=sid, status=_WorkerStatus.SKIPPED)

    # session_index is left unset here; assigned by the caller after
    # skipped sessions are filtered out.
    ctx = extractor.extract(trajectory_group=trajectories, session_index=None)
    return _WorkerResult(sid=sid, status=_WorkerStatus.LOADED, context=ctx)


def extract_all_contexts(
    session_ids: list[str], session_token: str | None, extractor: ContextExtractor
) -> SessionContextBatch:
    """Load sessions and extract compressed contexts (cached, parallel).

    Factory: loads sessions from stores, extracts each, returns a
    SessionContextBatch with all results.

    Results are cached in-process for CACHE_TTL_SECONDS, keyed by
    (tuple(session_ids), session_token, extractor class). The same call
    from estimate_*() and analyze_*() hits the cache on the second call.

    Per-session load + extract runs in a ThreadPoolExecutor. Input
    ordering is preserved so SessionContext.session_index stays
    deterministic.

    Args:
        session_ids: Sessions to load.
        session_token: Browser tab token for upload scoping.
        extractor: Context extractor to use; defaults to DetailExtractor.

    Returns:
        SessionContextBatch wrapping extracted contexts and load status.
    """
    cache_key = (tuple(session_ids), session_token or "", type(extractor).__name__)
    cached = _CONTEXT_CACHE.get(cache_key)
    if cached is not None:
        logger.info(
            "extract_all_contexts: %d sessions served from cache (extractor=%s)",
            len(session_ids),
            type(extractor).__name__,
        )
        # Downstream callers (sample_contexts, build_batches) mutate
        # SessionContext.session_index and context_text via reindex().
        # Return shallow copies so cached entries stay at canonical
        # (input-order) state. trajectory_group is shared by reference;
        # it is not mutated downstream.
        return _clone_batch(cached)

    start_wall = time.perf_counter()
    # Pre-sized list keeps workers' results in input order regardless of
    # completion order.
    results: list[_WorkerResult | None] = [None] * len(session_ids)
    if session_ids:
        with ThreadPoolExecutor(max_workers=EXTRACT_MAX_WORKERS) as pool:
            future_to_index = {
                pool.submit(_load_and_extract_one, sid, session_token, extractor): idx
                for idx, sid in enumerate(session_ids)
            }
            for future in future_to_index:
                idx = future_to_index[future]
                # Workers catch their own exceptions and return SKIPPED;
                # future.result() should not raise.
                results[idx] = future.result()

    contexts: list[SessionContext] = []
    loaded_ids: list[str] = []
    skipped_ids: list[str] = []
    for result in results:
        if result is None:
            continue
        if result.status is _WorkerStatus.LOADED and result.context is not None:
            # Assign session_index to match final position in contexts list,
            # preserving prior semantics.
            result.context.session_index = len(contexts)
            contexts.append(result.context)
            loaded_ids.append(result.sid)
        else:
            skipped_ids.append(result.sid)

    batch = SessionContextBatch(
        contexts=contexts, session_ids=loaded_ids, skipped_session_ids=skipped_ids
    )
    # Store a clone so the caller can freely reindex/mutate without
    # corrupting the cache entry.
    _CONTEXT_CACHE[cache_key] = _clone_batch(batch)

    elapsed = time.perf_counter() - start_wall
    logger.info(
        "extract_all_contexts: %d loaded, %d skipped in %.2fs (extractor=%s)",
        len(loaded_ids),
        len(skipped_ids),
        elapsed,
        type(extractor).__name__,
    )
    return batch


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


async def run_synthesis(
    backend: InferenceBackend,
    prompt: AnalysisPrompt,
    output_model: type[BaseModel],
    batch_data: list[dict],
    session_count: int,
    log_dir: Path,
    max_output_tokens: int,
    timeout_seconds: int,
    analysis_cwd: Path,
    extra_user_kwargs: dict[str, object] | None = None,
) -> tuple[BaseModel, Metrics]:
    """Run a synthesis LLM call that merges multi-batch outputs.

    Unifies friction/creation/evolution synthesis: each service serializes its
    per-batch outputs into ``batch_data`` dicts, then calls this helper to
    render prompts, invoke the backend, save logs, and parse the response.

    Log filenames and parse labels are derived from ``prompt.task_id`` so
    each prompt identifies its own artifacts.

    Args:
        backend: Configured inference backend.
        prompt: AnalysisPrompt whose user template accepts ``batch_count``,
            ``session_count``, ``batch_results`` and any ``extra_user_kwargs``.
        output_model: Pydantic model to validate the LLM response against.
        batch_data: Per-batch serialized outputs the LLM will merge.
        session_count: Total sessions covered by all batches.
        log_dir: Directory for system/user/output log files.
        max_output_tokens: max_tokens on the inference request.
        timeout_seconds: per-request timeout.
        extra_user_kwargs: Optional extra variables for the user template
            (e.g. ``installed_skills`` for evolution synthesis).

    Returns:
        Tuple of (parsed output_model instance, per-call Metrics).
    """
    # Lazy import avoids circular module load between inference_shared and
    # personalization.shared (which depends on CACHE_* constants here).
    from vibelens.services.personalization.shared import parse_llm_output

    system_prompt = render_system_for(prompt, backend)
    user_template_kwargs: dict[str, object] = {
        "batch_count": len(batch_data),
        "session_count": session_count,
        "batch_results": batch_data,
    }
    if extra_user_kwargs:
        user_template_kwargs.update(extra_user_kwargs)
    user_prompt = prompt.render_user(**user_template_kwargs)

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=max_output_tokens,
        timeout=timeout_seconds,
        json_schema=prompt.output_json_schema(),
        analysis_cwd=analysis_cwd,
    )

    save_inference_log(log_dir, f"{prompt.task_id}_system.txt", system_prompt)
    save_inference_log(log_dir, f"{prompt.task_id}_user.txt", user_prompt)

    result = await backend.generate(request)
    save_inference_log(log_dir, f"{prompt.task_id}_output.txt", result.text)

    parsed = parse_llm_output(result.text, output_model, prompt.task_id)
    return parsed, metrics_from_result(result)


def render_system_for(prompt: AnalysisPrompt, backend: InferenceBackend, **extras: object) -> str:
    """Render a prompt's system template with envelope kwargs merged in.

    Every system template includes ``_output_envelope.j2`` which requires
    ``output_schema`` and ``backend_rules``. Callers forget; Jinja's
    StrictUndefined then raises at render time. This helper collapses the
    ``kwargs = build_system_kwargs(...); kwargs.update(...); render_system(**kwargs)``
    pattern into one call and removes that footgun.

    Args:
        prompt: AnalysisPrompt to render.
        backend: Active inference backend (selects CLI vs LITELLM rules).
        **extras: Template-specific variables (e.g. max_results, min_relevance).

    Returns:
        Rendered system prompt string.
    """
    kwargs = build_system_kwargs(prompt, backend)
    kwargs.update(extras)
    return prompt.render_system(**kwargs)


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


def analysis_log_dir(mode: str) -> Path:
    """Return the base directory for per-run prompt artifacts of a mode.

    Friction lives at ``{log_root}/friction/``; the three personalization
    modes live under ``{log_root}/personalization/{mode}/``. The returned
    path has no trailing analysis_id segment — callers append that.
    Resolved at call time so tests that reconfigure settings see the
    current log root.
    """
    from vibelens.deps import get_settings

    base = get_settings().logging.dir
    if mode == "friction":
        return base / "friction"
    return base / "personalization" / mode


def save_inference_log(log_dir: Path, filename: str, content: str) -> None:
    """Save inference log to a per-run directory under ``analysis_log_dir``.

    Args:
        log_dir: Target directory (e.g. ``{log_root}/friction/{analysis_id}``).
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
