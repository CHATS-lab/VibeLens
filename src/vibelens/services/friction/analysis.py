"""Friction service — user-centric multi-session LLM-powered friction analysis.

Pipeline: load sessions → extract context per session → build batches →
concurrent LLM inference → compute costs from step spans → merge batch
results → validate step_id refs → compute type_summary → persist → cache.
"""

import asyncio
import hashlib
import json
import time
from collections import defaultdict
from datetime import UTC, datetime

from pydantic import BaseModel, ValidationError

from vibelens.deps import (
    get_friction_store,
    get_inference_backend,
    get_store,
    is_demo_mode,
)
from vibelens.llm.backend import InferenceBackend, InferenceError
from vibelens.llm.prompts.friction_analysis import FRICTION_ANALYSIS_PROMPT
from vibelens.models.analysis.friction import (
    FrictionAnalysisResult,
    FrictionCost,
    FrictionEvent,
    FrictionLLMBatchOutput,
    FrictionLLMEvent,
    Mitigation,
    TypeSummary,
)
from vibelens.models.analysis.step_ref import StepRef
from vibelens.models.inference import InferenceRequest
from vibelens.models.trajectories import Trajectory
from vibelens.services.context_extraction import SessionContext, extract_session_context
from vibelens.services.friction.digest import format_batch_digest
from vibelens.services.session_batcher import SessionBatch, build_batches
from vibelens.services.upload_visibility import is_session_visible
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 3600
FRICTION_OUTPUT_TOKENS = 8192
FRICTION_TIMEOUT_SECONDS = 300

_cache: dict[str, tuple[float, BaseModel]] = {}


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
    cached = _get_cached(cache_key)
    if cached:
        return cached

    backend = _require_backend()
    contexts, loaded_ids, skipped_ids = _extract_all_contexts(session_ids, session_token)

    if not contexts:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    batches = build_batches(contexts)
    logger.info("Friction analysis: %d sessions → %d batch(es)", len(loaded_ids), len(batches))

    # Collect all trajectories for cost computation and validation
    all_trajectories = []
    for ctx in contexts:
        all_trajectories.extend(ctx.trajectory_group)

    # Pipeline: concurrent LLM inference → merge batch outputs → validate refs → aggregate
    batch_results = await _run_all_batches(backend, batches)
    events, summary, top_mitigation, total_cost = _merge_batch_results(
        batch_results, all_trajectories
    )
    type_summary = _compute_type_summary(events)

    friction_result = FrictionAnalysisResult(
        events=events,
        summary=summary,
        top_mitigation=top_mitigation,
        type_summary=type_summary,
        session_ids=loaded_ids,
        sessions_skipped=skipped_ids,
        batch_count=len(batches),
        backend_id=backend.backend_id,
        model=_get_backend_model(backend),
        cost_usd=total_cost if total_cost > 0 else None,
        created_at=datetime.now(UTC).isoformat(),
    )

    get_friction_store().save(friction_result)
    _cache[cache_key] = (time.monotonic(), friction_result)
    return friction_result


def _extract_all_contexts(
    session_ids: list[str], session_token: str | None
) -> tuple[list[SessionContext], list[str], list[str]]:
    """Load sessions and extract compressed contexts.

    Args:
        session_ids: Sessions to load.
        session_token: Browser tab token for upload scoping.

    Returns:
        Tuple of (session_contexts, loaded_ids, skipped_ids).
    """
    store = get_store()
    demo = is_demo_mode()
    contexts: list[SessionContext] = []
    loaded_ids: list[str] = []
    skipped_ids: list[str] = []

    for sid in session_ids:
        if demo and not is_session_visible(store.get_metadata(sid), session_token):
            skipped_ids.append(sid)
            continue
        trajectories = store.load(sid)
        if not trajectories:
            skipped_ids.append(sid)
            continue

        ctx = extract_session_context(trajectories)
        contexts.append(ctx)
        loaded_ids.append(sid)

    return contexts, loaded_ids, skipped_ids


