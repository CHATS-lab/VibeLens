"""Friction service — multi-session LLM-powered friction analysis.

Pipeline: load sessions → build signals → digest → prompt → infer →
validate → recompute mode_summary → cache.
"""

import hashlib
import json
import time
from collections import defaultdict
from datetime import UTC, datetime

from pydantic import BaseModel, ValidationError

from vibelens.analysis.step_signals import build_step_signals
from vibelens.deps import (
    get_friction_store,
    get_inference_backend,
    get_store,
    is_demo_mode,
)
from vibelens.llm.backend import InferenceBackend, InferenceError
from vibelens.llm.digest_friction import digest_step_signals
from vibelens.llm.prompts.friction_analysis import FRICTION_ANALYSIS_PROMPT
from vibelens.models.analysis.friction import (
    FrictionAnalysisResult,
    FrictionCost,
    FrictionEvent,
    FrictionLLMOutput,
    ModeSummary,
)
from vibelens.models.analysis.step_ref import StepRef
from vibelens.models.inference import InferenceRequest
from vibelens.models.trajectories import Trajectory
from vibelens.services.upload_visibility import is_session_visible
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 3600

_cache: dict[str, tuple[float, BaseModel]] = {}


async def analyze_friction(
    session_ids: list[str], session_token: str | None = None
) -> FrictionAnalysisResult:
    """Run LLM-powered friction analysis across specified sessions.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.

    Returns:
        FrictionAnalysisResult with identified events and CLAUDE.md suggestions.

    Raises:
        ValueError: If no sessions could be loaded.
        InferenceError: If LLM backend fails.
    """
    cache_key = _friction_cache_key(session_ids)
    cached = _get_cached(cache_key)
    if cached:
        return cached

    backend = _require_backend()
    loaded_trajectories, loaded_session_ids, skipped_session_ids = _load_sessions(
        session_ids, session_token
    )

    if not loaded_trajectories:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    signals = build_step_signals(loaded_trajectories)
    digest = digest_step_signals(signals)
    user_prompt = _format_friction_prompt(digest, len(loaded_session_ids))

    request = InferenceRequest(system=FRICTION_ANALYSIS_PROMPT.render_system(), user=user_prompt)
    result = await backend.generate(request)
    llm_output = _parse_llm_output(result.text)

    validated_events = _validate_and_clean(llm_output, loaded_trajectories)
    mode_summary = _compute_mode_summary(validated_events)

    friction_result = FrictionAnalysisResult(
        events=validated_events,
        summary=llm_output.summary,
        top_mitigation=llm_output.top_mitigation,
        claude_md_suggestions=llm_output.claude_md_suggestions,
        mode_summary=mode_summary,
        session_ids=loaded_session_ids,
        sessions_skipped=skipped_session_ids,
        backend_id=backend.backend_id,
        model=_get_backend_model(backend),
        cost_usd=result.cost_usd,
        computed_at=datetime.now(UTC).isoformat(),
    )

    # Auto-persist the result to disk
    get_friction_store().save(friction_result)

    _cache[cache_key] = (time.monotonic(), friction_result)
    return friction_result


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


def _load_sessions(
    session_ids: list[str], session_token: str | None
) -> tuple[list[Trajectory], list[str], list[str]]:
    """Load trajectories for each session, tracking loaded and skipped.

    Args:
        session_ids: Sessions to load.
        session_token: Browser tab token for upload scoping.

    Returns:
        Tuple of (loaded_trajectories, loaded_session_ids, skipped_session_ids).
    """
    store = get_store()
    demo = is_demo_mode()
    loaded_trajectories: list[Trajectory] = []
    loaded_ids: list[str] = []
    skipped_ids: list[str] = []
    for sid in session_ids:
        # Visibility check only needed in demo mode (upload scoping).
        # In self-use mode all local sessions are visible.
        if demo and not is_session_visible(store.get_metadata(sid), session_token):
            skipped_ids.append(sid)
            continue
        trajectories = store.load(sid)
        if not trajectories:
            skipped_ids.append(sid)
            continue
        loaded_trajectories.extend(trajectories)
        loaded_ids.append(sid)
    return loaded_trajectories, loaded_ids, skipped_ids


def _format_friction_prompt(digest: str, session_count: int) -> str:
    """Format the friction analysis user prompt."""
    output_schema = json.dumps(FRICTION_ANALYSIS_PROMPT.output_model.model_json_schema(), indent=2)
    return FRICTION_ANALYSIS_PROMPT.render_user(
        session_count=session_count, session_digest=digest, output_schema=output_schema
    )


