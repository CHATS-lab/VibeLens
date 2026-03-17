"""Unit tests for vibelens.ingest.parsers.vibelens (VibeLens Export v1 parser)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vibelens.ingest.fingerprint import fingerprint_file, parse_auto
from vibelens.ingest.parsers.vibelens import VibeLensParser
from vibelens.models.message import Message, TokenUsage, ToolCall
from vibelens.models.session import SessionDetail, SessionSummary
from vibelens.targets.export import serialize_export

_parser = VibeLensParser()


def _make_export_data(
    agent_format: str = "codex",
    sub_sessions: list | None = None,
) -> dict:
    """Build a minimal VibeLens Export v1 JSON dict."""
    return {
        "vibelens_version": 1,
        "agent_format": agent_format,
        "session": {
            "session_id": "sess-round",
            "project_id": "proj-1",
            "project_name": "test-project",
            "timestamp": "2025-06-01T12:00:00+00:00",
            "duration": 300,
            "message_count": 2,
            "tool_call_count": 1,
            "models": ["gpt-5.4"],
            "first_message": "Hello",
            "source_type": "local",
            "total_input_tokens": 500,
            "total_output_tokens": 200,
            "total_cache_read": 50,
            "total_cache_write": 0,
            "diagnostics": None,
        },
        "messages": [
            {
                "uuid": "msg-u1",
                "role": "user",
                "content": "Hello",
                "timestamp": "2025-06-01T12:00:00+00:00",
            },
            {
                "uuid": "msg-a1",
                "role": "assistant",
                "content": "Hi there",
                "model": "gpt-5.4",
                "thinking": "Let me think...",
                "usage": {"input_tokens": 500, "output_tokens": 200},
                "tool_calls": [
                    {
                        "id": "tc-1",
                        "name": "shell",
                        "input": {"command": "ls"},
                        "output": "file.txt",
                    }
                ],
                "timestamp": "2025-06-01T12:00:05+00:00",
            },
        ],
        "sub_sessions": sub_sessions or [],
    }


def _write_export(path: Path, data: dict) -> None:
    """Write export data as JSON to a file."""
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class TestParseFile:
    """Tests for VibeLensParser.parse_file basic parsing."""

    def test_basic_parse(self, tmp_path: Path):
        """Parses a minimal VibeLens export file."""
        export_file = tmp_path / "vibelens-sess-round.json"
        _write_export(export_file, _make_export_data())
        results = _parser.parse_file(export_file)
        assert len(results) == 1
        summary, messages = results[0]
        assert summary.session_id == "sess-round"
        assert summary.agent_format == "codex"
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content == "Hello"
        assert messages[1].role == "assistant"
        assert messages[1].content == "Hi there"

    def test_missing_file_returns_empty(self, tmp_path: Path):
        """Non-existent file returns empty list."""
        results = _parser.parse_file(tmp_path / "does-not-exist.json")
        assert results == []

    def test_invalid_json_returns_empty(self, tmp_path: Path):
        """Invalid JSON returns empty list."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("NOT JSON", encoding="utf-8")
        results = _parser.parse_file(bad_file)
        assert results == []

    def test_unsupported_version_raises(self, tmp_path: Path):
        """Unsupported vibelens_version raises ValueError."""
        data = _make_export_data()
        data["vibelens_version"] = 99
        export_file = tmp_path / "future.json"
        _write_export(export_file, data)
        with pytest.raises(ValueError, match="Unsupported vibelens_version 99"):
            _parser.parse_file(export_file)

    def test_type_restored_from_role(self, tmp_path: Path):
        """Message type is restored to match role."""
        export_file = tmp_path / "export.json"
        _write_export(export_file, _make_export_data())
        results = _parser.parse_file(export_file)
        _, messages = results[0]
        for msg in messages:
            assert msg.type == msg.role

    def test_user_defaults_restored(self, tmp_path: Path):
        """User messages get default thinking=None, tool_calls=[]."""
        export_file = tmp_path / "export.json"
        _write_export(export_file, _make_export_data())
        results = _parser.parse_file(export_file)
        _, messages = results[0]
        user_msg = messages[0]
        assert user_msg.thinking is None
        assert user_msg.tool_calls == []
        assert user_msg.usage is None

    def test_assistant_fields_restored(self, tmp_path: Path):
        """Assistant messages get thinking, usage, tool_calls restored."""
        export_file = tmp_path / "export.json"
        _write_export(export_file, _make_export_data())
        results = _parser.parse_file(export_file)
        _, messages = results[0]
        assistant_msg = messages[1]
        assert assistant_msg.thinking == "Let me think..."
        assert assistant_msg.usage is not None
        assert assistant_msg.usage.input_tokens == 500
        assert len(assistant_msg.tool_calls) == 1
        assert assistant_msg.tool_calls[0].name == "shell"

    def test_tool_enrichment_applied(self, tmp_path: Path):
        """Tool calls are enriched with category after parsing."""
        export_file = tmp_path / "export.json"
        _write_export(export_file, _make_export_data())
        results = _parser.parse_file(export_file)
        _, messages = results[0]
        tc = messages[1].tool_calls[0]
        assert tc.category == "shell"


