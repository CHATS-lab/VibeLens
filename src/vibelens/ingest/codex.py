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

from vibelens.ingest.base import BaseParser
from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.models.message import Message, TokenUsage, ToolCall
from vibelens.models.session import DataSourceType, SessionSummary
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


class _CodexParseState(BaseModel):
    """Mutable state carried across response_item processing."""

    pending_tools: list[ToolCall] = Field(
        default_factory=list, description="Tool calls buffered until the next message boundary."
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

    def parse_file(self, file_path: Path) -> list[tuple[SessionSummary, list[Message]]]:
        """Parse a Codex rollout JSONL file.

        Args:
            file_path: Path to a rollout-*.jsonl file.

        Returns:
            Single-element list of (SessionSummary, messages), or empty list.
        """
        if not file_path.exists():
            logger.warning("Rollout file not found: %s", file_path)
            return []

        collector = DiagnosticsCollector()
        entries = _load_rollout_entries(file_path, collector)
        if not entries:
            return []

        meta = _extract_session_meta(entries)
        session_id = meta.get("id", file_path.stem)
        messages = _build_messages(entries, session_id, collector)
        if not messages:
            return []
        self.enrich_tool_calls(messages)

        is_subagent = meta.get("source") == "sub_agent"
        if is_subagent:
            for msg in messages:
                msg.is_sidechain = True

        project_path = meta.get("cwd", "")
        start_time = parse_iso_timestamp(meta.get("timestamp"))
        first_message = self.find_first_user_text(messages)
        models = {m.model for m in messages if m.model}
        tool_call_count = sum(len(m.tool_calls) for m in messages)

        total_input, total_output = compute_session_tokens_max(messages)

        timestamps = [m.timestamp for m in messages if m.timestamp]
        duration = 0
        if len(timestamps) >= 2:
            duration = int((max(timestamps) - min(timestamps)).total_seconds())

        summary = SessionSummary(
            session_id=session_id,
            project_id=self.encode_project_path(project_path) if project_path else "",
            project_name=self.extract_project_name(project_path) if project_path else "",
            timestamp=start_time,
            duration=duration,
            message_count=len(messages),
            tool_call_count=tool_call_count,
            models=sorted(models),
            first_message=first_message,
            source_type=DataSourceType.LOCAL,
            diagnostics=collector.to_diagnostics(),
        )

        return [(summary, messages)]


def compute_session_tokens_max(messages: list[Message]) -> tuple[int, int]:
    """Compute session token totals using MAX strategy.

    Codex token_count events report cumulative per-turn totals, so
    summing them would double-count. Instead, take the maximum input
    and output values seen across all messages.

    Args:
        messages: Parsed messages with optional usage data.

    Returns:
        Tuple of (max_input_tokens, max_output_tokens).
    """
    max_input = 0
    max_output = 0
    for msg in messages:
        if msg.usage:
            max_input = max(max_input, msg.usage.input_tokens)
            max_output = max(max_output, msg.usage.output_tokens)
    return max_input, max_output


def _load_rollout_entries(
    file_path: Path, diagnostics: DiagnosticsCollector | None = None
) -> list[dict]:
    """Load all JSON entries from a rollout JSONL file."""
    return list(BaseParser.iter_jsonl_safe(file_path, diagnostics=diagnostics))


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
            cleaned, is_error = _parse_structured_output(raw_output)
            outputs[call_id] = {
                "output": cleaned,
                "is_error": is_error,
            }
            if len(outputs) > MAX_TOOL_RESULT_CACHE:
                outputs.popitem(last=False)
            if diagnostics:
                diagnostics.record_tool_result()
    return outputs


def _build_messages(
    entries: list[dict],
    session_id: str,
    diagnostics: DiagnosticsCollector | None = None,
) -> list[Message]:
    """Build Message objects from rollout entries.

    Extracts user/assistant messages from response_item entries,
    attaches tool calls from function_call/function_call_output pairs,
    and parses token usage from event_msg token_count entries.

    Args:
        entries: Parsed JSON entries from rollout JSONL.
        session_id: Session identifier from session_meta.
        diagnostics: Optional collector for parse quality metrics.

    Returns:
        Ordered list of Message objects.
    """
    tool_outputs = _collect_tool_outputs(entries, diagnostics)
    messages: list[Message] = []
    state = _CodexParseState()

    for entry in entries:
        entry_type = entry.get("type", "")
        # Codex rollout timestamps are ISO-8601 strings (not ms-epoch).
        timestamp = parse_iso_timestamp(entry.get("timestamp"))
        payload = entry.get("payload", {})

        if entry_type == "turn_context":
            state.current_model = payload.get("model", state.current_model)
            continue

        if entry_type == "response_item":
            _handle_response_item(
                payload, timestamp, session_id,
                tool_outputs, messages, state,
            )
            continue

        # token_count events carry per-turn usage stats from the OpenAI API;
        # attach to the most recent assistant message for per-message accounting.
        if entry_type == "event_msg" and payload.get("type") == "token_count":
            usage = _parse_token_count(payload)
            if usage:
                _attach_usage_to_last_assistant(messages, usage)

    # Flush any trailing tool calls / thinking from the last assistant turn.
    _flush_pending(messages, state)
    return messages


def _handle_response_item(
    payload: dict,
    timestamp,
    session_id: str,
    tool_outputs: dict[str, dict],
    messages: list[Message],
    state: _CodexParseState,
) -> None:
    """Process a single response_item entry."""
    payload_type = payload.get("type", "")

    if payload_type == "message":
        role = payload.get("role", "")
        if role not in RELEVANT_ROLES:
            return
        # A new message boundary: flush any tool calls / thinking buffered
        # from the preceding assistant turn before creating the next message.
        _flush_pending(messages, state)
        content_text = _extract_message_text(payload)
        messages.append(
            Message(
                uuid=str(uuid4()),
                session_id=session_id,
                role=role,
                type=role,
                content=content_text,
                model=state.current_model if role == "assistant" else "",
                timestamp=timestamp,
            )
        )

    elif payload_type == "function_call":
        call_id = payload.get("call_id", "")
        result = tool_outputs.get(call_id, {})
        state.pending_tools.append(
            ToolCall(
                id=call_id,
                name=payload.get("name", "unknown"),
                input=_parse_arguments(payload.get("arguments", "")),
                output=result.get("output"),
                is_error=result.get("is_error", False),
            )
        )

    elif payload_type == "reasoning":
        # Codex reasoning entries contain summary[].text blocks with the
        # model's chain-of-thought.  Deduplicate by content hash since
        # Codex sometimes emits duplicate reasoning blocks.
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


def _flush_pending(messages: list[Message], state: _CodexParseState) -> None:
    """Attach pending tool calls and thinking to the last assistant message."""
    if not state.pending_tools and not state.pending_thinking:
        return
    for msg in reversed(messages):
        if msg.role == "assistant":
            if state.pending_tools:
                msg.tool_calls.extend(state.pending_tools)
            if state.pending_thinking:
                existing = msg.thinking or ""
                new_thinking = "\n".join(state.pending_thinking)
                msg.thinking = f"{existing}\n{new_thinking}".strip() if existing else new_thinking
            break
    state.pending_tools.clear()
    state.pending_thinking.clear()


def _attach_usage_to_last_assistant(messages: list[Message], usage: TokenUsage) -> None:
    """Attach token usage to the last assistant message lacking usage data."""
    for msg in reversed(messages):
        if msg.role == "assistant" and not msg.usage:
            msg.usage = usage
            return


def _extract_message_text(payload: dict) -> str:
    """Extract plain text from a response_item message payload.

    Codex uses ``input_text`` for user messages and ``output_text`` for
    assistant messages (following the OpenAI Responses API content types),
    unlike Claude Code's uniform ``text`` type.
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
    malformed (rare but possible in streaming), return the raw string so
    no data is lost.
    """
    if not arguments:
        return None
    try:
        return json.loads(arguments)
    except json.JSONDecodeError:
        return arguments


def _parse_structured_output(raw: str) -> tuple[str, bool]:
    """Parse Codex structured tool output, stripping metadata prefix.

    Codex tool outputs follow the pattern
    ``Exit code: N\\nWall time: ...\\nOutput:\\n<actual output>``.
    Strips the metadata prefix and returns just the actual output,
    preserving exit code as an error flag.

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


def _parse_token_count(payload: dict) -> TokenUsage | None:
    """Parse token_count event_msg payload into TokenUsage.

    The ``info`` sub-object mirrors the OpenAI API usage response, which
    has evolved over time: older versions used ``prompt_tokens`` /
    ``completion_tokens``, newer ones use ``input_tokens`` / ``output_tokens``.
    We accept both to handle rollouts from different CLI versions.
    Cached token counts are nested inside ``input_tokens_details``.
    """
    info = payload.get("info", {})
    if not info:
        return None
    input_tokens = info.get("input_tokens", 0) or info.get("prompt_tokens", 0)
    output_tokens = info.get("output_tokens", 0) or info.get("completion_tokens", 0)
    input_details = info.get("input_tokens_details", {}) or {}
    cached_tokens = input_details.get("cached_tokens", 0)
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cached_tokens,
    )
