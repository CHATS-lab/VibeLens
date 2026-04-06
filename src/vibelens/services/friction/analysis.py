"""Friction service — user-centric multi-session LLM-powered friction analysis.

Pipeline: load sessions → extract context → build batches →
concurrent LLM inference → optional synthesis → validate span_refs →
compute friction_cost per event → persist → cache.
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
    FrictionEvent,
)
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
from vibelens.services.session_batcher import build_batches
from vibelens.services.skill.shared import parse_llm_output
from vibelens.utils.log import clear_analysis_id, get_logger, set_analysis_id

logger = get_logger(__name__)

FRICTION_OUTPUT_TOKENS = 8192
FRICTION_TIMEOUT_SECONDS = 300
SYNTHESIS_OUTPUT_TOKENS = 20000
SYNTHESIS_TIMEOUT_SECONDS = 120
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
    context_set = extract_all_contexts(session_ids, session_token)

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
        FrictionAnalysisResult with identified events and mitigations.

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

    # Step 3: Resolve synthetic step indices, validate span_refs, compute friction_cost
    validated_events = _validate_and_enrich(analysis_output.friction_events, context_set)

    duration = round(time.monotonic() - start_time, 2)
    friction_result = FrictionAnalysisResult(
        title=analysis_output.title,
        user_profile=analysis_output.user_profile,
        summary=analysis_output.summary,
        mitigations=analysis_output.mitigations,
        friction_events=validated_events,
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

    system_kwargs = build_system_kwargs(FRICTION_ANALYSIS_PROMPT.output_model, backend)
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
        json_schema=FRICTION_ANALYSIS_PROMPT.output_model.model_json_schema(),
    )

    if batch_index == 0:
        save_analysis_log(log_dir, "system_prompt.txt", system_prompt)
    save_analysis_log(log_dir, f"user_prompt_{batch_index}.txt", user_prompt)

    try:
        result = await backend.generate(request)
    except Exception:
        save_analysis_log(log_dir, f"error_{batch_index}.txt", "LLM inference failed.")
        raise

    save_analysis_log(log_dir, f"output_{batch_index}.txt", result.text)

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
            "user_profile": output.user_profile,
            "summary": output.summary,
            "friction_events": [
                {
                    "friction_type": e.friction_type,
                    "severity": e.severity,
                    "user_intention": e.user_intention,
                    "description": e.description,
                    "span_ref": {
                        "session_id": e.span_ref.session_id,
                        "start_step_id": e.span_ref.start_step_id,
                        "end_step_id": e.span_ref.end_step_id,
                    },
                }
                for e in output.friction_events
            ],
            "mitigations": [
                {"action": m.action, "confidence": m.confidence} for m in output.mitigations
            ],
        }
        for output, _ in batch_results
    ]

    system_kwargs = build_system_kwargs(FRICTION_SYNTHESIS_PROMPT.output_model, backend)
    system_prompt = FRICTION_SYNTHESIS_PROMPT.render_system(**system_kwargs)
    user_prompt = FRICTION_SYNTHESIS_PROMPT.render_user(
        batch_count=len(batch_results), session_count=session_count, batch_results=batch_data
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=SYNTHESIS_OUTPUT_TOKENS,
        timeout=SYNTHESIS_TIMEOUT_SECONDS,
        json_schema=FRICTION_SYNTHESIS_PROMPT.output_model.model_json_schema(),
    )

    save_analysis_log(log_dir, "synthesis_system.txt", system_prompt)
    save_analysis_log(log_dir, "synthesis_user.txt", user_prompt)

    result = await backend.generate(request)
    save_analysis_log(log_dir, "synthesis_raw_output.txt", result.text)

    synthesis = parse_llm_output(result.text, FrictionAnalysisOutput, "friction synthesis")
    cost = result.cost_usd or 0.0
    logger.info("Synthesis complete: title=%r", synthesis.title)
    return synthesis, cost


def _validate_and_enrich(
    events: list[FrictionEvent], context_set: SessionContextBatch
) -> list[FrictionEvent]:
    """Resolve synthetic step indices, validate span_refs, and enrich events.

    Pipeline per event: resolve → validate → clamp severity → compute friction_cost.

    Args:
        events: Friction events from LLM output (with synthetic step indices).
        context_set: SessionContextBatch with trajectories and step index maps.

    Returns:
        List of validated and enriched FrictionEvents, sorted by severity descending.
    """
    validated: list[FrictionEvent] = []
    for event in events:
        valid_ref = context_set.resolve_step_ref(event.span_ref)
        if valid_ref is None:
            continue

        event.span_ref = valid_ref

        # Clamp severity to valid range
        if event.severity < 1 or event.severity > 5:
            clamped = max(1, min(5, event.severity))
            logger.warning(
                "Clamping severity %d → %d on event [%s]",
                event.severity,
                clamped,
                event.friction_type,
            )
            event.severity = clamped

        event.friction_cost = _compute_event_cost(event, context_set.all_trajectories)
        validated.append(event)

    dropped_count = len(events) - len(validated)
    if dropped_count > 0:
        logger.info(
            "Validation: %d/%d events passed, %d dropped",
            len(validated),
            len(events),
            dropped_count,
        )

    validated.sort(key=lambda e: e.severity, reverse=True)
    return validated


def _compute_event_cost(event: FrictionEvent, trajectories: list[Trajectory]) -> FrictionCost:
    """Compute cost from step span metrics.

    Finds steps between start_step_id and end_step_id in matching trajectory,
    then computes affected_steps, affected_tokens, and affected_time_seconds.

    Args:
        event: Friction event with span_ref.
        trajectories: All loaded trajectories.

    Returns:
        Computed FrictionCost.
    """
    span_ref = event.span_ref
    target_sid = span_ref.session_id

    target_traj = None
    for t in trajectories:
        if t.session_id == target_sid:
            target_traj = t
            break

    if not target_traj:
        return FrictionCost(affected_steps=0)

    # Walk all steps to find the start/end indices of the friction span
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


