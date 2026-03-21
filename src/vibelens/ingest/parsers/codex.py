"""Codex CLI rollout JSONL format parser.

Parses ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl files containing
Codex CLI session data with session_meta, response_item, turn_context,
and event_msg entries.

Codex uses the OpenAI Responses API convention where each JSONL line is
a ``RolloutItem`` envelope with ``{timestamp, type, payload}``.  Unlike
Claude Code, tool invocations are *separate* ``response_item`` entries
(``function_call`` + ``function_call_output`` linked by ``call_id``)
rather than content blocks embedded in the assistant message.  This
requires a two-pass approach: first collect all tool outputs by call_id,
then attach them to the assistant message that preceded them.

The rollout also has a ``turn_context`` entry per turn carrying the
active model name, which can change mid-session (e.g. switching between
gpt-5.4 and a lighter model), so model tracking is per-turn rather than
per-session.
"""

import hashlib
import json
import re
import sqlite3
from collections import OrderedDict
from pathlib import Path
from typing import NamedTuple
from uuid import uuid4

from pydantic import BaseModel, Field

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import (
    _SYSTEM_TAG_PREFIXES,
    ROLE_TO_SOURCE,
    BaseParser,
    mark_error_content,
)
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import (
    FinalMetrics,
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
    TrajectoryRef,
)
from vibelens.utils import coerce_to_string, get_logger, normalize_timestamp, parse_iso_timestamp

logger = get_logger(__name__)

# Skip "developer" role (system prompts, AGENTS.md injections, permission
# instructions) since they are boilerplate and not user-facing conversation.
RELEVANT_ROLES = {"user", "assistant"}

MAX_TOOL_RESULT_CACHE = 500

# Matches the metadata prefix Codex prepends to tool outputs:
#   Exit code: 0\nWall time: 1.23s\nOutput:\n<actual output>
_OUTPUT_PREFIX_RE = re.compile(
    r"^Exit code:\s*(\d+)\nWall time:\s*([0-9.]+)s?\nOutput:\n", re.DOTALL
)

# Tool output types that carry results linked by call_id
_TOOL_OUTPUT_TYPES = {"function_call_output", "custom_tool_call_output"}

# Tool call types that initiate tool invocations
_TOOL_CALL_TYPES = {"function_call", "custom_tool_call"}


class _CodexSessionMeta(NamedTuple):
    """Aggregated metadata from a single pass over raw JSONL content."""

    session_id: str | None
    cli_version: str | None
    model_name: str | None
    project_path: str | None
    source: str | None
    originator: str | None
    effort: str | None
    sandbox_policy: str | None
    approval_policy: str | None
    forked_from_id: str | None


class _CodexParseState(BaseModel):
    """Mutable state carried across response_item processing.

    Codex emits tool calls and reasoning as separate JSONL entries
    *between* message entries, with no explicit end-of-turn marker.
    We buffer them here and flush to the preceding agent step
    when the next message boundary arrives (or at end-of-file).
    """

    pending_tools: list[ToolCall] = Field(
        default_factory=list, description="Tool calls buffered until the next message boundary."
    )
    pending_obs_results: list[ObservationResult] = Field(
        default_factory=list, description="Observation results buffered for the preceding step."
    )
    current_model: str = Field(
        default="", description="Active model name from the most recent turn_context."
    )
    current_cwd: str = Field(
        default="", description="Working directory from the most recent turn_context."
    )
    current_effort: str = Field(
        default="", description="Reasoning effort from the most recent turn_context."
    )
    pending_thinking: list[str] = Field(
        default_factory=list, description="Reasoning text blocks buffered for attachment."
    )
    thinking_seen: set[str] = Field(
        default_factory=set, description="MD5 hashes of reasoning blocks seen for deduplication."
    )