async def _infer_batch(
    backend: InferenceBackend, batch: SessionBatch
) -> tuple[FrictionLLMBatchOutput, float]:
    """Run LLM inference for one batch.

    Args:
        backend: Configured inference backend.
        batch: Session batch with pre-extracted contexts.

    Returns:
        Tuple of (parsed batch output, cost in USD).
    """
    digest = format_batch_digest(batch)
    session_count = len(batch.session_contexts)
    output_schema = json.dumps(FRICTION_ANALYSIS_PROMPT.output_model.model_json_schema(), indent=2)

    system_prompt = FRICTION_ANALYSIS_PROMPT.render_system()
    user_prompt = FRICTION_ANALYSIS_PROMPT.render_user(
        session_count=session_count,
        batch_digest=digest,
        output_schema=output_schema,
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=FRICTION_OUTPUT_TOKENS,
        timeout=FRICTION_TIMEOUT_SECONDS,
    )

    _log_friction_prompt(system_prompt, user_prompt, batch.batch_id)
    result = await backend.generate(request)
    _log_friction_response(result.text, batch.batch_id)

    batch_output = _parse_llm_output(result.text)
    cost = result.cost_usd or 0.0
    return batch_output, cost


async def _run_all_batches(
    backend: InferenceBackend, batches: list[SessionBatch]
) -> list[tuple[FrictionLLMBatchOutput, float]]:
    """Run all batches concurrently.

    Args:
        backend: Configured inference backend.
        batches: List of session batches.

    Returns:
        List of (batch_output, cost_usd) tuples.
    """
    tasks = [_infer_batch(backend, batch) for batch in batches]
    return await asyncio.gather(*tasks)


def _merge_batch_results(
    batch_results: list[tuple[FrictionLLMBatchOutput, float]],
    trajectories: list[Trajectory],
) -> tuple[list[FrictionEvent], str, Mitigation | None, float]:
    """Merge results from all batches into a unified result.

    Args:
        batch_results: List of (batch_output, cost_usd) from each batch.
        trajectories: All loaded trajectories for cost computation.

    Returns:
        Tuple of (events, summary, top_mitigation, total_cost_usd).
    """
    all_events: list[FrictionEvent] = []
    summaries: list[str] = []
    top_mitigation: Mitigation | None = None
    highest_severity = 0
    total_cost = 0.0

    for batch_output, cost in batch_results:
        total_cost += cost

        # Enrich LLM events with computed costs
        for llm_event in batch_output.events:
            event_cost = _compute_event_cost(llm_event, trajectories)
            event = FrictionEvent(
                **llm_event.model_dump(),
                estimated_cost=event_cost,
            )
            all_events.append(event)

        if batch_output.summary:
            summaries.append(batch_output.summary)

        # Pick the top_mitigation from the highest-severity batch
        if batch_output.top_mitigation and batch_output.events:
            max_sev = max(e.severity for e in batch_output.events)
            if max_sev > highest_severity:
                highest_severity = max_sev
                top_mitigation = batch_output.top_mitigation

    # Validate step references
    all_events = _validate_and_clean(all_events, trajectories)

    # Sort by severity descending
    all_events.sort(key=lambda e: e.severity, reverse=True)

    summary = " ".join(summaries) if summaries else "No friction detected."
    return all_events, summary, top_mitigation, total_cost


def _compute_event_cost(
    llm_event: FrictionLLMEvent, trajectories: list[Trajectory]
) -> FrictionCost:
    """Compute cost from step span metrics.

    Finds steps between start_step_id and end_step_id in matching trajectory,
    then computes affected_steps, affected_tokens, and affected_time_seconds.

    Args:
        llm_event: LLM-generated friction event.
        trajectories: All loaded trajectories.

    Returns:
        Computed FrictionCost.
    """
    # The LLM returns span_ref with session_id + start/end step_ids.
    # We look up the actual trajectory and slice out the affected step range
    # to compute cost metrics (steps, tokens, wall time).
    span_ref = llm_event.span_ref
    target_sid = span_ref.session_id

    target_traj = None
    for t in trajectories:
        if t.session_id == target_sid:
            target_traj = t
            break

    if not target_traj:
        return FrictionCost(affected_steps=0)

    # Walk all steps to find the start/end indices of the friction span.
    # If no end_step_id is provided, the span is a single step (end = start).
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

    # Compute token cost from step metrics
    total_tokens = 0
    has_metrics = False
    for step in span_steps:
        if step.metrics:
            has_metrics = True
            total_tokens += step.metrics.prompt_tokens + step.metrics.completion_tokens

    # Compute time cost from timestamps
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


