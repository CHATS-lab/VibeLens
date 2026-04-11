"""Friction service — user-centric multi-session LLM-powered friction analysis.

Pipeline: load sessions → extract context → build batches →
concurrent LLM inference → optional synthesis → validate example_refs →
compute friction_cost per type → persist → cache.
"""

import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path

from cachetools import TTLCache

from vibelens.deps import get_friction_store
from vibelens.llm.backend import InferenceBackend
from vibelens.llm.cost_estimator import CostEstimate, estimate_analysis_cost
from vibelens.llm.prompts.friction_analysis import (
    FRICTION_ANALYSIS_PROMPT,
    FRICTION_SYNTHESIS_PROMPT,
)
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.analysis.friction import (
    FrictionAnalysisOutput,
    FrictionAnalysisResult,
    FrictionCost,
    FrictionType,
)
from vibelens.models.analysis.step_ref import StepRef
from vibelens.models.context import SessionContextBatch
from vibelens.models.llm.inference import InferenceRequest
from vibelens.models.trajectories import Trajectory
from vibelens.models.trajectories.metrics import Metrics
from vibelens.services.analysis_shared import (
    CACHE_MAXSIZE,
    CACHE_TTL_SECONDS,
    build_system_kwargs,
    extract_all_contexts,
    format_batch_digest,
    log_analysis_summary,
    require_backend,
    run_batches_concurrent,
    save_analysis_log,
    truncate_digest_to_fit,
)
from vibelens.services.analysis_store import generate_analysis_id
from vibelens.services.context_params import PRESET_DETAIL
from vibelens.services.session_batcher import build_batches
from vibelens.services.skill.shared import parse_llm_output
from vibelens.utils.log import clear_analysis_id, get_logger, set_analysis_id

logger = get_logger(__name__)

# Max output tokens for a single friction analysis batch call
FRICTION_OUTPUT_TOKENS = 8192
# Timeout per friction batch LLM call (seconds)
FRICTION_TIMEOUT_SECONDS = 300
# Synthesis needs more tokens because it merges multiple batch outputs
SYNTHESIS_OUTPUT_TOKENS = 20000
# Timeout for the synthesis LLM call (seconds)
SYNTHESIS_TIMEOUT_SECONDS = 120
# Directory for detailed request/response analysis logs
FRICTION_LOG_DIR = Path("logs/friction")

_cache: TTLCache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL_SECONDS)


def estimate_friction(session_ids: list[str], session_token: str | None = None) -> CostEstimate:
    """Pre-flight cost estimate for friction analysis without calling the LLM.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.

    Returns:
        CostEstimate with projected cost range.

    Raises:
        ValueError: If no sessions could be loaded.
    """
    backend = require_backend()
    context_set = extract_all_contexts(
        session_ids=session_ids, session_token=session_token, params=PRESET_DETAIL
    )

    if not context_set:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    batches = build_batches(context_set.contexts)
    system_prompt = FRICTION_ANALYSIS_PROMPT.render_system()

    batch_token_counts = [count_tokens(format_batch_digest(batch)) for batch in batches]

    return estimate_analysis_cost(
        batch_token_counts=batch_token_counts,
        system_prompt=system_prompt,
        model=backend.model,
        max_output_tokens=FRICTION_OUTPUT_TOKENS,
        synthesis_output_tokens=SYNTHESIS_OUTPUT_TOKENS,
        synthesis_threshold=0,
    )