class CodexParser(BaseParser):
    """Parser for Codex CLI's native rollout JSONL format.

    Handles rollout files containing session_meta, response_item,
    turn_context, and event_msg entries.
    """

    AGENT_NAME = "codex"
    LOCAL_DATA_DIR: Path | None = Path.home() / ".codex"

    def parse(self, content: str, source_path: str | None = None) -> list[Trajectory]:
        """Parse Codex rollout JSONL content into a Trajectory.

        Args:
            content: Raw JSONL content string.
            source_path: Original file path (used for session ID fallback).

        Returns:
            Single-element list with the Trajectory, or empty list.
        """
        collector = DiagnosticsCollector()
        entries = _load_rollout_content(content, collector)
        if not entries:
            return []

        meta = _scan_session_metadata(entries)
        fallback_id = Path(source_path).stem if source_path else str(uuid4())
        session_id = meta.session_id or fallback_id
        steps = _build_steps(entries, session_id, collector)
        if not steps:
            return []

        agent = self.build_agent(version=meta.cli_version, model=meta.model_name)

        extra = self.build_diagnostics_extra(collector)

        total_usage = _extract_final_token_usage(entries)
        if total_usage:
            extra = extra or {}
            extra["total_token_usage"] = total_usage

        session_extra = _build_session_extra(meta)
        if session_extra:
            extra = extra or {}
            extra.update(session_extra)

        parent_ref = None
        if meta.forked_from_id:
            parent_ref = TrajectoryRef(session_id=meta.forked_from_id)

        return [
            self.assemble_trajectory(
                session_id=session_id,
                agent=agent,
                steps=steps,
                project_path=meta.project_path,
                parent_trajectory_ref=parent_ref,
                extra=extra,
            )
        ]

    def parse_session_index(self, data_dir: Path) -> list[Trajectory]:
        """Build skeleton trajectories from Codex SQLite index.

        Reads ~/.codex/state_5.sqlite threads table for fast listing
        without parsing individual rollout files.

        Args:
            data_dir: Path to the Codex data directory (~/.codex).

        Returns:
            List of skeleton Trajectory objects (no steps).
        """
        db_path = data_dir / "state_5.sqlite"
        if not db_path.exists():
            return []

        trajectories: list[Trajectory] = []
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, rollout_path, created_at, source, cwd, "
                "title, tokens_used, model, first_user_message, cli_version "
                "FROM threads"
            )
            for row in cursor:
                traj = self._build_skeleton_from_row(row)
                if traj:
                    trajectories.append(traj)
            conn.close()
        except (sqlite3.Error, OSError) as exc:
            logger.warning("Failed to read Codex SQLite index: %s", exc)
            return []

        logger.info("Codex SQLite index: %d sessions", len(trajectories))
        return trajectories

    def _build_skeleton_from_row(self, row: sqlite3.Row) -> Trajectory | None:
        """Build a skeleton Trajectory from a SQLite threads row.

        Args:
            row: sqlite3.Row with columns from the threads table.

        Returns:
            Skeleton Trajectory, or None if row lacks a valid id.
        """
        session_id = row["id"]
        if not session_id:
            return None

        # Sub-agent threads have a JSON source with "subagent" key —
        # skip them so they only appear as children of their parent.
        source_val = row["source"] or ""
        if source_val.startswith("{") and "subagent" in source_val:
            return None

        timestamp = normalize_timestamp(row["created_at"])
        agent = self.build_agent(
            version=row["cli_version"],
            model=row["model"],
        )

        first_message = row["first_user_message"]
        if first_message:
            first_message = self.truncate_first_message(first_message)

        # Skeleton step so Trajectory validation passes (min_length=1)
        skeleton_step = Step(
            step_id="index-0",
            source=StepSource.USER,
            message=first_message or "",
            timestamp=timestamp,
        )

        tokens_used = row["tokens_used"] or 0
        final_metrics = FinalMetrics(
            total_prompt_tokens=tokens_used,
            total_completion_tokens=0,
            total_steps=0,
            tool_call_count=0,
            duration=0,
            total_cache_write=0,
            total_cache_read=0,
        )

        extra: dict = {"is_skeleton": True}
        if row["rollout_path"]:
            extra["rollout_path"] = row["rollout_path"]
        if row["source"]:
            extra["source"] = row["source"]
        if row["title"]:
            extra["title"] = row["title"]

        return Trajectory(
            session_id=session_id,
            project_path=row["cwd"],
            timestamp=timestamp,
            first_message=first_message,
            agent=agent,
            steps=[skeleton_step],
            final_metrics=final_metrics,
            extra=extra,
        )


def _load_rollout_content(
    content: str, diagnostics: DiagnosticsCollector | None = None
) -> list[dict]:
    """Parse JSONL content string into entry dicts."""
    entries = []
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if diagnostics:
            diagnostics.total_lines += 1
        try:
            entries.append(json.loads(stripped))
            if diagnostics:
                diagnostics.parsed_lines += 1
        except json.JSONDecodeError:
            if diagnostics:
                diagnostics.record_skip("invalid JSON")
    return entries


