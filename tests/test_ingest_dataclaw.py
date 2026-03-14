"""Tests for the dataclaw JSONL parser."""

import json
import tempfile
from pathlib import Path

from vibelens.ingest.dataclaw import DataclawParser
from vibelens.models.session import DataSourceType

_parser = DataclawParser()


def _make_session_record(
    session_id: str = "abc-123",
    model: str = "claude-opus-4-6",
    project: str = "/home/user/my-project",
    start_time: str = "2025-01-15T10:00:00Z",
    end_time: str = "2025-01-15T10:30:00Z",
    messages: list | None = None,
    stats: dict | None = None,
) -> dict:
    """Build a synthetic dataclaw session record."""
    if messages is None:
        messages = [
            {
                "role": "user",
                "content": "Hello, help me fix this bug",
                "timestamp": "2025-01-15T10:00:00Z",
            },
            {
                "role": "assistant",
                "content": "Sure, let me look at it.",
                "timestamp": "2025-01-15T10:00:05Z",
                "tool_uses": [
                    {"tool": "Read", "input": "src/main.py"},
                ],
            },
            {
                "role": "user",
                "content": "Thanks!",
                "timestamp": "2025-01-15T10:01:00Z",
            },
        ]
    if stats is None:
        stats = {
            "user_messages": 2,
            "assistant_messages": 1,
            "tool_uses": 1,
            "input_tokens": 5000,
            "output_tokens": 1500,
        }
    return {
        "session_id": session_id,
        "model": model,
        "project": project,
        "git_branch": "main",
        "start_time": start_time,
        "end_time": end_time,
        "messages": messages,
        "stats": stats,
    }


