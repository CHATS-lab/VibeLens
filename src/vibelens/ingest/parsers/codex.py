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
from collections import OrderedDict
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import BaseParser, mark_error_content
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import (
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
)
from vibelens.utils import coerce_to_string, get_logger, parse_iso_timestamp

logger = get_logger(__name__)

# Skip "developer" role (system prompts, AGENTS.md injections, permission
# instructions) since they are boilerplate and not user-facing conversation.
RELEVANT_ROLES = {"user", "assistant"}

MAX_TOOL_RESULT_CACHE = 500

# Matches the metadata prefix Codex prepends to tool outputs:
#   Exit code: 0\nWall time: 1.23s\nOutput:\n<actual output>
_OUTPUT_PREFIX_RE = re.compile(
    r"^Exit code:\s*(\d+)\nWall time:.*?\nOutput:\n",
    re.DOTALL,
)

# ATIF source mapping for Codex role names
_ROLE_TO_SOURCE = {"user": StepSource.USER, "assistant": StepSource.AGENT}

AGENT_NAME = "codex"


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

        meta = _extract_session_meta(entries)
        fallback_id = Path(source_path).stem if source_path else str(uuid4())
        session_id = meta.get("id", fallback_id)
        steps = _build_steps(entries, session_id, collector)
        if not steps:
            return []

        project_path = meta.get("cwd") or None
        extra = _build_diagnostics_extra(collector)
        agent = self.build_agent(AGENT_NAME)
        return [self.assemble_trajectory(
            session_id=session_id,
            agent=agent,
            steps=steps,
            project_path=project_path,
            extra=extra,
        )]


def _build_diagnostics_extra(collector: DiagnosticsCollector) -> dict | None:
    """Build trajectory extra dict from diagnostics if there are issues."""
    has_issues = (
        collector.skipped_lines > 0
        or collector.orphaned_tool_calls > 0
        or collector.orphaned_tool_results > 0
    )
    if not has_issues:
        return None
    return {"diagnostics": collector.to_diagnostics().model_dump()}


def compute_session_tokens_max(steps: list[Step]) -> tuple[int, int]:
    """Compute session token totals using MAX strategy.

    Codex token_count events report cumulative per-turn totals, so
    summing them would double-count. Instead, take the maximum prompt
    and completion values seen across all steps.

    Args:
        steps: Parsed steps with optional metrics data.

    Returns:
        Tuple of (max_prompt_tokens, max_completion_tokens).
    """
    max_prompt = 0
    max_completion = 0
    for step in steps:
        if step.metrics:
            max_prompt = max(max_prompt, step.metrics.prompt_tokens)
            max_completion = max(max_completion, step.metrics.completion_tokens)
    return max_prompt, max_completion


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


def _extract_session_meta(entries: list[dict]) -> dict:
    """Extract session_meta payload from entries."""
    for entry in entries:
        if entry.get("type") == "session_meta":
            return entry.get("payload", {})
    return {}


def _collect_tool_outputs(
    entries: list[dict], diagnostics: DiagnosticsCollector | None = None
) -> OrderedDict[str, dict]:
    """Build a bounded call_id → result mapping from function_call_output entries.

    Uses an OrderedDict bounded at MAX_TOOL_RESULT_CACHE entries.
    """
    outputs: OrderedDict[str, dict] = OrderedDict()
    for entry in entries:
        if entry.get("type") != "response_item":
            continue
        payload = entry.get("payload", {})
        if payload.get("type") != "function_call_output":
            continue
        call_id = payload.get("call_id", "")
        if call_id:
            raw_output = payload.get("output", "")
            cleaned, has_error = _parse_structured_output(raw_output)
            outputs[call_id] = {
                "output": cleaned,
                "is_error": has_error,
            }
            if len(outputs) > MAX_TOOL_RESULT_CACHE:
                outputs.popitem(last=False)
            if diagnostics:
                diagnostics.record_tool_result()
    return outputs


def _build_steps(
    entries: list[dict],
    session_id: str,
    diagnostics: DiagnosticsCollector | None = None,
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
            continue

        if entry_type == "response_item":
            _handle_response_item(
                payload, timestamp, session_id, tool_outputs, steps, state,
            )
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
        source = _ROLE_TO_SOURCE.get(role, StepSource.USER)
        content_text = _extract_message_text(payload)
        steps.append(
            Step(
                step_id=str(uuid4()),
                source=source,
                message=content_text,
                model_name=(state.current_model or None) if role == "assistant" else None,
                timestamp=timestamp,
            )
        )

    elif payload_type == "function_call":
        call_id = payload.get("call_id", "")
        result = tool_outputs.get(call_id, {})
        state.pending_tools.append(
            ToolCall(
                tool_call_id=call_id,
                function_name=payload.get("name", "unknown"),
                arguments=_parse_arguments(payload.get("arguments", "")),
            )
        )
        # Buffer observation result for the tool output
        if result:
            content = result.get("output")
            if result.get("is_error", False):
                content = mark_error_content(content)
            state.pending_obs_results.append(
                ObservationResult(
                    source_call_id=call_id,
                    content=content,
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


def _parse_arguments(arguments: str) -> dict | str | None:
    """Parse function_call arguments JSON string.

    OpenAI serialises function_call arguments as a JSON *string* rather
    than an inline object.  We decode it back to a dict; if the JSON is
    malformed, return the raw string so no data is lost.
    """
    if not arguments:
        return None
    try:
        return json.loads(arguments)
    except json.JSONDecodeError:
        return arguments


def _parse_structured_output(raw: str) -> tuple[str, bool]:
    """Parse Codex structured tool output, stripping metadata prefix.

    Args:
        raw: Raw tool output string.

    Returns:
        Tuple of (cleaned_output, is_error).
    """
    if not raw:
        return "", False
    match = _OUTPUT_PREFIX_RE.match(raw)
    if not match:
        return raw, False
    exit_code = int(match.group(1))
    cleaned = raw[match.end():]
    return cleaned, exit_code != 0


def _parse_token_count(payload: dict) -> Metrics | None:
    """Parse token_count event_msg payload into Metrics.

    Accepts both old (``prompt_tokens``/``completion_tokens``) and new
    (``input_tokens``/``output_tokens``) field names.
    """
    info = payload.get("info", {})
    if not info:
        return None
    prompt_tokens = info.get("input_tokens", 0) or info.get("prompt_tokens", 0)
    completion_tokens = info.get("output_tokens", 0) or info.get("completion_tokens", 0)
    input_details = info.get("input_tokens_details", {}) or {}
    cached_tokens = input_details.get("cached_tokens", 0)
    if prompt_tokens == 0 and completion_tokens == 0 and cached_tokens == 0:
        return None
    return Metrics(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
    )