def _scan_session_metadata(entries: list[dict]) -> _CodexSessionMeta:
    """Extract session metadata from a single pass over entries.

    Collects fields from:
    - ``session_meta.payload``: id, cli_version, cwd, source, originator
    - First ``turn_context.payload``: model, effort, sandbox_policy, approval_policy

    Args:
        entries: Parsed JSONL entries.

    Returns:
        Populated _CodexSessionMeta.
    """
    session_id: str | None = None
    cli_version: str | None = None
    model_name: str | None = None
    project_path: str | None = None
    source: str | None = None
    originator: str | None = None
    effort: str | None = None
    sandbox_policy: str | None = None
    approval_policy: str | None = None
    forked_from_id: str | None = None
    found_session_meta = False
    found_turn_context = False

    for entry in entries:
        entry_type = entry.get("type", "")
        payload = entry.get("payload", {})

        # Sub-agent rollouts contain two session_meta entries: the child
        # (this rollout) and the parent (forked-from context). Only use
        # the first one to avoid session_id collisions.
        if entry_type == "session_meta" and not found_session_meta:
            found_session_meta = True
            session_id = payload.get("id") or None
            cli_version = payload.get("cli_version") or None
            project_path = payload.get("cwd") or None
            source = payload.get("source") or None
            originator = payload.get("originator") or None
            forked_from_id = payload.get("forked_from_id") or None

        elif entry_type == "turn_context" and not found_turn_context:
            found_turn_context = True
            model_name = payload.get("model") or None
            effort = payload.get("reasoning_effort") or payload.get("effort") or None
            sandbox_policy = payload.get("sandbox") or payload.get("sandbox_policy") or None
            approval_policy = payload.get("approval_policy") or None

    return _CodexSessionMeta(
        session_id=session_id,
        cli_version=cli_version,
        model_name=model_name,
        project_path=project_path,
        source=source,
        originator=originator,
        effort=effort,
        sandbox_policy=sandbox_policy,
        approval_policy=approval_policy,
        forked_from_id=forked_from_id,
    )


def _build_session_extra(meta: _CodexSessionMeta) -> dict | None:
    """Build trajectory-level extra dict from session metadata.

    Args:
        meta: Scanned session metadata.

    Returns:
        Dict with non-None metadata fields, or None if all empty.
    """
    pairs = [
        ("source", meta.source),
        ("originator", meta.originator),
        ("reasoning_effort", meta.effort),
        ("sandbox_policy", meta.sandbox_policy),
        ("approval_policy", meta.approval_policy),
    ]
    extra = {k: v for k, v in pairs if v}
    return extra or None


def _collect_tool_outputs(
    entries: list[dict], diagnostics: DiagnosticsCollector | None = None
) -> OrderedDict[str, dict]:
    """Build a bounded call_id -> result mapping from tool output entries.

    Handles both ``function_call_output`` and ``custom_tool_call_output``.
    Uses an OrderedDict bounded at MAX_TOOL_RESULT_CACHE entries.
    """
    outputs: OrderedDict[str, dict] = OrderedDict()
    for entry in entries:
        if entry.get("type") != "response_item":
            continue
        payload = entry.get("payload", {})
        if payload.get("type") not in _TOOL_OUTPUT_TYPES:
            continue
        call_id = payload.get("call_id", "")
        if call_id:
            raw_output = payload.get("output", "")
            cleaned, has_error, metadata = _parse_structured_output(raw_output)
            outputs[call_id] = {
                "output": cleaned,
                "is_error": has_error,
                "metadata": metadata,
            }
            if len(outputs) > MAX_TOOL_RESULT_CACHE:
                outputs.popitem(last=False)
            if diagnostics:
                diagnostics.record_tool_result()
    return outputs


