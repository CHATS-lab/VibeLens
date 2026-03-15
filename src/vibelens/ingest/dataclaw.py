"""Dataclaw JSONL format parser.

Parses HuggingFace dataclaw datasets that contain Claude Code conversation
histories exported as structured JSONL.

Unlike the local CLI parsers (claude_code, codex, gemini) where each file
holds one session, dataclaw packs **one complete session per JSONL line**.
Each line is a self-contained JSON object with session metadata, message
array, and pre-computed stats — so ``parse_file`` can return multiple
(summary, messages) tuples from a single file.

The format is a third-party export format (dataclaw tool), not a native
agent format, so field names and structures differ from all three CLI
agents.  Tool calls use a flat ``tool_uses`` array without result data
(dataclaw strips tool outputs during privacy scrubbing).
"""

from collections.abc import Iterator
from pathlib import Path

from vibelens.ingest.base import BaseParser
from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.models.message import Message, ToolCall
from vibelens.models.session import DataSourceType, SessionSummary
from vibelens.utils import coerce_to_string, deterministic_id, get_logger, parse_iso_timestamp

logger = get_logger(__name__)


class DataclawParser(BaseParser):
    """Parser for dataclaw-exported conversation datasets."""

    def parse_file(self, file_path: Path) -> list[tuple[SessionSummary, list[Message]]]:
        """Parse a dataclaw conversations.jsonl file.

        Args:
            file_path: Path to the conversations.jsonl file.

        Returns:
            List of (SessionSummary, messages) tuples, one per session.
        """
        return list(self.iter_sessions(file_path))

    def iter_sessions(self, file_path: Path) -> Iterator[tuple[SessionSummary, list[Message]]]:
        """Yield sessions one at a time for constant-memory processing.

        Args:
            file_path: Path to the conversations.jsonl file.

        Yields:
            (SessionSummary, messages) tuples, one per valid session line.
        """
        collector = DiagnosticsCollector()
        for record in self.iter_jsonl_safe(file_path, diagnostics=collector):
            try:
                yield self.parse_session(record, collector)
            except (KeyError, TypeError, ValueError):
                logger.warning("Failed to parse dataclaw session", exc_info=True)
                continue

    def parse_session(
        self, record: dict, diagnostics: DiagnosticsCollector | None = None
    ) -> tuple[SessionSummary, list[Message]]:
        """Parse a single dataclaw session record into models.

        Args:
            record: Parsed JSON object from a conversations.jsonl line.
            diagnostics: Optional collector for parse quality metrics.

        Returns:
            Tuple of (SessionSummary, list of Message objects).
        """
        # Dataclaw may omit session_id; derive a deterministic one from
        # project + start_time so parsing the same file twice yields the same ID.
        session_id = record.get("session_id") or deterministic_id(
            "sess", record.get("project", ""), record.get("start_time", "")
        )
        project = record.get("project", "")
        model = record.get("model", "")
        start_time = parse_iso_timestamp(record.get("start_time"))
        end_time = parse_iso_timestamp(record.get("end_time"))

        # Use pre-computed stats from the export rather than counting
        # messages ourselves — dataclaw may have filtered or truncated
        # the raw message array during privacy scrubbing.
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
        self.enrich_tool_calls(messages)

        first_message = self.find_first_user_text(messages)

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
            diagnostics=diagnostics.to_diagnostics() if diagnostics else None,
        )

        return summary, messages


def _build_messages(raw_messages: list, session_id: str, session_model: str) -> list[Message]:
    """Convert dataclaw message dicts into Message objects.

    Dataclaw does not include per-message model or token data — the model
    is session-level and only applied to assistant messages.  Message UUIDs
    are generated since dataclaw strips original IDs for privacy.
    """
    messages = []
    for idx, raw in enumerate(raw_messages):
        if not isinstance(raw, dict):
            continue

        role = raw.get("role", "")
        if role not in ("user", "assistant"):
            continue

        content = coerce_to_string(raw.get("content", ""))
        thinking = raw.get("thinking") or None
        timestamp = parse_iso_timestamp(raw.get("timestamp"))

        raw_tool_uses = raw.get("tool_uses", [])
        tool_calls = _build_tool_calls(raw_tool_uses, session_id, idx)

        messages.append(
            Message(
                uuid=deterministic_id("msg", session_id, str(idx), role),
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


def _build_tool_calls(
    raw_tool_uses: list, session_id: str, msg_idx: int
) -> list[ToolCall]:
    """Convert dataclaw tool_uses into ToolCall objects.

    Dataclaw only records tool name and input; outputs are stripped
    during privacy scrubbing, so ToolCall.output stays None.
    """
    calls = []
    for tc_idx, tool in enumerate(raw_tool_uses):
        if not isinstance(tool, dict):
            continue
        tool_name = tool.get("tool", "unknown")
        calls.append(
            ToolCall(
                id=deterministic_id("tc", session_id, str(msg_idx), tool_name, str(tc_idx)),
                name=tool_name,
                input=tool.get("input"),
            )
        )
    return calls