async def analyze_friction(
    session_ids: list[str], session_token: str | None = None
) -> FrictionAnalysisResult:
    """Run user-centric friction analysis across specified sessions.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.

    Returns:
        FrictionAnalysisResult with identified friction types and mitigations.

    Raises:
        ValueError: If no sessions could be loaded.
        InferenceError: If LLM backend fails.
    """
    cache_key = _friction_cache_key(session_ids)
    if cache_key in _cache:
        return _cache[cache_key]

    start_time = time.monotonic()
    analysis_id = generate_analysis_id()
    set_analysis_id(analysis_id)

    backend = require_backend()
    context_set = extract_all_contexts(session_ids, session_token)

    if not context_set:
        clear_analysis_id()
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    batches = build_batches(context_set.contexts)
    logger.info(
        "Friction analysis: %d sessions → %d batch(es)",
        len(context_set.session_ids),
        len(batches),
    )

    run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_dir = FRICTION_LOG_DIR / run_timestamp
    log_analysis_summary(context_set, batches, backend)

    # Step 1: Concurrent LLM inference per batch
    tasks = [
        _infer_friction_analysis_batch(backend, batch, log_dir, idx)
        for idx, batch in enumerate(batches)
    ]
    batch_results, batch_warnings = await run_batches_concurrent(tasks, "friction")

    total_cost = sum(cost for _, cost in batch_results)

    # Step 2: Single batch → use directly; multiple → synthesize
    if len(batch_results) == 1:
        analysis_output = batch_results[0][0]
    else:
        analysis_output, syn_cost = await _synthesize_friction_analysis(
            backend, batch_results, len(context_set.session_ids), log_dir
        )
        total_cost += syn_cost
        # Synthesis LLM may drop example_refs; recover from batch outputs
        _merge_friction_refs(
            analysis_output.friction_types,
            [output.friction_types for output, _ in batch_results],
        )

    # Step 3: Validate example_refs and compute friction_cost per type
    validated_types = _validate_and_enrich(analysis_output.friction_types, context_set)

    duration = round(time.monotonic() - start_time, 2)
    friction_result = FrictionAnalysisResult(
        title=analysis_output.title,
        mitigations=analysis_output.mitigations,
        friction_types=validated_types,
        session_ids=context_set.session_ids,
        skipped_session_ids=context_set.skipped_session_ids,
        warnings=batch_warnings,
        batch_count=len(batches),
        backend_id=backend.backend_id,
        model=backend.model,
        metrics=Metrics(cost_usd=total_cost if total_cost > 0 else None),
        duration_seconds=duration,
        created_at=datetime.now(UTC).isoformat(),
    )
    get_friction_store().save(friction_result, analysis_id)
    clear_analysis_id()

    _cache[cache_key] = friction_result
    return friction_result


async def _infer_friction_analysis_batch(
    backend: InferenceBackend, batch: SessionContextBatch, log_dir: Path, batch_index: int
) -> tuple[FrictionAnalysisOutput, float]:
    """Run LLM inference for one batch.

    Args:
        backend: Configured inference backend.
        batch: Session batch with pre-extracted contexts.
        log_dir: Timestamped directory for saving prompts and outputs.
        batch_index: Zero-based batch index for file naming.

    Returns:
        Tuple of (parsed batch output, cost in USD).
    """
    digest = format_batch_digest(batch)
    session_count = len(batch.contexts)

    system_kwargs = build_system_kwargs(FRICTION_ANALYSIS_PROMPT, backend)
    system_prompt = FRICTION_ANALYSIS_PROMPT.render_system(**system_kwargs)

    non_digest_overhead = FRICTION_ANALYSIS_PROMPT.render_user(
        session_count=session_count, batch_digest=""
    )
    digest = truncate_digest_to_fit(digest, system_prompt, non_digest_overhead)

    user_prompt = FRICTION_ANALYSIS_PROMPT.render_user(
        session_count=session_count, batch_digest=digest
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=FRICTION_OUTPUT_TOKENS,
        timeout=FRICTION_TIMEOUT_SECONDS,
        json_schema=FRICTION_ANALYSIS_PROMPT.output_json_schema(),
    )

    if batch_index == 0:
        save_analysis_log(log_dir, "friction_analysis_system.txt", system_prompt)
    save_analysis_log(log_dir, f"friction_analysis_user_{batch_index}.txt", user_prompt)

    try:
        result = await backend.generate(request)
    except Exception:
        error_file = f"friction_analysis_error_{batch_index}.txt"
        save_analysis_log(log_dir, error_file, "LLM inference failed.")
        raise

    save_analysis_log(log_dir, f"friction_analysis_output_{batch_index}.txt", result.text)

    batch_output = parse_llm_output(result.text, FrictionAnalysisOutput, "friction analysis")
    cost = result.cost_usd or 0.0
    return batch_output, cost