class TestParseDataclawSession:
    """Tests for parse_dataclaw_session."""

    def test_basic_session(self):
        record = _make_session_record()
        summary, messages = _parser.parse_session(record)

        assert summary.session_id == "abc-123"
        assert summary.project_name == "my-project"
        assert summary.models == ["claude-opus-4-6"]
        assert summary.source_type == DataSourceType.HUGGINGFACE
        assert summary.source_host == "https://huggingface.co"

    def test_message_count_from_stats(self):
        record = _make_session_record()
        summary, _ = _parser.parse_session(record)
        assert summary.message_count == 3
        assert summary.tool_call_count == 1

    def test_duration_calculation(self):
        record = _make_session_record(
            start_time="2025-01-15T10:00:00Z",
            end_time="2025-01-15T10:30:00Z",
        )
        summary, _ = _parser.parse_session(record)
        assert summary.duration == 1800

    def test_messages_parsed(self):
        record = _make_session_record()
        _, messages = _parser.parse_session(record)

        assert len(messages) == 3
        assert messages[0].role == "user"
        assert messages[0].content == "Hello, help me fix this bug"
        assert messages[1].role == "assistant"
        assert len(messages[1].tool_calls) == 1
        assert messages[1].tool_calls[0].name == "Read"

    def test_first_message_extraction(self):
        record = _make_session_record()
        summary, _ = _parser.parse_session(record)
        assert summary.first_message == "Hello, help me fix this bug"

    def test_first_message_truncated(self):
        long_msg = "x" * 500
        record = _make_session_record(
            messages=[{"role": "user", "content": long_msg, "timestamp": "2025-01-15T10:00:00Z"}],
        )
        summary, _ = _parser.parse_session(record)
        assert len(summary.first_message) == 200

    def test_missing_model(self):
        record = _make_session_record(model="")
        summary, _ = _parser.parse_session(record)
        assert summary.models == []

    def test_missing_timestamps(self):
        record = _make_session_record(start_time=None, end_time=None)
        summary, _ = _parser.parse_session(record)
        assert summary.timestamp is None
        assert summary.duration == 0

    def test_thinking_field(self):
        record = _make_session_record(
            messages=[
                {
                    "role": "assistant",
                    "content": "The answer is 42.",
                    "timestamp": "2025-01-15T10:00:05Z",
                    "thinking": "Let me think about this carefully...",
                },
            ],
        )
        _, messages = _parser.parse_session(record)
        assert messages[0].thinking == "Let me think about this carefully..."

    def test_empty_messages(self):
        record = _make_session_record(messages=[])
        _, messages = _parser.parse_session(record)
        assert messages == []

    def test_invalid_role_skipped(self):
        record = _make_session_record(
            messages=[
                {
                    "role": "system",
                    "content": "You are helpful",
                    "timestamp": "2025-01-15T10:00:00Z",
                },
                {"role": "user", "content": "hi", "timestamp": "2025-01-15T10:00:01Z"},
            ],
        )
        _, messages = _parser.parse_session(record)
        assert len(messages) == 1
        assert messages[0].role == "user"

    def test_project_encoding(self):
        record = _make_session_record(project="/Users/dev/projects/my-app")
        summary, _ = _parser.parse_session(record)
        assert summary.project_name == "my-app"
        assert summary.project_id == "Users-dev-projects-my-app"

    def test_empty_project(self):
        record = _make_session_record(project="")
        summary, _ = _parser.parse_session(record)
        assert summary.project_name == "Unknown"
        assert summary.project_id == ""

    def test_tool_uses_multiple(self):
        record = _make_session_record(
            messages=[
                {
                    "role": "assistant",
                    "content": "Let me check...",
                    "timestamp": "2025-01-15T10:00:05Z",
                    "tool_uses": [
                        {"tool": "Bash", "input": "ls -la"},
                        {"tool": "Read", "input": "README.md"},
                    ],
                },
            ],
        )
        _, messages = _parser.parse_session(record)
        assert len(messages[0].tool_calls) == 2
        assert messages[0].tool_calls[0].name == "Bash"
        assert messages[0].tool_calls[1].name == "Read"

    def test_session_id_assigned(self):
        record = _make_session_record()
        _, messages = _parser.parse_session(record)
        for msg in messages:
            assert msg.session_id == "abc-123"

    def test_assistant_gets_model(self):
        record = _make_session_record(model="claude-opus-4-6")
        _, messages = _parser.parse_session(record)
        user_msgs = [m for m in messages if m.role == "user"]
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        for m in user_msgs:
            assert m.model == ""
        for m in assistant_msgs:
            assert m.model == "claude-opus-4-6"


class TestParseFile:
    """Tests for DataclawParser.parse_file."""

    def test_parse_multi_session_file(self):
        records = [
            _make_session_record(session_id="s1"),
            _make_session_record(session_id="s2"),
            _make_session_record(session_id="s3"),
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
            path = Path(f.name)

        results = _parser.parse_file(path)
        assert len(results) == 3
        session_ids = {s.session_id for s, _ in results}
        assert session_ids == {"s1", "s2", "s3"}
        path.unlink()

    def test_skip_malformed_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(_make_session_record(session_id="good")) + "\n")
            f.write("NOT VALID JSON\n")
            f.write(json.dumps(_make_session_record(session_id="also-good")) + "\n")
            path = Path(f.name)

        results = _parser.parse_file(path)
        assert len(results) == 2
        path.unlink()

    def test_skip_empty_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("\n")
            f.write(json.dumps(_make_session_record(session_id="s1")) + "\n")
            f.write("   \n")
            path = Path(f.name)

        results = _parser.parse_file(path)
        assert len(results) == 1
        path.unlink()

    def test_nonexistent_file(self):
        results = _parser.parse_file(Path("/tmp/does_not_exist_dataclaw.jsonl"))
        assert results == []

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)

        results = _parser.parse_file(path)
        assert results == []
        path.unlink()

    def test_messages_have_uuids(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(_make_session_record()) + "\n")
            path = Path(f.name)

        results = _parser.parse_file(path)
        _, messages = results[0]
        uuids = [m.uuid for m in messages]
        assert len(uuids) == len(set(uuids))
        path.unlink()