def _build_steps(
    entries: list[dict], session_id: str, diagnostics: DiagnosticsCollector | None = None
) -> list[Step]:
    """Build Step objects from rollout entries.

    Args:
        entries: Parsed JSON entries from rollout JSONL.
        session_id: Session identifier from session_meta.
        diagnostics: Optional collector for parse quality metrics.

    Returns:
        Ordered list of Step objects.
    """
    tool_outputs = _collect_tool_outputs(entries, diagnostics)
    steps: list[Step] = []
    state = _CodexParseState()

    for entry in entries:
        entry_type = entry.get("type", "")
        timestamp = parse_iso_timestamp(entry.get("timestamp"))
        payload = entry.get("payload", {})

        if entry_type == "turn_context":
            state.current_model = payload.get("model", state.current_model)
            state.current_cwd = payload.get("cwd", state.current_cwd)
            effort = payload.get("reasoning_effort") or payload.get("effort") or ""
            if effort:
                state.current_effort = effort
            continue

        if entry_type == "response_item":
            _handle_response_item(payload, timestamp, session_id, tool_outputs, steps, state)
            continue

        # token_count events carry per-turn usage stats from the OpenAI API;
        # attach to the most recent agent step for per-step accounting.
        if entry_type == "event_msg" and payload.get("type") == "token_count":
            metrics = _parse_token_count(payload)
            if metrics:
                _attach_metrics_to_last_agent(steps, metrics)

    # Flush any trailing tool calls / thinking from the last agent turn.
    _flush_pending(steps, state)
    return steps


def _build_step_extra(state: _CodexParseState) -> dict | None:
    """Build step-level extra dict from current parse state.

    Args:
        state: Current parse state with cwd and effort.

    Returns:
        Dict with non-empty fields, or None if all empty.
    """
    extra: dict = {}
    if state.current_cwd:
        extra["cwd"] = state.current_cwd
    if state.current_effort:
        extra["reasoning_effort"] = state.current_effort
    return extra or None


def _handle_response_item(
    payload: dict,
    timestamp,
    session_id: str,
    tool_outputs: dict[str, dict],
    steps: list[Step],
    state: _CodexParseState,
) -> None:
    """Process a single response_item entry."""
    payload_type = payload.get("type", "")

    if payload_type == "message":
        role = payload.get("role", "")
        if role not in RELEVANT_ROLES:
            return
        # A new message boundary: flush any tool calls / thinking buffered
        # from the preceding agent turn before creating the next step.
        _flush_pending(steps, state)
        content_text = _extract_message_text(payload)
        source = ROLE_TO_SOURCE.get(role, StepSource.USER)
        # Reclassify agent-injected context (e.g. <environment_context>)
        # that arrives as role=user but is system boilerplate.
        if source == StepSource.USER and content_text.lstrip().startswith(_SYSTEM_TAG_PREFIXES):
            source = StepSource.SYSTEM
        extra = _build_step_extra(state) if role == "assistant" else None
        status = payload.get("status")
        if status and extra is not None:
            extra["status"] = status
        elif status:
            extra = {"status": status}
        steps.append(
            Step(
                step_id=str(uuid4()),
                source=source,
                message=content_text,
                model_name=(state.current_model or None) if role == "assistant" else None,
                timestamp=timestamp,
                extra=extra,
            )
        )

    elif payload_type in _TOOL_CALL_TYPES:
        call_id = payload.get("call_id", "")
        # custom_tool_call uses "input" for arguments, function_call uses "arguments"
        raw_args = payload.get("arguments", "") or payload.get("input", "")
        result = tool_outputs.get(call_id, {})
        state.pending_tools.append(
            ToolCall(
                tool_call_id=call_id,
                function_name=payload.get("name", "unknown"),
                arguments=_parse_arguments(raw_args),
            )
        )
        # Buffer observation result for the tool output
        if result:
            content = result.get("output")
            if result.get("is_error", False):
                content = mark_error_content(content)
            obs_extra = result.get("metadata")
            state.pending_obs_results.append(
                ObservationResult(
                    source_call_id=call_id,
                    content=content,
                    extra=obs_extra,
                )
            )

    elif payload_type == "reasoning":
        # Codex reasoning entries contain summary[].text blocks with the
        # model's chain-of-thought.  Deduplicate by content hash because
        # Codex streaming recovery can re-emit identical reasoning blocks.
        summary_items = payload.get("summary", [])
        for item in summary_items:
            if not isinstance(item, dict):
                continue
            text = item.get("text", "")
            if not text:
                continue
            content_hash = hashlib.md5(text.encode()).hexdigest()
            if content_hash not in state.thinking_seen:
                state.thinking_seen.add(content_hash)
                state.pending_thinking.append(text)


