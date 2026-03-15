"""Claude Code JSONL format parser.

Parses ~/.claude/history.jsonl for session indices and individual
session .jsonl files for full conversation data, including subagent
conversations stored in {session-id}/subagents/ directories.

Claude Code stores each conversation event as a separate JSONL line with
a top-level ``type`` field (``"user"`` or ``"assistant"``).  Tool use
follows the Anthropic Messages API convention: tool invocations appear
as ``tool_use`` content blocks inside assistant messages, while their
results come back as ``tool_result`` blocks inside the *next* user
message, linked by ``tool_use_id``.  This two-message pairing requires
a pre-scan to build the result map before constructing ToolCall objects.
"""

import json
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from vibelens.ingest.base import BaseParser
from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.models.message import (
    ContentBlock,
    Message,
    SubAgentSession,
    TokenUsage,
    ToolCall,
)
from vibelens.models.session import SessionMetadata, SessionSummary
from vibelens.utils import coerce_to_string, get_logger, parse_ms_timestamp

# Sentinel for sorting messages that lack timestamps — placed before all
# real timestamps so they don't disrupt chronological ordering.
_EPOCH_MIN = datetime.min.replace(tzinfo=UTC)

logger = get_logger(__name__)

# Tool results almost always appear adjacent to their tool_use blocks.
# A bounded cache avoids doubling memory for large sessions.
MAX_TOOL_RESULT_CACHE = 500

# Only "user" and "assistant" carry conversation content.
# Other types (e.g. "result") are internal bookkeeping and skipped.
RELEVANT_TYPES = {"user", "assistant"}