def _validate_and_clean(
    events: list[FrictionEvent], trajectories: list[Trajectory]
) -> list[FrictionEvent]:
    """Validate step_id references and drop events with invalid refs.

    Args:
        events: Friction events to validate.
        trajectories: Loaded trajectories for reference validation.

    Returns:
        List of validated FrictionEvents.
    """
    valid_step_ids = {step.step_id for t in trajectories for step in t.steps}
    valid_session_ids = {t.session_id for t in trajectories}

    validated = []
    for event in events:
        ref = event.span_ref

        # Validate session_id
        if ref.session_id not in valid_session_ids:
            logger.warning(
                "Dropping friction event %s: invalid session_id %s",
                event.friction_id,
                ref.session_id,
            )
            continue

        # Validate start_step_id
        if ref.start_step_id not in valid_step_ids:
            logger.warning(
                "Dropping friction event %s: invalid start_step_id %s",
                event.friction_id,
                ref.start_step_id,
            )
            continue

        # Validate end_step_id if present
        if ref.end_step_id and ref.end_step_id not in valid_step_ids:
            logger.warning(
                "Clearing invalid end_step_id %s on event %s",
                ref.end_step_id,
                event.friction_id,
            )
            event.span_ref = StepRef(
                session_id=ref.session_id,
                start_step_id=ref.start_step_id,
            )

        validated.append(event)

    # Clean cross-references
    valid_friction_ids = {e.friction_id for e in validated}
    for event in validated:
        event.related_friction_ids = [
            fid for fid in event.related_friction_ids if fid in valid_friction_ids
        ]

    return validated


def _compute_type_summary(events: list[FrictionEvent]) -> list[TypeSummary]:
    """Compute aggregated statistics per friction_type.

    Args:
        events: Validated friction events.

    Returns:
        TypeSummary list sorted by count descending.
    """
    type_events: dict[str, list[FrictionEvent]] = defaultdict(list)
    for event in events:
        type_events[event.friction_type].append(event)

    summaries = []
    for friction_type, type_evts in type_events.items():
        total_steps = sum(e.estimated_cost.affected_steps for e in type_evts)
        total_time = sum(e.estimated_cost.affected_time_seconds or 0 for e in type_evts)
        total_tokens = sum(e.estimated_cost.affected_tokens or 0 for e in type_evts)
        avg_severity = sum(e.severity for e in type_evts) / len(type_evts)

        summaries.append(
            TypeSummary(
                friction_type=friction_type,
                count=len(type_evts),
                affected_sessions=len({e.span_ref.session_id for e in type_evts}),
                total_estimated_cost=FrictionCost(
                    affected_steps=total_steps,
                    affected_time_seconds=total_time or None,
                    affected_tokens=total_tokens or None,
                ),
                avg_severity=round(avg_severity, 1),
            )
        )

    summaries.sort(key=lambda s: s.count, reverse=True)
    return summaries


def _friction_cache_key(session_ids: list[str]) -> str:
    """Generate a cache key from sorted session IDs."""
    sorted_ids = ",".join(sorted(session_ids))
    return f"friction:{hashlib.sha256(sorted_ids.encode()).hexdigest()[:16]}"


def _require_backend() -> InferenceBackend:
    """Get the inference backend or raise if unavailable."""
    backend = get_inference_backend()
    if not backend:
        raise ValueError("No inference backend configured. Set llm.backend in config.")
    return backend


def _get_backend_model(backend: InferenceBackend) -> str:
    """Extract model name from a backend instance."""
    if hasattr(backend, "_model"):
        return backend._model or "unknown"
    return "unknown"