async def _synthesize_friction_analysis(
    backend: InferenceBackend,
    batch_results: list[tuple[FrictionAnalysisOutput, float]],
    session_count: int,
    log_dir: Path,
) -> tuple[FrictionAnalysisOutput, float]:
    """Merge results from multiple batches via LLM synthesis.

    Args:
        backend: Configured inference backend.
        batch_results: Per-batch analysis outputs and costs.
        session_count: Total number of sessions analyzed.
        log_dir: Timestamped directory for saving prompts and outputs.

    Returns:
        Tuple of (merged FrictionAnalysisOutput, synthesis cost in USD).
    """
    batch_data = [
        {
            "title": output.title,
            "friction_types": [
                {
                    "type_name": ft.type_name,
                    "severity": ft.severity,
                    "description": ft.description,
                    "example_refs": [
                        {
                            "session_id": ref.session_id,
                            "start_step_id": ref.start_step_id,
                            "end_step_id": ref.end_step_id,
                        }
                        for ref in ft.example_refs
                    ],
                }
                for ft in output.friction_types
            ],
            "mitigations": [
                {
                    "title": m.title,
                    "action": m.action,
                    "rationale": m.rationale,
                    "confidence": m.confidence,
                }
                for m in output.mitigations
            ],
        }
        for output, _ in batch_results
    ]

    system_kwargs = build_system_kwargs(FRICTION_SYNTHESIS_PROMPT, backend)
    system_prompt = FRICTION_SYNTHESIS_PROMPT.render_system(**system_kwargs)
    user_prompt = FRICTION_SYNTHESIS_PROMPT.render_user(
        batch_count=len(batch_results), session_count=session_count, batch_results=batch_data
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=SYNTHESIS_OUTPUT_TOKENS,
        timeout=SYNTHESIS_TIMEOUT_SECONDS,
        json_schema=FRICTION_SYNTHESIS_PROMPT.output_json_schema(),
    )

    save_analysis_log(log_dir, "friction_synthesis_system.txt", system_prompt)
    save_analysis_log(log_dir, "friction_synthesis_user.txt", user_prompt)

    result = await backend.generate(request)
    save_analysis_log(log_dir, "friction_synthesis_output.txt", result.text)

    synthesis = parse_llm_output(result.text, FrictionAnalysisOutput, "friction synthesis")
    cost = result.cost_usd or 0.0
    logger.info("Synthesis complete: title=%r", synthesis.title)
    return synthesis, cost


def _merge_friction_refs(
    synthesis_types: list[FrictionType],
    batch_types_list: list[list[FrictionType]],
) -> None:
    """Recover example_refs the synthesis LLM dropped.

    Builds a union of all example_refs by type_name from batch results,
    then fills any synthesis friction type whose refs are shorter than
    the batch union.

    Mutates synthesis_types in place.

    Args:
        synthesis_types: Friction types from synthesis output.
        batch_types_list: Per-batch friction type lists with refs intact.
    """
    refs_by_type: dict[str, list[StepRef]] = {}
    for batch_types in batch_types_list:
        for ft in batch_types:
            if not ft.example_refs:
                continue
            refs_by_type.setdefault(ft.type_name, []).extend(ft.example_refs)

    merged_count = 0
    for ft in synthesis_types:
        batch_refs = refs_by_type.get(ft.type_name)
        if not batch_refs:
            continue
        if len(ft.example_refs) < len(batch_refs):
            ft.example_refs = list(batch_refs)
            merged_count += 1

    if merged_count:
        logger.info(
            "Merged friction example_refs into %d/%d synthesis types",
            merged_count,
            len(synthesis_types),
        )