class TestParseFileFull:
    """Tests for VibeLensParser.parse_file_full with sub-sessions."""

    def test_sub_sessions_restored(self, tmp_path: Path):
        """Sub-sessions are reconstructed from export data."""
        data = _make_export_data(
            sub_sessions=[
                {
                    "agent_id": "agent-abc",
                    "spawn_index": 0,
                    "spawn_tool_call_id": "tc-spawn",
                    "messages": [
                        {
                            "uuid": "msg-sub1",
                            "role": "user",
                            "content": "Sub task",
                            "timestamp": "2025-06-01T12:01:00+00:00",
                        },
                    ],
                    "sub_sessions": [],
                }
            ]
        )
        export_file = tmp_path / "export.json"
        _write_export(export_file, data)
        detail = _parser.parse_file_full(export_file)
        assert detail is not None
        assert len(detail.sub_sessions) == 1
        sub = detail.sub_sessions[0]
        assert sub.agent_id == "agent-abc"
        assert sub.spawn_index == 0
        assert len(sub.messages) == 1
        assert sub.messages[0].is_sidechain is True

    def test_missing_file_returns_none(self, tmp_path: Path):
        """Non-existent file returns None."""
        result = _parser.parse_file_full(tmp_path / "nope.json")
        assert result is None


class TestRoundTrip:
    """Test export → re-import roundtrip preserves data."""

    def test_roundtrip_preserves_data(self, tmp_path: Path):
        """Exported session can be re-imported with matching data."""
        original_summary = SessionSummary(
            session_id="sess-rt",
            project_name="roundtrip-project",
            timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC),
            duration=600,
            message_count=2,
            tool_call_count=1,
            models=["gpt-5.4"],
            first_message="Fix the bug",
            agent_format="codex",
        )
        original_messages = [
            Message(
                uuid="msg-1",
                session_id="sess-rt",
                role="user",
                type="user",
                content="Fix the bug",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC),
            ),
            Message(
                uuid="msg-2",
                session_id="sess-rt",
                role="assistant",
                type="assistant",
                content="Done!",
                model="gpt-5.4",
                thinking="I need to fix it",
                timestamp=datetime(2025, 6, 1, 12, 0, 30, tzinfo=UTC),
                usage=TokenUsage(input_tokens=100, output_tokens=50),
                tool_calls=[
                    ToolCall(id="tc-1", name="shell", input={"command": "git diff"}, output="diff")
                ],
            ),
        ]
        original_detail = SessionDetail(
            summary=original_summary, messages=original_messages
        )

        # Export
        exported = serialize_export(original_detail)
        export_file = tmp_path / "vibelens-roundtrip.json"
        export_file.write_text(json.dumps(exported, indent=2, default=str), encoding="utf-8")

        # Re-import
        results = _parser.parse_file(export_file)
        assert len(results) == 1
        reimported_summary, reimported_messages = results[0]

        # Verify summary
        assert reimported_summary.session_id == original_summary.session_id
        assert reimported_summary.project_name == original_summary.project_name
        assert reimported_summary.duration == original_summary.duration
        assert reimported_summary.models == original_summary.models
        assert reimported_summary.agent_format == "codex"

        # Verify messages
        assert len(reimported_messages) == 2
        assert reimported_messages[0].role == "user"
        assert reimported_messages[0].content == "Fix the bug"
        assert reimported_messages[1].role == "assistant"
        assert reimported_messages[1].thinking == "I need to fix it"
        assert reimported_messages[1].usage.input_tokens == 100
        assert reimported_messages[1].tool_calls[0].name == "shell"


class TestFingerprint:
    """Tests for VibeLens format fingerprint detection."""

    def test_vibelens_detected(self, tmp_path: Path):
        """VibeLens export files are detected with high confidence."""
        export_file = tmp_path / "vibelens-test.json"
        _write_export(export_file, _make_export_data())
        matches = fingerprint_file(export_file)
        assert len(matches) >= 1
        best = matches[0]
        assert best.format_name == "vibelens"
        assert best.confidence >= 0.8
        assert best.parser_class == "VibeLensParser"

    def test_parse_auto_picks_vibelens(self, tmp_path: Path):
        """parse_auto selects VibeLensParser for export files."""
        export_file = tmp_path / "vibelens-auto.json"
        _write_export(export_file, _make_export_data())
        results = parse_auto(export_file)
        assert len(results) == 1
        summary, _ = results[0]
        assert summary.session_id == "sess-round"

    def test_gemini_not_confused(self, tmp_path: Path):
        """Gemini files are not confused with VibeLens format."""
        gemini_data = {
            "sessionId": "gem-123",
            "messages": [{"type": "user", "text": "hello"}],
            "startTime": "2025-01-01T00:00:00Z",
        }
        gemini_file = tmp_path / "session.json"
        gemini_file.write_text(json.dumps(gemini_data), encoding="utf-8")
        matches = fingerprint_file(gemini_file)
        assert matches[0].format_name == "gemini"