def _flush_pending(steps: list[Step], state: _CodexParseState) -> None:
    """Attach pending tool calls, observations, and thinking to the last agent step."""
    if not state.pending_tools and not state.pending_thinking:
        return
    for step in reversed(steps):
        if step.source == StepSource.AGENT:
            if state.pending_tools:
                step.tool_calls.extend(state.pending_tools)
            if state.pending_obs_results:
                if step.observation is None:
                    step.observation = Observation(results=[])
                step.observation.results.extend(state.pending_obs_results)
            if state.pending_thinking:
                existing = step.reasoning_content or ""
                new_thinking = "\n".join(state.pending_thinking)
                step.reasoning_content = (
                    f"{existing}\n{new_thinking}".strip() if existing else new_thinking
                )
            break
    state.pending_tools.clear()
    state.pending_obs_results.clear()
    state.pending_thinking.clear()


def _attach_metrics_to_last_agent(steps: list[Step], metrics: Metrics) -> None:
    """Attach token metrics to the last agent step lacking metrics data."""
    for step in reversed(steps):
        if step.source == StepSource.AGENT and not step.metrics:
            step.metrics = metrics
            return


def _extract_message_text(payload: dict) -> str:
    """Extract plain text from a response_item message payload.

    Codex uses ``input_text`` for user messages and ``output_text`` for
    assistant messages (following the OpenAI Responses API content types).
    """
    content = payload.get("content", [])
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return coerce_to_string(content)
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") in ("input_text", "output_text"):
            text = block.get("text", "")
            if text:
                parts.append(text)
    return "\n".join(parts)


def _parse_arguments(arguments: str | dict) -> dict | str | None:
    """Parse function_call arguments JSON string.

    OpenAI serialises function_call arguments as a JSON *string* rather
    than an inline object.  custom_tool_call may pass arguments as a dict
    directly.  We decode strings back to dicts; if the JSON is malformed,
    return the raw string so no data is lost.
    """
    if not arguments:
        return None
    if isinstance(arguments, dict):
        return arguments
    try:
        return json.loads(arguments)
    except (json.JSONDecodeError, TypeError):
        return arguments


def _parse_structured_output(raw: str) -> tuple[str, bool, dict | None]:
    """Parse Codex structured tool output, stripping metadata prefix.

    Args:
        raw: Raw tool output string.

    Returns:
        Tuple of (cleaned_output, is_error, metadata).
        metadata contains exit_code and wall_time_sec when the prefix is present.
    """
    if not raw:
        return "", False, None
    match = _OUTPUT_PREFIX_RE.match(raw)
    if not match:
        return raw, False, None
    exit_code = int(match.group(1))
    wall_time_sec = float(match.group(2))
    cleaned = raw[match.end() :]
    metadata = {"exit_code": exit_code, "wall_time_sec": wall_time_sec}
    return cleaned, exit_code != 0, metadata


def _parse_token_count(payload: dict) -> Metrics | None:
    """Parse token_count event_msg payload into Metrics.

    Per-turn usage is nested under ``info.last_token_usage``; falls back
    to top-level ``info`` fields for older formats. Accepts both old
    (``prompt_tokens``/``completion_tokens``) and new
    (``input_tokens``/``output_tokens``) field names.
    """
    info = payload.get("info", {})
    if not info:
        return None

    # Per-turn usage is nested under last_token_usage; fall back to
    # top-level fields for older formats.
    usage = info.get("last_token_usage") or info

    input_tokens = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)

    cached_tokens = usage.get("cached_input_tokens", 0)
    if not cached_tokens:
        input_details = usage.get("input_tokens_details", {}) or {}
        cached_tokens = input_details.get("cached_tokens", 0)

    prompt_tokens = input_tokens + cached_tokens

    if prompt_tokens == 0 and completion_tokens == 0:
        return None

    reasoning_tokens = usage.get("reasoning_output_tokens", 0)
    metrics_extra = {"reasoning_output_tokens": reasoning_tokens} if reasoning_tokens else None

    return Metrics(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
        extra=metrics_extra,
    )


def _extract_final_token_usage(entries: list[dict]) -> dict | None:
    """Extract cumulative total_token_usage from the last token_count event.

    Codex includes a ``total_token_usage`` block in token_count events
    that represents the cumulative usage across the entire session.

    Args:
        entries: Parsed JSONL entries.

    Returns:
        The total_token_usage dict, or None if not found.
    """
    for entry in reversed(entries):
        if entry.get("type") != "event_msg":
            continue
        payload = entry.get("payload", {})
        if payload.get("type") != "token_count":
            continue
        info = payload.get("info", {})
        total_usage = info.get("total_token_usage")
        if isinstance(total_usage, dict) and total_usage:
            return total_usage
    return None
