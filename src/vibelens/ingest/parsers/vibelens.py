"""VibeLens Export v1 format parser.

Re-imports sessions previously exported via the VibeLens export
endpoint, reconstructing SessionSummary, Messages, and sub-sessions
from the VibeLens Export v1 JSON format.
"""

import json
from pathlib import Path

from vibelens.ingest.parsers.base import BaseParser
from vibelens.models.enums import DataSourceType
from vibelens.models.message import Message, TokenUsage, ToolCall
from vibelens.models.session import SessionDetail, SessionSummary, SubAgentSession
from vibelens.utils import get_logger
from vibelens.utils.timestamps import normalize_timestamp

logger = get_logger(__name__)

SUPPORTED_VERSION = 1


class VibeLensParser(BaseParser):
    """Parser for VibeLens Export v1 JSON format.

    Reads JSON files produced by the VibeLens export serializer and
    reconstructs the internal session model.
    """

    def parse_file(self, file_path: Path) -> list[tuple[SessionSummary, list[Message]]]:
        """Parse a VibeLens export JSON file.

        Args:
            file_path: Path to a vibelens-*.json export file.

        Returns:
            Single-element list of (SessionSummary, messages), or empty list.

        Raises:
            ValueError: If vibelens_version is not supported.
        """
        if not file_path.exists():
            logger.warning("Export file not found: %s", file_path)
            return []

        try:
            raw = file_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Cannot read VibeLens export %s: %s", file_path, exc)
            return []

        if not isinstance(data, dict):
            return []

        version = data.get("vibelens_version")
        if version != SUPPORTED_VERSION:
            raise ValueError(
                f"Unsupported vibelens_version {version} in {file_path}"
                f" (expected {SUPPORTED_VERSION})"
            )

        summary = _parse_session_metadata(data)
        messages = _parse_messages(data, summary.session_id)
        self.enrich_tool_calls(messages)

        return [(summary, messages)]

    def parse_file_full(self, file_path: Path) -> SessionDetail | None:
        """Parse a VibeLens export into a full SessionDetail with sub-sessions.

        Args:
            file_path: Path to a vibelens-*.json export file.

        Returns:
            SessionDetail with sub-sessions, or None on failure.
        """
        if not file_path.exists():
            return None

        try:
            raw = file_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError):
            return None

        if not isinstance(data, dict):
            return None

        version = data.get("vibelens_version")
        if version != SUPPORTED_VERSION:
            return None

        summary = _parse_session_metadata(data)
        messages = _parse_messages(data, summary.session_id)
        self.enrich_tool_calls(messages)
        sub_sessions = _parse_sub_sessions(data, summary.session_id)

        return SessionDetail(summary=summary, messages=messages, sub_sessions=sub_sessions)


def _parse_session_metadata(data: dict) -> SessionSummary:
    """Reconstruct a SessionSummary from export data.

    Args:
        data: Parsed export JSON root.

    Returns:
        SessionSummary with fields populated from the export.
    """
    session = data.get("session", {})
    timestamp = normalize_timestamp(session.get("timestamp"))

    return SessionSummary(
        session_id=session.get("session_id", ""),
        project_id=session.get("project_id", ""),
        project_name=session.get("project_name", ""),
        timestamp=timestamp,
        duration=session.get("duration", 0),
        message_count=session.get("message_count", 0),
        tool_call_count=session.get("tool_call_count", 0),
        models=session.get("models", []),
        first_message=session.get("first_message", ""),
        source_type=DataSourceType.UPLOAD,
        total_input_tokens=session.get("total_input_tokens", 0),
        total_output_tokens=session.get("total_output_tokens", 0),
        total_cache_read=session.get("total_cache_read", 0),
        total_cache_write=session.get("total_cache_write", 0),
        agent_format=data.get("agent_format", "vibelens"),
    )


def _parse_messages(data: dict, session_id: str) -> list[Message]:
    """Reconstruct Message objects from export message list.

    Restores default values for fields omitted in the export format
    (type=role, thinking=None, tool_calls=[], is_sidechain=False).

    Args:
        data: Parsed export JSON root.
        session_id: Session ID for the messages.

    Returns:
        List of Message objects.
    """
    raw_messages = data.get("messages", [])
    messages: list[Message] = []
    for raw in raw_messages:
        if not isinstance(raw, dict):
            continue
        msg = _reconstruct_message(raw, session_id)
        messages.append(msg)
    return messages


def _reconstruct_message(raw: dict, session_id: str) -> Message:
    """Reconstruct a single Message from export dict.

    Args:
        raw: Message dictionary from the export.
        session_id: Session ID to assign.

    Returns:
        Message with defaults restored for omitted fields.
    """
    role = raw.get("role", "user")
    timestamp = normalize_timestamp(raw.get("timestamp"))

    usage = None
    raw_usage = raw.get("usage")
    if isinstance(raw_usage, dict):
        usage = TokenUsage(**raw_usage)

    tool_calls: list[ToolCall] = []
    raw_tools = raw.get("tool_calls", [])
    for tc_data in raw_tools:
        if isinstance(tc_data, dict):
            tool_calls.append(ToolCall(**tc_data))

    return Message(
        uuid=raw.get("uuid", ""),
        session_id=session_id,
        parent_uuid=raw.get("parent_uuid", ""),
        role=role,
        type=role,
        content=raw.get("content", ""),
        thinking=raw.get("thinking"),
        model=raw.get("model", ""),
        timestamp=timestamp,
        is_sidechain=False,
        usage=usage,
        tool_calls=tool_calls,
    )


def _parse_sub_sessions(data: dict, session_id: str) -> list[SubAgentSession]:
    """Reconstruct sub-sessions from export data.

    Args:
        data: Parsed export JSON root.
        session_id: Session ID for sub-session messages.

    Returns:
        List of SubAgentSession objects.
    """
    raw_subs = data.get("sub_sessions", [])
    return [_reconstruct_sub_session(raw, session_id) for raw in raw_subs if isinstance(raw, dict)]


def _reconstruct_sub_session(raw: dict, session_id: str) -> SubAgentSession:
    """Reconstruct a single SubAgentSession from export dict.

    Args:
        raw: Sub-session dictionary from the export.
        session_id: Session ID for messages.

    Returns:
        SubAgentSession with messages and nested sub-sessions.
    """
    messages: list[Message] = []
    for msg_data in raw.get("messages", []):
        if isinstance(msg_data, dict):
            msg = _reconstruct_message(msg_data, session_id)
            msg.is_sidechain = True
            messages.append(msg)

    nested_subs: list[SubAgentSession] = []
    for sub_data in raw.get("sub_sessions", []):
        if isinstance(sub_data, dict):
            nested_subs.append(_reconstruct_sub_session(sub_data, session_id))

    return SubAgentSession(
        agent_id=raw.get("agent_id", ""),
        spawn_index=raw.get("spawn_index"),
        spawn_tool_call_id=raw.get("spawn_tool_call_id", ""),
        messages=messages,
        sub_sessions=nested_subs,
    )
