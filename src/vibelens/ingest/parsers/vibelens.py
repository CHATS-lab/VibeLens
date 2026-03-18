"""VibeLens Export v1/v2 format parser.

Re-imports sessions previously exported via the VibeLens export
endpoint, reconstructing Trajectory objects from the VibeLens Export
JSON format.

Supports both v1 (old field names) and v2 (ATIF-aligned field names).
"""

import json

from vibelens.ingest.parsers.base import BaseParser, mark_error_content
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import (
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
    TrajectoryRef,
)
from vibelens.utils import get_logger
from vibelens.utils.timestamps import normalize_timestamp

logger = get_logger(__name__)

SUPPORTED_VERSIONS = {1, 2}

# ATIF source mapping for legacy v1 role names
_ROLE_TO_SOURCE = {"user": StepSource.USER, "assistant": StepSource.AGENT}

AGENT_NAME = "vibelens"


class VibeLensParser(BaseParser):
    """Parser for VibeLens Export v1/v2 JSON format.

    Reads JSON files produced by the VibeLens export serializer and
    reconstructs ATIF Trajectory objects. Supports both v1 (old names)
    and v2 (ATIF-aligned names) for backward compatibility.
    """

    def parse(self, content: str, source_path: str | None = None) -> list[Trajectory]:
        """Parse VibeLens export JSON content into Trajectory objects.

        Args:
            content: Raw JSON content string.
            source_path: Original file path (for error messages).

        Returns:
            List of Trajectory objects, or empty list on failure.

        Raises:
            ValueError: If vibelens_version is not supported.
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON in VibeLens export: %s", exc)
            return []

        if not isinstance(data, dict):
            return []

        version = data.get("vibelens_version")
        if version not in SUPPORTED_VERSIONS:
            raise ValueError(
                f"Unsupported vibelens_version {version}"
                f" (expected one of {SUPPORTED_VERSIONS})"
            )

        session_meta = data.get("session", {})
        session_id = session_meta.get("session_id", "")
        steps = _parse_steps(data, version)
        extra = _build_extra_from_session(session_meta, data)
        agent = self.build_agent(
            name=data.get("agent_format", AGENT_NAME),
        )

        main_trajectory = self.assemble_trajectory(
            session_id=session_id,
            agent=agent,
            steps=steps,
            extra=extra,
        )

        sub_trajectories = _parse_sub_trajectories(data, version, session_id, agent, self)

        return [main_trajectory, *sub_trajectories]


def _build_extra_from_session(session_meta: dict, data: dict) -> dict:
    """Build Trajectory.extra from the session metadata in the export.

    Args:
        session_meta: Session section from the export JSON.
        data: Full export JSON root.

    Returns:
        Dict of extra metadata.
    """
    extra: dict = {
        "source_type": "upload",
        "agent_format": data.get("agent_format", AGENT_NAME),
    }

    # v1 and v2 carry the same metadata keys in the session block
    extra.update({
        "project_id": session_meta.get("project_id", ""),
        "project_name": session_meta.get("project_name", ""),
        "first_message": session_meta.get("first_message", ""),
        "duration": session_meta.get("duration", 0),
        "models": session_meta.get("models", []),
        "tool_call_count": session_meta.get("tool_call_count", 0),
        "total_cache_write": session_meta.get("total_cache_write", 0),
    })

    timestamp = session_meta.get("timestamp")
    if timestamp:
        extra["timestamp"] = timestamp

    return extra


def _parse_steps(data: dict, version: int) -> list[Step]:
    """Reconstruct Step objects from export data.

    Handles both v1 (messages with old names) and v2 (steps with ATIF names).

    Args:
        data: Parsed export JSON root.
        version: Export format version.

    Returns:
        List of Step objects.
    """
    # v1 uses "messages" key, v2 uses "steps" key
    raw_items = data.get("steps" if version == 2 else "messages", [])
    steps: list[Step] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        step = _reconstruct_step(raw, version)
        steps.append(step)
    return steps


def _reconstruct_step(raw: dict, version: int) -> Step:
    """Reconstruct a single Step from export dict.

    Args:
        raw: Step/message dictionary from the export.
        version: Export format version.

    Returns:
        Step with defaults restored for omitted fields.
    """
    if version == 1:
        return _reconstruct_step_v1(raw)
    return _reconstruct_step_v2(raw)


def _reconstruct_step_v1(raw: dict) -> Step:
    """Reconstruct a Step from v1 export format (old field names)."""
    role = raw.get("role", "user")
    source = _ROLE_TO_SOURCE.get(role, StepSource.USER)
    timestamp = normalize_timestamp(raw.get("timestamp"))

    metrics = None
    raw_usage = raw.get("usage")
    if isinstance(raw_usage, dict):
        metrics = Metrics(
            prompt_tokens=raw_usage.get("input_tokens", 0),
            completion_tokens=raw_usage.get("output_tokens", 0),
            cached_tokens=raw_usage.get("cache_read_tokens", 0),
            cache_creation_tokens=raw_usage.get("cache_creation_tokens", 0),
        )

    tool_calls: list[ToolCall] = []
    obs_results: list[ObservationResult] = []
    raw_tools = raw.get("tool_calls", [])
    for tc_data in raw_tools:
        if not isinstance(tc_data, dict):
            continue
        tc = ToolCall(
            tool_call_id=tc_data.get("id", ""),
            function_name=tc_data.get("name", ""),
            arguments=tc_data.get("input"),
        )
        tool_calls.append(tc)
        # v1 stores output and is_error on the tool call itself
        output = tc_data.get("output")
        has_error = tc_data.get("is_error", False)
        if output is not None or has_error:
            content = mark_error_content(output) if has_error else output
            obs_results.append(
                ObservationResult(
                    source_call_id=tc_data.get("id", ""),
                    content=content,
                )
            )

    observation = Observation(results=obs_results) if obs_results else None

    # v1 content can be str or list of ContentBlock dicts
    content = raw.get("content", "")
    message = content if isinstance(content, str) else ""

    # Preserve parent_step_id in extra if present
    extra: dict | None = None
    parent_step_id = raw.get("parent_uuid", "")
    if parent_step_id:
        extra = {"parent_step_id": parent_step_id}

    return Step(
        step_id=raw.get("uuid", ""),
        source=source,
        message=message,
        reasoning_content=raw.get("thinking"),
        model_name=raw.get("model") or None,
        timestamp=timestamp,
        metrics=metrics,
        tool_calls=tool_calls,
        observation=observation,
        extra=extra,
    )


def _reconstruct_step_v2(raw: dict) -> Step:
    """Reconstruct a Step from v2 export format (ATIF-aligned names)."""
    timestamp = normalize_timestamp(raw.get("timestamp"))

    metrics = None
    raw_metrics = raw.get("metrics")
    if isinstance(raw_metrics, dict):
        metrics = Metrics(**raw_metrics)

    tool_calls: list[ToolCall] = []
    raw_tools = raw.get("tool_calls", [])
    for tc_data in raw_tools:
        if isinstance(tc_data, dict):
            tool_calls.append(ToolCall(**tc_data))

    observation = None
    raw_obs = raw.get("observation")
    if isinstance(raw_obs, dict):
        results = []
        for r in raw_obs.get("results", []):
            if isinstance(r, dict):
                results.append(ObservationResult(**r))
        observation = Observation(results=results) if results else None

    # Preserve parent_step_id in extra if present
    extra: dict | None = None
    parent_step_id = raw.get("parent_step_id", "")
    if parent_step_id:
        extra = {"parent_step_id": parent_step_id}

    return Step(
        step_id=raw.get("step_id", ""),
        source=raw.get("source", StepSource.USER),
        message=raw.get("message", ""),
        reasoning_content=raw.get("reasoning_content"),
        model_name=raw.get("model_name") or None,
        timestamp=timestamp,
        metrics=metrics,
        tool_calls=tool_calls,
        observation=observation,
        extra=extra,
    )


def _parse_sub_trajectories(
    data: dict, version: int, parent_sid: str, agent: object, parser: BaseParser
) -> list[Trajectory]:
    """Reconstruct sub-agent trajectories from export data.

    Each sub-session in the export becomes a separate Trajectory with
    parent_session_ref pointing back to the main session.

    Args:
        data: Parsed export JSON root.
        version: Export format version.
        parent_sid: Session ID of the parent trajectory.
        agent: Agent model for the trajectories.
        parser: Parser instance for assemble_trajectory.

    Returns:
        List of sub-agent Trajectory objects.
    """
    raw_subs = data.get("sub_sessions", [])
    trajectories: list[Trajectory] = []

    for raw in raw_subs:
        if not isinstance(raw, dict):
            continue
        _reconstruct_sub_trajectory(
            raw, version, parent_sid, agent, parser, trajectories
        )

    return trajectories


def _reconstruct_sub_trajectory(
    raw: dict,
    version: int,
    parent_sid: str,
    agent: object,
    parser: BaseParser,
    result_list: list[Trajectory],
) -> None:
    """Reconstruct a single sub-agent trajectory and its nested children.

    Args:
        raw: Sub-session dictionary from the export.
        version: Export format version.
        parent_sid: Session ID of the parent.
        agent: Agent model.
        parser: Parser instance.
        result_list: List to append trajectories to.
    """
    # v1 uses "messages" key, v2 uses "steps" key
    items_key = "steps" if version == 2 else "messages"
    steps: list[Step] = []
    for item_data in raw.get(items_key, []):
        if isinstance(item_data, dict):
            step = _reconstruct_step(item_data, version)
            steps.append(step)

    if not steps:
        return

    agent_id = raw.get("agent_id", "")
    parent_ref = TrajectoryRef(
        session_id=parent_sid,
        tool_call_id=raw.get("spawn_tool_call_id", "") or None,
    )

    sub_extra = {
        "source_type": "upload",
        "spawn_index": raw.get("spawn_index"),
    }

    result_list.append(
        parser.assemble_trajectory(
            session_id=agent_id,
            agent=agent,
            steps=steps,
            parent_trajectory_ref=TrajectoryRef(session_id=parent_sid),
            parent_ref=parent_ref,
            extra=sub_extra,
        )
    )

    # Recurse into nested sub-sessions
    for sub_data in raw.get("sub_sessions", []):
        if isinstance(sub_data, dict):
            _reconstruct_sub_trajectory(
                sub_data, version, agent_id, agent, parser, result_list
            )