def _validate_and_enrich(
    friction_types: list[FrictionType], context_set: SessionContextBatch
) -> list[FrictionType]:
    """Validate example_refs and compute friction_cost per type.

    Pipeline per type: resolve refs → drop invalid → clamp severity → compute cost.

    Args:
        friction_types: Friction types from LLM output (with synthetic step indices).
        context_set: SessionContextBatch with trajectories and step index maps.

    Returns:
        List of validated and enriched FrictionTypes, sorted by severity descending.
    """
    validated: list[FrictionType] = []
    for ft in friction_types:
        valid_refs: list[StepRef] = []
        for ref in ft.example_refs:
            resolved = context_set.resolve_step_ref(ref)
            if resolved is not None:
                valid_refs.append(resolved)

        if not valid_refs:
            continue

        ft.example_refs = valid_refs

        # Clamp severity to valid range
        if ft.severity < 1 or ft.severity > 5:
            clamped = max(1, min(5, ft.severity))
            logger.warning(
                "Clamping severity %d → %d on type [%s]",
                ft.severity,
                clamped,
                ft.type_name,
            )
            ft.severity = clamped

        ft.friction_cost = _compute_type_cost(ft.example_refs, context_set.all_trajectories)
        validated.append(ft)

    dropped_count = len(friction_types) - len(validated)
    if dropped_count > 0:
        logger.info(
            "Validation: %d/%d types passed, %d dropped",
            len(validated),
            len(friction_types),
            dropped_count,
        )

    validated.sort(key=lambda ft: ft.severity, reverse=True)
    return validated


def _compute_type_cost(example_refs: list[StepRef], trajectories: list[Trajectory]) -> FrictionCost:
    """Compute aggregate cost from all example_refs spans.

    For each ref, finds the matching trajectory and walks steps to compute
    affected_steps, affected_tokens, and affected_time_seconds. Sums across
    all refs since each span represents independent wasted effort.

    Args:
        example_refs: Step span references for this friction type.
        trajectories: All loaded trajectories.

    Returns:
        Aggregated FrictionCost across all spans.
    """
    total_steps = 0
    total_tokens = 0
    has_any_metrics = False
    total_time = 0
    has_any_time = False

    for ref in example_refs:
        span_cost = _compute_span_cost(ref, trajectories)
        total_steps += span_cost.affected_steps
        if span_cost.affected_tokens is not None:
            has_any_metrics = True
            total_tokens += span_cost.affected_tokens
        if span_cost.affected_time_seconds is not None:
            has_any_time = True
            total_time += span_cost.affected_time_seconds

    return FrictionCost(
        affected_steps=total_steps,
        affected_tokens=total_tokens if has_any_metrics else None,
        affected_time_seconds=total_time if has_any_time else None,
    )


def _compute_span_cost(span_ref: StepRef, trajectories: list[Trajectory]) -> FrictionCost:
    """Compute cost for a single step span.

    Args:
        span_ref: Step span reference.
        trajectories: All loaded trajectories.

    Returns:
        FrictionCost for this single span.
    """
    target_traj = None
    for t in trajectories:
        if t.session_id == span_ref.session_id:
            target_traj = t
            break

    if not target_traj:
        return FrictionCost(affected_steps=0)

    start_idx = None
    end_idx = None
    for i, step in enumerate(target_traj.steps):
        if step.step_id == span_ref.start_step_id:
            start_idx = i
        is_end = (
            span_ref.end_step_id
            and step.step_id == span_ref.end_step_id
            or not span_ref.end_step_id
            and step.step_id == span_ref.start_step_id
        )
        if is_end:
            end_idx = i

    if start_idx is None:
        return FrictionCost(affected_steps=0)
    if end_idx is None:
        end_idx = start_idx

    span_steps = target_traj.steps[start_idx : end_idx + 1]
    affected_steps = len(span_steps)

    total_tokens = 0
    has_metrics = False
    for step in span_steps:
        if step.metrics:
            has_metrics = True
            total_tokens += step.metrics.prompt_tokens + step.metrics.completion_tokens

    affected_time = None
    first_ts = span_steps[0].timestamp if span_steps else None
    last_ts = span_steps[-1].timestamp if span_steps else None
    if first_ts and last_ts and first_ts != last_ts:
        affected_time = int((last_ts - first_ts).total_seconds())

    return FrictionCost(
        affected_steps=affected_steps,
        affected_tokens=total_tokens if has_metrics else None,
        affected_time_seconds=affected_time,
    )


def _friction_cache_key(session_ids: list[str]) -> str:
    """Generate a cache key from sorted session IDs."""
    sorted_ids = ",".join(sorted(session_ids))
    return f"friction:{hashlib.sha256(sorted_ids.encode()).hexdigest()[:16]}"