def _get_cached(cache_key: str) -> BaseModel | None:
    """Return cached result if still valid, or None."""
    entry = _cache.get(cache_key)
    if not entry:
        return None
    cached_at, result = entry
    if time.monotonic() - cached_at > CACHE_TTL_SECONDS:
        del _cache[cache_key]
        return None
    return result


def _parse_llm_output(text: str) -> FrictionLLMBatchOutput:
    """Parse LLM output text into FrictionLLMBatchOutput.

    Args:
        text: Raw LLM output text.

    Returns:
        Validated FrictionLLMBatchOutput instance.

    Raises:
        InferenceError: If parsing or validation fails.
    """
    if not text or not text.strip():
        raise InferenceError(
            "LLM returned empty response. Check logs/friction/ for the prompt that was sent. "
            "The model may not support JSON output or the prompt may exceed context limits."
        )

    json_str = _extract_json(text)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        repaired = _repair_truncated_json(json_str)
        try:
            data = json.loads(repaired)
            logger.warning("Repaired truncated JSON output (max_tokens likely hit)")
        except json.JSONDecodeError as exc:
            preview = json_str[:500] if len(json_str) > 500 else json_str
            raise InferenceError(
                f"LLM output is not valid JSON. Preview: {preview!r}. Error: {exc}"
            ) from exc

    try:
        return FrictionLLMBatchOutput.model_validate(data)
    except ValidationError as exc:
        raise InferenceError(
            f"LLM JSON does not match FrictionLLMBatchOutput schema: {exc}"
        ) from exc


def _extract_json(text: str) -> str:
    """Extract JSON from LLM output, handling markdown code blocks."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.split("\n")
    start = 1
    end = len(lines) - 1

    while end > start and not lines[end].strip().startswith("```"):
        end -= 1

    if end <= start:
        return "\n".join(lines[1:])
    return "\n".join(lines[start:end])


def _repair_truncated_json(text: str) -> str:
    """Attempt to repair JSON truncated by max_tokens.

    Args:
        text: Truncated JSON string.

    Returns:
        Best-effort repaired JSON string.
    """
    # Repair strategy: strip trailing incomplete tokens, fix unbalanced quotes,
    # then count unclosed braces/brackets and append closing characters.
    # This handles the common case where max_tokens cuts off mid-object.
    trimmed = text.rstrip()

    # Step 1: Strip trailing JSON noise (dangling commas, colons, whitespace)
    while trimmed and trimmed[-1] in (",", ":", " ", "\n", "\r", "\t"):
        trimmed = trimmed[:-1]

    # Step 2: Fix unbalanced quotes by truncating to last complete string
    if trimmed.count('"') % 2 != 0:
        last_quote = trimmed.rfind('"')
        if last_quote > 0:
            trimmed = trimmed[: last_quote + 1]

    # Step 3: Count unclosed braces/brackets (respecting string boundaries)
    open_braces = 0
    open_brackets = 0
    in_string = False
    escape_next = False

    for char in trimmed:
        if escape_next:
            escape_next = False
            continue
        if char == "\\":
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            open_braces += 1
        elif char == "}":
            open_braces -= 1
        elif char == "[":
            open_brackets += 1
        elif char == "]":
            open_brackets -= 1

    # Step 4: Append closing characters (brackets before braces for valid nesting)
    suffix = "]" * max(open_brackets, 0) + "}" * max(open_braces, 0)
    return trimmed + suffix


def _log_friction_prompt(system_prompt: str, user_prompt: str, batch_id: str) -> None:
    """Log the full friction prompt via the module logger."""
    logger.info(
        "Friction prompt — batch=%s | system_chars=%d | user_chars=%d\n"
        "SYSTEM PROMPT:\n%s\n\nUSER PROMPT:\n%s",
        batch_id,
        len(system_prompt),
        len(user_prompt),
        system_prompt,
        user_prompt,
    )


def _log_friction_response(raw_output: str, batch_id: str) -> None:
    """Log the raw LLM response via the module logger."""
    logger.info(
        "Friction response — batch=%s | response_chars=%d\nRAW OUTPUT:\n%s",
        batch_id,
        len(raw_output),
        raw_output,
    )
