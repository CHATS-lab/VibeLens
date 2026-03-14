"""Claude Code JSONL format parser.

Parses ~/.claude/history.jsonl for session indices and individual
session .jsonl files for full conversation data, including subagent
conversations stored in {session-id}/subagents/ directories.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from vibelens.ingest.base import BaseParser
from vibelens.models.message import ContentBlock, Message, TokenUsage, ToolCall
from vibelens.models.session import SessionMetadata, SessionSummary
from vibelens.utils import get_logger, parse_ms_timestamp

logger = get_logger(__name__)

RELEVANT_TYPES = {"user", "assistant"}


class ClaudeCodeParser(BaseParser):
    """Parser for Claude Code's native JSONL format.

    Handles both the history index (history.jsonl) and individual
    session files, including subagent conversations.
    """

    def parse_file(
        self, file_path: Path
    ) -> list[tuple[SessionSummary, list[Message]]]:
        """Parse a session JSONL file into a (summary, messages) pair.

        Args:
            file_path: Path to a session .jsonl file.

        Returns:
            Single-element list of (SessionSummary, messages).
        """
        messages = self.parse_session_jsonl(file_path)
        if not messages:
            return []
        metadata = self.compute_session_metadata(messages)
        session_id = file_path.stem
        summary = SessionSummary(
            session_id=session_id,
            message_count=metadata.message_count,
            first_message=metadata.first_message,
        )
        return [(summary, messages)]

    def parse_history_index(self, claude_dir: Path) -> list[SessionSummary]:
        """Parse history.jsonl to build a session summary list.

        Groups entries by sessionId, extracts project name, first message,
        timestamp, and message count per session.

        Args:
            claude_dir: Path to ~/.claude directory.

        Returns:
            List of SessionSummary objects sorted by timestamp descending.
        """
        history_file = claude_dir / "history.jsonl"
        if not history_file.exists():
            logger.warning("history.jsonl not found at %s", history_file)
            return []

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

        summaries = []
        for session_id, data in sessions.items():
            project_path = data["project_path"]
            project_name = self.extract_project_name(project_path)
            project_id = self.encode_project_path(project_path)
            first_message = self.truncate_first_message(data["first_message"])
            timestamp = datetime.fromtimestamp(
                data["last_timestamp"] / 1000, tz=UTC
            )

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

        epoch = datetime.min.replace(tzinfo=UTC)
        summaries.sort(key=lambda s: s.timestamp or epoch, reverse=True)
        return summaries

    def parse_session_jsonl(self, file_path: Path) -> list[Message]:
        """Parse a session .jsonl file into a list of Message objects.

        Filters to user/assistant types, builds ContentBlocks, extracts
        ToolCalls by matching tool_use to tool_result across messages,
        parses TokenUsage, and appends subagent messages if present.

        Args:
            file_path: Path to the session .jsonl file.

        Returns:
            List of Message objects in chronological order.
        """
        messages = self._parse_single_jsonl(file_path)

        subagent_dir = file_path.parent / file_path.stem / "subagents"
        if subagent_dir.is_dir():
            for agent_file in sorted(subagent_dir.glob("agent-*.jsonl")):
                subagent_messages = self._parse_single_jsonl(agent_file)
                messages.extend(subagent_messages)

        return messages

    def compute_session_metadata(
        self, messages: list[Message]
    ) -> SessionMetadata:
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
            duration = int(
                (max(timestamps) - min(timestamps)).total_seconds()
            )

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

    @staticmethod
    def _parse_single_jsonl(file_path: Path) -> list[Message]:
        """Parse a single JSONL file into Message objects.

        Args:
            file_path: Path to the .jsonl file.

        Returns:
            List of Message objects.
        """
        if not file_path.exists():
            logger.warning("Session file not found: %s", file_path)
            return []

        raw_entries = []
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") in RELEVANT_TYPES:
                    raw_entries.append(entry)

        tool_results = _collect_tool_results(raw_entries)

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

            message_content: str | list[ContentBlock] = (
                raw_content
                if isinstance(raw_content, str)
                else content_blocks
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

        return messages


def _collect_tool_results(raw_entries: list[dict]) -> dict[str, dict]:
    """Build a mapping of tool_use_id → result from user messages."""
    tool_results: dict[str, dict] = {}
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
                    tool_results[tool_use_id] = {
                        "output": output,
                        "is_error": bool(is_error),
                    }
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
    """Extract plain text from a tool_result content field."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content)


def _parse_usage(usage_data: dict | None) -> TokenUsage | None:
    """Parse usage dict into TokenUsage model."""
    if not usage_data:
        return None
    return TokenUsage(
        input_tokens=usage_data.get("input_tokens", 0),
        output_tokens=usage_data.get("output_tokens", 0),
        cache_creation_tokens=usage_data.get(
            "cache_creation_input_tokens", 0
        ),
        cache_read_tokens=usage_data.get("cache_read_input_tokens", 0),
    )
