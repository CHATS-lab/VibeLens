"""Shared infrastructure for LLM-powered analysis services.

Consolidates helpers used by friction analysis and personalization
(creation, evolution): backend retrieval, session context extraction,
caching, prompt rendering, inference orchestration, LLM output parsing,
and per-entry output caps (example_refs, counts).
"""

import asyncio
import json
import time
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TypeVar

from cachetools import TTLCache
from pydantic import BaseModel, ValidationError

from vibelens.context import ContextExtractor
from vibelens.deps import get_inference_backend
from vibelens.llm.backend import InferenceBackend, InferenceError
from vibelens.models.context import SessionContext, SessionContextBatch
from vibelens.models.llm.inference import BackendType, InferenceRequest
from vibelens.models.llm.prompts import TEMPLATES_DIR, AnalysisPrompt
from vibelens.models.trajectories.final_metrics import FinalMetrics
from vibelens.models.trajectories.metrics import Metrics
from vibelens.services.inference_log import (
    InferenceCallContext,
    InferenceLogWriter,
    run_inference,
)
from vibelens.services.session.store_resolver import (
    get_metadata_from_stores,
    load_from_stores,
)
from vibelens.utils.json import extract_json_from_llm_output, repair_json_escapes
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Time-to-live for analysis result caches (1 hour)
CACHE_TTL_SECONDS = 3600
# Maximum entries in each analysis result cache
CACHE_MAXSIZE = 64
# CLI-specific rules appended to system prompts for non-LiteLLM backends.
# Common rules (JSON format, no clarifying questions, etc.) are inlined in
# _output_envelope.j2 and apply to every backend - no string injection needed.
CLI_BACKEND_RULES = (TEMPLATES_DIR / "_partials" / "_backend_rules.j2").read_text()
# Worker pool size for parallel session load + extract.
# 8 balances I/O concurrency against extractor CPU cost for JSON parse.
EXTRACT_MAX_WORKERS = 8
# Per-entry caps on LLM-emitted analysis output. Passed into every system
# template as Jinja kwargs (see build_system_kwargs) so prompts stay in sync
# with post-processing. Every cap is also enforced deterministically in
# Python (truncate_to_cap) because LLMs regularly exceed max-N instructions.
MAX_EXAMPLE_REFS_PER_ENTRY = 3
MAX_WORKFLOW_PATTERNS_PER_BATCH = 3
MAX_WORKFLOW_PATTERNS = 5
MAX_PROPOSALS_PER_BATCH = 3
MAX_PROPOSALS = 5
MAX_FRICTION_TYPES_PER_BATCH = 3
MAX_FRICTION_TYPES = 5
MAX_MITIGATIONS_PER_BATCH = 3
MAX_MITIGATIONS = 5

ModelT = TypeVar("ModelT", bound=BaseModel)

# Cache for extracted SessionContextBatch results. Keyed by
# (tuple(session_ids), session_token, extractor_class_name). Tuple (not
# frozenset) because input ordering defines SessionContext.session_index,
# which downstream step-ref resolution depends on.
#
# maxsize is smaller than other analysis caches because each entry holds
# full trajectory_group objects, which dominate memory for large session
# sets.
_CONTEXT_CACHE_MAXSIZE = 16
_CONTEXT_CACHE: TTLCache = TTLCache(maxsize=_CONTEXT_CACHE_MAXSIZE, ttl=CACHE_TTL_SECONDS)


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

    # session_index is assigned by the caller after skipped sessions are filtered out.
    ctx = extractor.extract(trajectory_group=trajectories, session_index=None)
    return _WorkerResult(sid=sid, status=_WorkerStatus.LOADED, context=ctx)


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


def build_system_kwargs(prompt: AnalysisPrompt, backend: InferenceBackend) -> dict[str, object]:
    """Build common kwargs for render_system(): schema + rules + output caps.

    Every system template receives the same cap kwargs so templates reference
    ``{{ max_workflow_patterns }}`` etc. instead of hard-coded numbers.
    Individual templates ignore caps they don't use (Jinja StrictUndefined
    only complains about missing variables referenced in the template).

    Args:
        prompt: AnalysisPrompt with output_model and optional exclude_fields.
        backend: Active inference backend.

    Returns:
        Dict with output_schema, backend_rules, output caps, and any
        caller-added keys.
    """
    kwargs: dict[str, object] = {
        "output_schema": json.dumps(prompt.output_json_schema(), indent=2),
        "max_example_refs": MAX_EXAMPLE_REFS_PER_ENTRY,
        "max_workflow_patterns_per_batch": MAX_WORKFLOW_PATTERNS_PER_BATCH,
        "max_workflow_patterns": MAX_WORKFLOW_PATTERNS,
        "max_proposals_per_batch": MAX_PROPOSALS_PER_BATCH,
        "max_proposals": MAX_PROPOSALS,
        "max_friction_types_per_batch": MAX_FRICTION_TYPES_PER_BATCH,
        "max_friction_types": MAX_FRICTION_TYPES,
        "max_mitigations_per_batch": MAX_MITIGATIONS_PER_BATCH,
        "max_mitigations": MAX_MITIGATIONS,
    }
    if backend.backend_id != BackendType.LITELLM:
        kwargs["backend_rules"] = CLI_BACKEND_RULES
    else:
        kwargs["backend_rules"] = ""
    return kwargs


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


