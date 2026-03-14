"""Dataclaw JSONL format parser.

Parses HuggingFace dataclaw datasets that contain Claude Code conversation
histories exported as structured JSONL.
"""

import json
from pathlib import Path
from uuid import uuid4

from vibelens.ingest.base import BaseParser
from vibelens.models.message import Message, ToolCall
from vibelens.models.session import DataSourceType, SessionSummary
from vibelens.utils import get_logger, parse_iso_timestamp

logger = get_logger(__name__)


class DataclawParser(BaseParser):
    """Parser for dataclaw-exported conversation datasets."""

    def parse_file(
        self, file_path: Path
    ) -> list[tuple[SessionSummary, list[Message]]]:
        """Parse a dataclaw conversations.jsonl file.

        Args:
            file_path: Path to the conversations.jsonl file.

        Returns:
            List of (SessionSummary, messages) tuples, one per session.
        """
        if not file_path.exists():
            logger.warning("Dataclaw file not found: %s", file_path)
            return []

        results = []
        with open(file_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(
                        "Skipping malformed JSON at line %d", line_num
                    )
                    continue
                try:
                    result = self.parse_session(record)
                    results.append(result)
                except Exception:
                    logger.warning(
                        "Failed to parse session at line %d",
                        line_num,
                        exc_info=True,
                    )
                    continue

        return results

    def parse_session(
        self, record: dict
    ) -> tuple[SessionSummary, list[Message]]:
        """Parse a single dataclaw session record into models.

        Args:
            record: Parsed JSON object from a conversations.jsonl line.

        Returns:
            Tuple of (SessionSummary, list of Message objects).
        """
        session_id = record.get("session_id", str(uuid4()))
        project = record.get("project", "")
        model = record.get("model", "")
        start_time = parse_iso_timestamp(record.get("start_time"))
        end_time = parse_iso_timestamp(record.get("end_time"))

        stats = record.get("stats", {})
        user_msg_count = stats.get("user_messages", 0)
        assistant_msg_count = stats.get("assistant_messages", 0)
        message_count = user_msg_count + assistant_msg_count
        tool_use_count = stats.get("tool_uses", 0)

        duration = 0
        if start_time and end_time:
            duration = int((end_time - start_time).total_seconds())

        raw_messages = record.get("messages", [])
        messages = _build_messages(raw_messages, session_id, model)

        first_message = self._extract_first_user_message(raw_messages)

        summary = SessionSummary(
            session_id=session_id,
            project_id=self.encode_project_path(project),
            project_name=self.extract_project_name(project),
            timestamp=start_time,
            duration=duration,
            message_count=message_count,
            tool_call_count=tool_use_count,
            models=[model] if model else [],
            first_message=first_message,
            source_type=DataSourceType.HUGGINGFACE,
            source_name="",
            source_host="https://huggingface.co",
        )

        return summary, messages

    def _extract_first_user_message(self, raw_messages: list) -> str:
        """Extract truncated text of the first user message."""
        for raw in raw_messages:
            if not isinstance(raw, dict):
                continue
            if raw.get("role") == "user":
                content = raw.get("content", "")
                if isinstance(content, str) and content.strip():
                    return self.truncate_first_message(content)
        return ""


def _build_messages(
    raw_messages: list,
    session_id: str,
    session_model: str,
) -> list[Message]:
    """Convert dataclaw message dicts into Message objects."""
    messages = []
    for raw in raw_messages:
        if not isinstance(raw, dict):
            continue

        role = raw.get("role", "")
        if role not in ("user", "assistant"):
            continue

        content = raw.get("content", "")
        thinking = raw.get("thinking") or None
        timestamp = parse_iso_timestamp(raw.get("timestamp"))

        raw_tool_uses = raw.get("tool_uses", [])
        tool_calls = _build_tool_calls(raw_tool_uses)

        messages.append(
            Message(
                uuid=str(uuid4()),
                session_id=session_id,
                role=role,
                type=role,
                content=content,
                thinking=thinking,
                model=session_model if role == "assistant" else "",
                timestamp=timestamp,
                tool_calls=tool_calls,
            )
        )

    return messages


def _build_tool_calls(raw_tool_uses: list) -> list[ToolCall]:
    """Convert dataclaw tool_uses into ToolCall objects."""
    calls = []
    for tool in raw_tool_uses:
        if not isinstance(tool, dict):
            continue
        calls.append(
            ToolCall(
                id=str(uuid4()),
                name=tool.get("tool", "unknown"),
                input=tool.get("input"),
            )
        )
    return calls