def _parse_llm_output(text: str) -> FrictionLLMOutput:
    """Parse LLM output text into FrictionLLMOutput.

    Args:
        text: Raw LLM output text.

    Returns:
        Validated FrictionLLMOutput instance.

    Raises:
        InferenceError: If parsing or validation fails.
    """
    json_str = _extract_json(text)
    try:
        data = json.loads(json_str)
        return FrictionLLMOutput.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise InferenceError(f"Failed to parse LLM output as FrictionLLMOutput: {exc}") from exc


def _extract_json(text: str) -> str:
    """Extract JSON from LLM output, handling markdown code blocks."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        start = 1
        end = len(lines) - 1
        while end > start and not lines[end].strip().startswith("```"):
            end -= 1
        return "\n".join(lines[start:end])
    return stripped


def _validate_and_clean(
    llm_output: FrictionLLMOutput, trajectories: list[Trajectory]
) -> list[FrictionEvent]:
    """Validate LLM output references and clean invalid ones.

    Args:
        llm_output: Raw LLM friction output.
        trajectories: Loaded trajectories for reference validation.

    Returns:
        List of validated FrictionEvents.
    """
    valid_step_ids = {step.step_id for t in trajectories for step in t.steps}
    valid_tc_ids = {
        tc.tool_call_id
        for t in trajectories
        for step in t.steps
        for tc in step.tool_calls
        if tc.tool_call_id
    }

    validated = _validate_friction_events(llm_output.events, valid_step_ids, valid_tc_ids)

    # Clean cross-references using only validated event IDs
    valid_event_ids = {e.event_id for e in validated}
    for event in validated:
        event.related_event_ids = [eid for eid in event.related_event_ids if eid in valid_event_ids]
    for suggestion in llm_output.claude_md_suggestions:
        suggestion.source_event_ids = [
            eid for eid in suggestion.source_event_ids if eid in valid_event_ids
        ]

    return validated


def _validate_friction_events(
    events: list[FrictionEvent], valid_step_ids: set[str], valid_tc_ids: set[str]
) -> list[FrictionEvent]:
    """Validate step_id and tool_call_id references, dropping invalid events.

    Args:
        events: Raw friction events from LLM output.
        valid_step_ids: Set of all step_ids in the loaded trajectories.
        valid_tc_ids: Set of all tool_call_ids in the loaded trajectories.

    Returns:
        List of validated events with invalid references cleaned.
    """
    validated = []
    for event in events:
        valid_steps = [sid for sid in event.step_ids if sid in valid_step_ids]
        if not valid_steps:
            logger.warning(
                "Dropping friction event %s: no valid step_ids (had %s)",
                event.event_id,
                event.step_ids,
            )
            continue
        event.step_ids = valid_steps

        # Validate tool_call_id on the ref
        tc_id = event.ref.tool_call_id
        if tc_id and tc_id not in valid_tc_ids:
            logger.warning("Clearing invalid tool_call_id %s on event %s", tc_id, event.event_id)
            tc_id = None

        # Rebuild ref from validated step_ids
        event.ref = StepRef(
            session_id=event.ref.session_id,
            start_step_id=valid_steps[0],
            end_step_id=valid_steps[-1] if len(valid_steps) > 1 else None,
            tool_call_id=tc_id,
        )

        validated.append(event)
    return validated


def _compute_mode_summary(events: list[FrictionEvent]) -> list[ModeSummary]:
    """Recompute mode_summary from validated events.

    Args:
        events: Validated friction events.

    Returns:
        Aggregated ModeSummary list sorted by count descending.
    """
    mode_events: dict[str, list[FrictionEvent]] = defaultdict(list)
    for event in events:
        mode_events[event.mode].append(event)

    summaries = []
    for mode, mode_evts in mode_events.items():
        total_steps = sum(e.estimated_cost.wasted_steps for e in mode_evts)
        total_time = sum(e.estimated_cost.wasted_time_seconds or 0 for e in mode_evts)
        total_tokens = sum(e.estimated_cost.wasted_tokens or 0 for e in mode_evts)
        avg_severity = sum(e.severity for e in mode_evts) / len(mode_evts)

        summaries.append(
            ModeSummary(
                mode=mode,
                count=len(mode_evts),
                affected_sessions=len({e.ref.session_id for e in mode_evts}),
                total_estimated_cost=FrictionCost(
                    wasted_steps=total_steps,
                    wasted_time_seconds=total_time or None,
                    wasted_tokens=total_tokens or None,
                ),
                avg_severity=round(avg_severity, 1),
            )
        )

    summaries.sort(key=lambda s: s.count, reverse=True)
    return summaries


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