async def run_batches_concurrent(
    tasks: list[Coroutine], label: str
) -> tuple[list[tuple], list[str]]:
    """Run batch coroutines concurrently, tolerating individual failures.

    Each task should return a tuple (output, Metrics).

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


async def run_synthesis(
    backend: InferenceBackend,
    prompt: AnalysisPrompt,
    output_model: type[BaseModel],
    batch_data: list[dict],
    session_count: int,
    writer: InferenceLogWriter,
    workspace_dir: Path,
    extra_user_kwargs: dict[str, object] | None = None,
) -> tuple[BaseModel, Metrics]:
    """Run a synthesis LLM call that merges multi-batch outputs.

    Renders prompts, invokes the backend, parses the response, and logs.

    Args:
        backend: Configured inference backend.
        prompt: AnalysisPrompt whose user template accepts ``batch_count``,
            ``session_count``, ``batch_results`` and any ``extra_user_kwargs``.
        output_model: Pydantic model to validate the LLM response against.
        batch_data: Per-batch serialized outputs the LLM will merge.
        session_count: Total sessions covered by all batches.
        writer: Log writer for this analysis run.
        workspace_dir: CLI subprocess working directory.
        extra_user_kwargs: Optional extra variables for the user template
            (e.g. ``installed_skills`` for evolution synthesis).

    Returns:
        Tuple of (parsed output_model instance, per-call Metrics).
    """
    system_prompt = render_system_for(prompt, backend)
    user_template_kwargs: dict[str, object] = {
        "batch_count": len(batch_data),
        "session_count": session_count,
        "batch_results": batch_data,
    }
    if extra_user_kwargs:
        user_template_kwargs.update(extra_user_kwargs)
    user_prompt = prompt.render_user(**user_template_kwargs)

    system_file = f"{prompt.task_id}_system.txt"
    user_file = f"{prompt.task_id}_user.txt"
    writer.log_prompt_file(system_file, system_prompt)
    writer.log_prompt_file(user_file, user_prompt)

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        json_schema=prompt.output_json_schema(),
        workspace_dir=workspace_dir,
    )
    context = InferenceCallContext(
        task_id=prompt.task_id, system_file=system_file, user_file=user_file
    )
    result = await run_inference(backend, request, writer, context)

    parsed = parse_llm_output(result.text, output_model, prompt.task_id)
    return parsed, result.metrics


def parse_llm_output(
    text: str,
    model_class: type[ModelT],
    label: str,
    field_fallbacks: dict[str, object] | None = None,
) -> ModelT:
    """Parse raw LLM text into a Pydantic model.

    Extracts JSON from the text, validates against the model schema,
    and raises InferenceError with a descriptive message on failure.

    Args:
        text: Raw LLM output text.
        model_class: Pydantic model class to validate against.
        label: Human-readable label for error messages (e.g. "retrieval").
        field_fallbacks: Optional mapping of field names to fallback values
            applied only when that key is missing from the parsed JSON.

    Returns:
        Validated model instance.

    Raises:
        InferenceError: If text is empty, not valid JSON, or fails validation.
    """
    if not text or not text.strip():
        raise InferenceError(f"LLM returned empty response for {label}.")

    json_str = extract_json_from_llm_output(text)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        logger.warning("JSON parse failed for %s at %s; retrying with escape repair", label, exc)
        try:
            data = json.loads(repair_json_escapes(json_str))
        except json.JSONDecodeError as retry_exc:
            preview = json_str[:500] if len(json_str) > 500 else json_str
            raise InferenceError(
                f"{label} output is not valid JSON (even after escape repair). "
                f"Preview: {preview!r}. Error: {retry_exc}"
            ) from retry_exc

    if field_fallbacks and isinstance(data, dict):
        for key, fallback in field_fallbacks.items():
            if key not in data:
                logger.warning("LLM omitted %s in %s output; filling with fallback", key, label)
                data[key] = fallback

    try:
        return model_class.model_validate(data)
    except ValidationError as exc:
        raise InferenceError(
            f"{label} JSON does not match {model_class.__name__} schema: {exc}"
        ) from exc