class ClaudeCodeParser(BaseParser):
    """Parser for Claude Code's native JSONL format.

    Handles both the history index (history.jsonl) and individual
    session files, including subagent conversations.
    """

    def parse_file(self, file_path: Path) -> list[tuple[SessionSummary, list[Message]]]:
        """Parse a session JSONL file into a (summary, messages) pair.

        Args:
            file_path: Path to a session .jsonl file.

        Returns:
            Single-element list of (SessionSummary, messages).
        """
        collector = DiagnosticsCollector()
        messages, sub_sessions = self.parse_session_with_subagents(
            file_path, diagnostics=collector
        )
        if not messages:
            return []
        self.enrich_tool_calls(messages)
        for sub in sub_sessions:
            self.enrich_tool_calls(sub.messages)
        metadata = self.compute_session_metadata(messages)
        session_id = file_path.stem
        summary = SessionSummary(
            session_id=session_id,
            message_count=metadata.message_count,
            first_message=metadata.first_message,
            diagnostics=collector.to_diagnostics(),
        )
        return [(summary, messages)]

    def parse_history_index(
        self,
        claude_dir: Path,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[SessionSummary]:
        """Parse history.jsonl to build a session summary list.

        Groups entries by sessionId, extracts project name, first message,
        timestamp, and message count per session.

        Args:
            claude_dir: Path to ~/.claude directory.
            since: Only include sessions with activity at or after this time.
            limit: Maximum number of sessions to return (after sorting).

        Returns:
            List of SessionSummary objects sorted by timestamp descending.
        """
        history_file = claude_dir / "history.jsonl"
        if not history_file.exists():
            logger.warning("history.jsonl not found at %s", history_file)
            return []

        since_ms = int(since.timestamp() * 1000) if since else 0

        sessions = _aggregate_history_lines(history_file, since_ms)

        summaries = []
        for session_id, data in sessions.items():
            project_path = data["project_path"]
            project_name = self.extract_project_name(project_path)
            project_id = self.encode_project_path(project_path)
            first_message = self.truncate_first_message(data["first_message"])
            timestamp = datetime.fromtimestamp(data["last_timestamp"] / 1000, tz=UTC)

            summaries.append(
                SessionSummary(
                    session_id=session_id,
                    project_id=project_id,
                    project_name=project_name,
                    timestamp=timestamp,
                    message_count=data["message_count"],
                    first_message=first_message,
                    source_type="local",
                )
            )

        summaries.sort(key=lambda s: s.timestamp or _EPOCH_MIN, reverse=True)
        if limit is not None:
            summaries = summaries[:limit]
        return summaries

    def parse_session_jsonl(self, file_path: Path) -> list[Message]:
        """Parse a session .jsonl file into main-session messages only.

        Args:
            file_path: Path to the session .jsonl file.

        Returns:
            List of Message objects for the main session (no sub-agents).
        """
        return self._parse_single_jsonl(file_path)

    def parse_session_with_subagents(
        self,
        file_path: Path,
        diagnostics: DiagnosticsCollector | None = None,
    ) -> tuple[list[Message], list[SubAgentSession]]:
        """Parse a session file and its sub-agent conversations separately.

        Sub-agent messages are NOT merged into the main message list.
        Instead they are returned as ``SubAgentSession`` objects that
        preserve the cascade hierarchy.  Each sub-agent records which
        parent message spawned it via ``spawn_index``.

        Args:
            file_path: Path to the session .jsonl file.
            diagnostics: Optional collector for parse quality metrics.

        Returns:
            Tuple of (main_messages, sub_sessions).
        """
        messages = self._parse_single_jsonl(file_path, diagnostics=diagnostics)
        sub_sessions = self._parse_subagent_dir(file_path, messages)
        return messages, sub_sessions

    def _parse_subagent_dir(
        self, file_path: Path, parent_messages: list[Message]
    ) -> list[SubAgentSession]:
        """Parse sub-agent JSONL files into SubAgentSession objects.

        Matches each sub-agent to the parent message that spawned it
        by finding Agent tool_calls ordered chronologically.

        Args:
            file_path: Path to the main session .jsonl file.
            parent_messages: Parsed messages from the main session.

        Returns:
            List of SubAgentSession objects with spawn_index populated.
        """
        subagent_dir = file_path.parent / file_path.stem / "subagents"
        if not subagent_dir.is_dir():
            return []

        agent_files = sorted(subagent_dir.glob("agent-*.jsonl"))
        if not agent_files:
            return []

        agent_spawn_points = _find_agent_spawn_points(parent_messages)
        sub_sessions: list[SubAgentSession] = []

        for idx, agent_file in enumerate(agent_files):
            agent_id = agent_file.stem
            sub_messages = self._parse_single_jsonl(agent_file)
            for msg in sub_messages:
                msg.is_sidechain = True

            spawn_index = None
            spawn_tool_call_id = ""
            if idx < len(agent_spawn_points):
                spawn_index, spawn_tool_call_id = agent_spawn_points[idx]

            sub_sessions.append(
                SubAgentSession(
                    agent_id=agent_id,
                    spawn_index=spawn_index,
                    spawn_tool_call_id=spawn_tool_call_id,
                    messages=sub_messages,
                )
            )

        return sub_sessions

    @staticmethod
    def discover_subagent_only_sessions(project_dir: Path) -> list[Path]:
        """Find session dirs that have only subagent files and no root JSONL.

        Dataclaw handles these orphaned subagent sessions; VibeLens should
        detect them so they can be surfaced or merged upstream.

        Args:
            project_dir: Directory containing session subdirectories.

        Returns:
            List of subagent directory paths without a root JSONL file.
        """
        orphaned = []
        try:
            for subagent_dir in project_dir.glob("*/subagents"):
                if not subagent_dir.is_dir():
                    continue
                session_dir = subagent_dir.parent
                root_jsonl = session_dir.parent / f"{session_dir.name}.jsonl"
                if not root_jsonl.exists() and list(subagent_dir.glob("agent-*.jsonl")):
                    orphaned.append(subagent_dir)
        except OSError:
            pass
        return orphaned

    def compute_session_metadata(self, messages: list[Message]) -> SessionMetadata:
        """Aggregate counts, models, tokens, and duration from messages.

        Args:
            messages: List of parsed Message objects.

        Returns:
            SessionMetadata with aggregated statistics.
        """
        if not messages:
            return SessionMetadata()

        models: set[str] = set()
        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_write = 0
        tool_call_count = 0
        first_message = ""

        for msg in messages:
            if msg.model:
                models.add(msg.model)
            if msg.usage:
                total_input += msg.usage.input_tokens
                total_output += msg.usage.output_tokens
                total_cache_read += msg.usage.cache_read_tokens
                total_cache_write += msg.usage.cache_creation_tokens
            tool_call_count += len(msg.tool_calls)
            if (
                not first_message
                and msg.role == "user"
                and isinstance(msg.content, str)
                and msg.content.strip()
            ):
                first_message = self.truncate_first_message(msg.content)

        timestamps = [m.timestamp for m in messages if m.timestamp]
        duration = 0
        if len(timestamps) >= 2:
            duration = int((max(timestamps) - min(timestamps)).total_seconds())

        return SessionMetadata(
            message_count=len(messages),
            tool_call_count=tool_call_count,
            models=sorted(models),
            first_message=first_message,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_cache_read=total_cache_read,
            total_cache_write=total_cache_write,
            duration=duration,
        )

    def _parse_single_jsonl(
        self,
        file_path: Path,
        diagnostics: DiagnosticsCollector | None = None,
    ) -> list[Message]:
        """Parse a single JSONL file into Message objects.

        Args:
            file_path: Path to the .jsonl file.
            diagnostics: Optional collector for parse quality metrics.

        Returns:
            List of Message objects.
        """
        raw_entries = [
            entry
            for entry in self.iter_jsonl_safe(file_path, diagnostics=diagnostics)
            if entry.get("type") in RELEVANT_TYPES
        ]

        tool_results = _collect_tool_results(raw_entries)
        tool_use_ids: set[str] = set()

        messages = []
        for entry in raw_entries:
            entry_type = entry.get("type", "")
            msg = entry.get("message", {})
            uuid = entry.get("uuid", str(uuid4()))
            session_id = entry.get("sessionId", "")
            parent_uuid = entry.get("parentUuid", "")
            is_sidechain = entry.get("isSidechain", False)
            timestamp = parse_ms_timestamp(entry.get("timestamp"))

            role = msg.get("role", entry_type)
            model = msg.get("model", "")
            raw_content = msg.get("content", "")

            content_blocks = _parse_content_blocks(raw_content)
            tool_calls = _extract_tool_calls(content_blocks, tool_results)
            usage = _parse_usage(msg.get("usage"))

            for tc in tool_calls:
                if tc.id:
                    tool_use_ids.add(tc.id)
                    if diagnostics:
                        diagnostics.record_tool_call()

            message_content: str | list[ContentBlock] = (
                raw_content if isinstance(raw_content, str) else content_blocks
            )

            messages.append(
                Message(
                    uuid=uuid,
                    session_id=session_id,
                    parent_uuid=parent_uuid,
                    role=role,
                    type=entry_type,
                    content=message_content,
                    model=model,
                    timestamp=timestamp,
                    is_sidechain=is_sidechain,
                    usage=usage,
                    tool_calls=tool_calls,
                )
            )

        if diagnostics:
            _detect_orphans(tool_use_ids, tool_results, diagnostics)

        return messages


def count_history_entries(claude_dir: Path) -> int:
    """Count lines in history.jsonl with O(1) memory via buffered byte reads.

    Args:
        claude_dir: Path to ~/.claude directory.

    Returns:
        Number of non-empty lines in history.jsonl, or 0 if missing.
    """
    history_file = claude_dir / "history.jsonl"
    if not history_file.exists():
        return 0

    count = 0
    buf_size = 65536
    try:
        with open(history_file, "rb") as f:
            while True:
                buf = f.read(buf_size)
                if not buf:
                    break
                count += buf.count(b"\n")
    except OSError:
        return 0
    return count


def _aggregate_history_lines(
    history_file: Path, since_ms: int
) -> dict[str, dict]:
    """Read history.jsonl and group entries by session.

    Skips entries whose timestamp falls before ``since_ms`` for early
    filtering when callers only need recent sessions.

    Args:
        history_file: Path to the history.jsonl file.
        since_ms: Minimum timestamp in milliseconds (0 to include all).

    Returns:
        Dict mapping session_id → aggregated session data.
    """
    sessions: dict[str, dict] = {}
    with open(history_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            session_id = entry.get("sessionId", "")
            if not session_id:
                continue

            timestamp_ms = entry.get("timestamp", 0)
            if since_ms and timestamp_ms < since_ms:
                continue

            display = entry.get("display", "")
            project_path = entry.get("project", "")

            if session_id not in sessions:
                sessions[session_id] = {
                    "first_timestamp": timestamp_ms,
                    "last_timestamp": timestamp_ms,
                    "first_message": display,
                    "project_path": project_path,
                    "message_count": 1,
                }
            else:
                sess = sessions[session_id]
                sess["message_count"] += 1
                if timestamp_ms < sess["first_timestamp"]:
                    sess["first_timestamp"] = timestamp_ms
                    sess["first_message"] = display
                if timestamp_ms > sess["last_timestamp"]:
                    sess["last_timestamp"] = timestamp_ms
    return sessions


def _detect_orphans(
    tool_use_ids: set[str],
    tool_results: dict[str, dict],
    diagnostics: DiagnosticsCollector,
) -> None:
    """Detect orphaned tool calls and results and record in diagnostics.

    Args:
        tool_use_ids: Set of tool_use IDs found in assistant messages.
        tool_results: Mapping of tool_use_id → result from user messages.
        diagnostics: Collector to record orphans into.
    """
    result_ids = set(tool_results.keys())
    for tc_id in tool_use_ids:
        diagnostics.record_tool_result()
        if tc_id not in result_ids:
            diagnostics.record_orphaned_call(tc_id)
    for result_id in result_ids:
        diagnostics.record_tool_result()
        if result_id not in tool_use_ids:
            diagnostics.record_orphaned_result(result_id)


def _find_agent_spawn_points(messages: list[Message]) -> list[tuple[int, str]]:
    """Find message indices where Agent tool calls were spawned.

    Scans for assistant messages with tool_calls named "Agent" and
    returns their (message_index, tool_call_id) pairs in order.

    Args:
        messages: Parsed main-session messages.

    Returns:
        Ordered list of (message_index, tool_call_id) tuples.
    """
    spawn_points: list[tuple[int, str]] = []
    for idx, msg in enumerate(messages):
        if msg.role != "assistant":
            continue
        for tc in msg.tool_calls:
            if tc.name == "Agent":
                spawn_points.append((idx, tc.id))
    return spawn_points


def _collect_tool_results(raw_entries: list[dict]) -> OrderedDict[str, dict]:
    """Build a bounded mapping of tool_use_id → result from user messages.

    Uses an OrderedDict bounded at MAX_TOOL_RESULT_CACHE entries to avoid
    doubling memory for large sessions. Tool results almost always appear
    near their tool_use, so the bounded cache rarely evicts needed entries.
    """
    tool_results: OrderedDict[str, dict] = OrderedDict()
    for entry in raw_entries:
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", {})
        content = msg.get("content", "")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_result":
                tool_use_id = block.get("tool_use_id", "")
                if tool_use_id:
                    result_content = block.get("content", "")
                    is_error = block.get("is_error", False)
                    output = _extract_tool_result_text(result_content)
                    tool_results[tool_use_id] = {"output": output, "is_error": bool(is_error)}
                    if len(tool_results) > MAX_TOOL_RESULT_CACHE:
                        tool_results.popitem(last=False)
    return tool_results


def _parse_content_blocks(raw_content: str | list) -> list[ContentBlock]:
    """Convert raw content into ContentBlock objects."""
    if isinstance(raw_content, str):
        if raw_content.strip():
            return [ContentBlock(type="text", text=raw_content)]
        return []

    blocks = []
    for item in raw_content:
        if not isinstance(item, dict):
            continue
        block_type = item.get("type", "text")
        block = ContentBlock(
            type=block_type,
            text=item.get("text"),
            thinking=item.get("thinking"),
            id=item.get("id"),
            name=item.get("name"),
            input=item.get("input"),
            tool_use_id=item.get("tool_use_id"),
            content=item.get("content"),
            is_error=item.get("is_error"),
        )
        blocks.append(block)
    return blocks


def _extract_tool_calls(
    content_blocks: list[ContentBlock], tool_results: dict[str, dict]
) -> list[ToolCall]:
    """Extract ToolCall objects from tool_use blocks, matching with results."""
    calls = []
    for block in content_blocks:
        if block.type != "tool_use":
            continue
        tool_id = block.id or ""
        result = tool_results.get(tool_id, {})
        calls.append(
            ToolCall(
                id=tool_id,
                name=block.name or "unknown",
                input=block.input,
                output=result.get("output"),
                is_error=result.get("is_error", False),
            )
        )
    return calls


def _extract_tool_result_text(content: str | list | None) -> str:
    """Extract plain text from a tool_result content field.

    The content field is polymorphic: plain string for simple results,
    list of typed blocks (``{type: "text", text: "..."}`` dicts or bare
    strings) for rich results.  We normalise everything to a single string.
    """
    return coerce_to_string(content)


def _parse_usage(usage_data: dict | None) -> TokenUsage | None:
    """Parse usage dict into TokenUsage model.

    Field names follow the Anthropic API convention (``cache_creation_input_tokens``
    and ``cache_read_input_tokens``), which differ slightly from our model's
    shorter names.
    """
    if not usage_data:
        return None
    return TokenUsage(
        input_tokens=usage_data.get("input_tokens", 0),
        output_tokens=usage_data.get("output_tokens", 0),
        cache_creation_tokens=usage_data.get("cache_creation_input_tokens", 0),
        cache_read_tokens=usage_data.get("cache_read_input_tokens", 0),
    )
