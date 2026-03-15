"""Unit tests for vibelens.ingest.gemini parser."""

import json
from pathlib import Path

from vibelens.ingest.gemini import (
    GeminiParser,
    _extract_thinking,
    _parse_gemini_tokens,
    resolve_project_path,
)
from vibelens.models.session import DataSourceType

_parser = GeminiParser()


def _write_session_json(path: Path, data: dict) -> None:
    """Write a session dict as a single JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _make_session(
    session_id: str = "sess-1",
    start_time: str = "2025-01-15T10:00:00Z",
    last_updated: str = "2025-01-15T10:30:00Z",
    messages: list | None = None,
    kind: str | None = None,
) -> dict:
    """Build a minimal Gemini session dict."""
    if messages is None:
        messages = [
            {
                "type": "user",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": [{"text": "Hello"}],
            },
            {
                "type": "gemini",
                "id": "m2",
                "timestamp": "2025-01-15T10:00:05Z",
                "content": "Hi there",
                "model": "gemini-2.5-pro",
            },
        ]
    session = {
        "sessionId": session_id,
        "startTime": start_time,
        "lastUpdated": last_updated,
        "messages": messages,
    }
    if kind is not None:
        session["kind"] = kind
    return session


# ─── TestParseFile
class TestParseFile:
    """Tests for GeminiParser.parse_file high-level behavior."""

    def test_basic_session(self, tmp_path: Path):
        """Parse a standard two-message session."""
        path = tmp_path / "session-1.json"
        _write_session_json(path, _make_session())

        results = _parser.parse_file(path)
        assert len(results) == 1
        summary, messages = results[0]
        print(f"  summary: id={summary.session_id}, source={summary.source_type}")
        print(f"  models={summary.models}, first_message={summary.first_message}")
        print(f"  messages: {len(messages)}")
        for m in messages:
            print(f"    role={m.role}, type={m.type}, model={m.model}")
        assert summary.session_id == "sess-1"
        assert summary.source_type == DataSourceType.LOCAL
        assert len(messages) == 2

    def test_empty_file(self, tmp_path: Path):
        """Empty file returns no sessions."""
        path = tmp_path / "empty.json"
        path.write_text("")
        results = _parser.parse_file(path)
        assert results == []

    def test_missing_file(self, tmp_path: Path):
        """Non-existent file returns no sessions."""
        results = _parser.parse_file(tmp_path / "missing.json")
        assert results == []

    def test_missing_session_id(self, tmp_path: Path):
        """Session without sessionId is skipped."""
        data = _make_session()
        data.pop("sessionId")
        path = tmp_path / "no-id.json"
        _write_session_json(path, data)

        results = _parser.parse_file(path)
        assert results == []

    def test_empty_session_id(self, tmp_path: Path):
        """Empty sessionId string is treated as missing."""
        data = _make_session(session_id="")
        path = tmp_path / "empty-id.json"
        _write_session_json(path, data)

        results = _parser.parse_file(path)
        assert results == []

    def test_no_messages(self, tmp_path: Path):
        """Session with empty message list returns no results."""
        data = _make_session(messages=[])
        path = tmp_path / "no-msgs.json"
        _write_session_json(path, data)

        results = _parser.parse_file(path)
        assert results == []

    def test_session_id_propagated(self, tmp_path: Path):
        """All messages carry the session_id from the file."""
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(session_id="abc"))

        _, messages = _parser.parse_file(path)[0]
        for msg in messages:
            assert msg.session_id == "abc"

    def test_model_collected(self, tmp_path: Path):
        """Models are collected from gemini messages."""
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session())

        summary, _ = _parser.parse_file(path)[0]
        assert "gemini-2.5-pro" in summary.models

    def test_first_message_extracted(self, tmp_path: Path):
        """First user text is used as the summary first_message."""
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session())

        summary, _ = _parser.parse_file(path)[0]
        assert summary.first_message == "Hello"


# ─── TestUserContent
class TestUserContent:
    """Tests for user message content extraction."""

    def test_content_array(self, tmp_path: Path):
        """Content array with text objects is concatenated."""
        messages = [
            {
                "type": "user",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": [
                    {"text": "Line one"},
                    {"text": "Line two"},
                ],
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        assert parsed[0].content == "Line one\nLine two"

    def test_string_content(self, tmp_path: Path):
        """Plain string content is used as-is."""
        messages = [
            {
                "type": "user",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "Just a string",
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        assert parsed[0].content == "Just a string"

    def test_empty_content_array(self, tmp_path: Path):
        """Empty content array produces empty string."""
        messages = [
            {
                "type": "user",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": [],
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        # Empty content user message followed by a gemini message so
        # session is not empty.
        messages.append(
            {
                "type": "gemini",
                "id": "m2",
                "timestamp": "2025-01-15T10:00:05Z",
                "content": "reply",
            }
        )
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        user_msg = [m for m in parsed if m.role == "user"][0]
        assert user_msg.content == ""

    def test_non_list_non_string_content(self, tmp_path: Path):
        """Non-list, non-string content is coerced to string."""
        messages = [
            {
                "type": "user",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": 42,
            },
            {
                "type": "gemini",
                "id": "m2",
                "timestamp": "2025-01-15T10:00:05Z",
                "content": "reply",
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        user_msg = [m for m in parsed if m.role == "user"][0]
        assert user_msg.content == "42"


# ─── TestGeminiToAssistant
class TestGeminiToAssistant:
    """Tests for gemini type normalization to assistant role."""

    def test_role_normalized(self, tmp_path: Path):
        """Gemini messages get role='assistant'."""
        messages = [
            {
                "type": "gemini",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "response",
                "model": "gemini-2.5-pro",
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        assert parsed[0].role == "assistant"
        assert parsed[0].type == "gemini"

    def test_user_role_preserved(self, tmp_path: Path):
        """User messages keep role='user'."""
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session())

        _, parsed = _parser.parse_file(path)[0]
        user_msgs = [m for m in parsed if m.role == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0].type == "user"


# ─── TestThinkingExtraction
class TestThinkingExtraction:
    """Tests for _extract_thinking helper."""

    def test_subject_and_description(self):
        """Subject and description are formatted as [Subject] desc."""
        raw = {
            "thoughts": [
                {"subject": "Analysis", "description": "Thinking deeply"},
            ]
        }
        result = _extract_thinking(raw)
        assert result == "[Analysis] Thinking deeply"

    def test_description_only(self):
        """Description without subject omits brackets."""
        raw = {
            "thoughts": [
                {"description": "Just a thought"},
            ]
        }
        result = _extract_thinking(raw)
        assert result == "Just a thought"

    def test_empty_thoughts(self):
        """Empty thoughts list returns None."""
        raw = {"thoughts": []}
        assert _extract_thinking(raw) is None

    def test_no_thoughts_key(self):
        """Missing thoughts key returns None."""
        assert _extract_thinking({}) is None

    def test_multiple_thoughts(self):
        """Multiple thoughts joined by newlines."""
        raw = {
            "thoughts": [
                {"subject": "Step 1", "description": "First"},
                {"subject": "Step 2", "description": "Second"},
            ]
        }
        result = _extract_thinking(raw)
        assert result == "[Step 1] First\n[Step 2] Second"

    def test_non_dict_thoughts_skipped(self):
        """Non-dict items in thoughts list are skipped."""
        raw = {
            "thoughts": [
                "not a dict",
                {"subject": "OK", "description": "Valid"},
            ]
        }
        result = _extract_thinking(raw)
        assert result == "[OK] Valid"

    def test_thinking_in_full_parse(self, tmp_path: Path):
        """Thinking is attached to parsed messages."""
        messages = [
            {
                "type": "gemini",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "answer",
                "thoughts": [
                    {"subject": "Reason", "description": "Because..."},
                ],
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        print(f"  thinking: {parsed[0].thinking}")
        assert parsed[0].thinking == "[Reason] Because..."


# ─── TestToolCalls
class TestToolCalls:
    """Tests for embedded tool call parsing."""

    def test_tool_call_with_result(self, tmp_path: Path):
        """Tool call with functionResponse result is extracted."""
        messages = [
            {
                "type": "gemini",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "Let me check.",
                "toolCalls": [
                    {
                        "id": "tc-1",
                        "name": "ReadFile",
                        "args": {"path": "test.py"},
                        "result": [
                            {
                                "functionResponse": {
                                    "id": "tc-1",
                                    "name": "ReadFile",
                                    "response": {
                                        "output": "file content"
                                    },
                                }
                            }
                        ],
                        "status": "ok",
                    }
                ],
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        tc = parsed[0].tool_calls[0]
        assert tc.name == "ReadFile"
        assert tc.id == "tc-1"
        assert tc.input == {"path": "test.py"}
        assert tc.output == "file content"
        assert tc.is_error is False

    def test_tool_call_error_status(self, tmp_path: Path):
        """Tool call with status='error' sets is_error=True."""
        messages = [
            {
                "type": "gemini",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "Oops",
                "toolCalls": [
                    {
                        "id": "tc-err",
                        "name": "Bash",
                        "args": {"cmd": "rm -rf /"},
                        "result": [],
                        "status": "error",
                    }
                ],
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        assert parsed[0].tool_calls[0].is_error is True

    def test_tool_call_missing_result(self, tmp_path: Path):
        """Tool call without result array has output=None."""
        messages = [
            {
                "type": "gemini",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "Calling tool...",
                "toolCalls": [
                    {
                        "id": "tc-no-result",
                        "name": "Search",
                        "args": {"q": "foo"},
                    }
                ],
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        tc = parsed[0].tool_calls[0]
        assert tc.output is None
        assert tc.is_error is False

    def test_multiple_tool_calls(self, tmp_path: Path):
        """Multiple tool calls in one message are all captured."""
        messages = [
            {
                "type": "gemini",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "Working...",
                "toolCalls": [
                    {"id": "tc-1", "name": "Read", "args": {}},
                    {"id": "tc-2", "name": "Write", "args": {}},
                ],
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        assert len(parsed[0].tool_calls) == 2
        names = [tc.name for tc in parsed[0].tool_calls]
        assert names == ["Read", "Write"]

    def test_tool_call_count_in_summary(self, tmp_path: Path):
        """Summary tool_call_count reflects total tools."""
        messages = [
            {
                "type": "gemini",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "done",
                "toolCalls": [
                    {"id": "tc-1", "name": "Read", "args": {}},
                    {"id": "tc-2", "name": "Edit", "args": {}},
                    {"id": "tc-3", "name": "Bash", "args": {}},
                ],
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        summary, _ = _parser.parse_file(path)[0]
        assert summary.tool_call_count == 3


# ─── TestSubagentKind
class TestSubagentKind:
    """Tests for kind='subagent' sidechain marking."""

    def test_subagent_marks_all_sidechain(self, tmp_path: Path):
        """All messages are marked is_sidechain when kind=subagent."""
        data = _make_session(kind="subagent")
        path = tmp_path / "session.json"
        _write_session_json(path, data)

        _, messages = _parser.parse_file(path)[0]
        for msg in messages:
            assert msg.is_sidechain is True

    def test_normal_session_not_sidechain(self, tmp_path: Path):
        """Messages in a normal session are not marked as sidechain."""
        data = _make_session()
        path = tmp_path / "session.json"
        _write_session_json(path, data)

        _, messages = _parser.parse_file(path)[0]
        for msg in messages:
            assert msg.is_sidechain is False

    def test_other_kind_not_sidechain(self, tmp_path: Path):
        """Non-subagent kind values do not trigger sidechain."""
        data = _make_session(kind="primary")
        path = tmp_path / "session.json"
        _write_session_json(path, data)

        _, messages = _parser.parse_file(path)[0]
        for msg in messages:
            assert msg.is_sidechain is False


# ─── TestMalformedInput
class TestMalformedInput:
    """Tests for malformed or invalid input handling."""

    def test_malformed_json(self, tmp_path: Path):
        """Non-parseable JSON returns empty list."""
        path = tmp_path / "bad.json"
        path.write_text("{not valid json!!!}")
        results = _parser.parse_file(path)
        assert results == []

    def test_invalid_message_types_skipped(self, tmp_path: Path):
        """Messages with unrecognized types are ignored."""
        messages = [
            {
                "type": "system",
                "id": "m0",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "system prompt",
            },
            {
                "type": "user",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:01Z",
                "content": [{"text": "Hello"}],
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        assert len(parsed) == 1
        assert parsed[0].role == "user"

    def test_non_dict_messages_skipped(self, tmp_path: Path):
        """Non-dict items in the messages array are skipped."""
        messages = [
            "not a dict",
            42,
            {
                "type": "gemini",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "valid",
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        assert len(parsed) == 1
        assert parsed[0].content == "valid"

    def test_non_dict_tool_calls_skipped(self, tmp_path: Path):
        """Non-dict items in toolCalls are silently skipped."""
        messages = [
            {
                "type": "gemini",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "result",
                "toolCalls": [
                    "not a dict",
                    {"id": "tc-1", "name": "Read", "args": {}},
                ],
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        assert len(parsed[0].tool_calls) == 1


# ─── TestGeminiTokens
class TestGeminiTokens:
    """Tests for Gemini token parsing."""

    def test_full_token_fields(self):
        """Input, output, and cached fields are mapped."""
        tokens = {"input": 100, "output": 50, "cached": 20}
        usage = _parse_gemini_tokens(tokens)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.cache_read_tokens == 20

    def test_partial_tokens(self):
        """Missing fields default to zero."""
        usage = _parse_gemini_tokens({"input": 200})
        assert usage.input_tokens == 200
        assert usage.output_tokens == 0
        assert usage.cache_read_tokens == 0

    def test_none_tokens(self):
        """None tokens returns None usage."""
        assert _parse_gemini_tokens(None) is None

    def test_empty_dict_tokens(self):
        """Empty dict is falsy in Python, so returns None."""
        assert _parse_gemini_tokens({}) is None

    def test_tokens_in_full_parse(self, tmp_path: Path):
        """Token usage is attached to parsed gemini messages."""
        messages = [
            {
                "type": "gemini",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "answer",
                "model": "gemini-2.5-pro",
                "tokens": {
                    "input": 500,
                    "output": 200,
                    "cached": 100,
                },
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        assert parsed[0].usage is not None
        assert parsed[0].usage.input_tokens == 500
        assert parsed[0].usage.output_tokens == 200
        assert parsed[0].usage.cache_read_tokens == 100

    def test_extra_token_fields_ignored(self):
        """Gemini-specific fields like 'thoughts' and 'tool' are dropped."""
        tokens = {
            "input": 100,
            "output": 50,
            "cached": 10,
            "thoughts": 30,
            "tool": 20,
            "total": 210,
        }
        usage = _parse_gemini_tokens(tokens)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.cache_read_tokens == 10


# ─── TestProjectHashResolution
class TestProjectHashResolution:
    """Tests for resolve_project_path with different strategies."""

    def test_project_root_file(self, tmp_path: Path):
        """Fast path: .project_root file is read."""
        gemini_dir = tmp_path / ".gemini"
        hash_dir = "abc123hash"
        project_dir = gemini_dir / "tmp" / hash_dir
        project_dir.mkdir(parents=True)
        (project_dir / ".project_root").write_text(
            "/Users/dev/my-project"
        )

        result = resolve_project_path(hash_dir, gemini_dir)
        assert result == "/Users/dev/my-project"

    def test_projects_json_lookup(self, tmp_path: Path):
        """Medium path: projects.json reverse lookup by hash."""
        gemini_dir = tmp_path / ".gemini"
        gemini_dir.mkdir(parents=True)
        (gemini_dir / "tmp").mkdir()

        projects = {
            "/Users/dev/my-app": {"hash": "def456hash"},
            "/Users/dev/other": {"hash": "ghi789hash"},
        }
        with open(gemini_dir / "projects.json", "w") as f:
            json.dump(projects, f)

        result = resolve_project_path("def456hash", gemini_dir)
        assert result == "/Users/dev/my-app"

    def test_fallback_to_hash(self, tmp_path: Path):
        """Fallback: returns the hash string when nothing resolves."""
        gemini_dir = tmp_path / ".gemini"
        gemini_dir.mkdir(parents=True)
        (gemini_dir / "tmp").mkdir()

        result = resolve_project_path("unknown_hash", gemini_dir)
        assert result == "unknown_hash"

    def test_project_root_takes_precedence(self, tmp_path: Path):
        """.project_root wins over projects.json."""
        gemini_dir = tmp_path / ".gemini"
        hash_dir = "priority_hash"
        project_dir = gemini_dir / "tmp" / hash_dir
        project_dir.mkdir(parents=True)
        (project_dir / ".project_root").write_text("/from/root/file")

        # Also set up projects.json with a different mapping
        projects = {"/from/projects/json": {"hash": hash_dir}}
        with open(gemini_dir / "projects.json", "w") as f:
            json.dump(projects, f)

        result = resolve_project_path(hash_dir, gemini_dir)
        assert result == "/from/root/file"

    def test_empty_project_root_falls_through(self, tmp_path: Path):
        """Empty .project_root file falls through to projects.json."""
        gemini_dir = tmp_path / ".gemini"
        hash_dir = "empty_root_hash"
        project_dir = gemini_dir / "tmp" / hash_dir
        project_dir.mkdir(parents=True)
        (project_dir / ".project_root").write_text("   \n  ")

        projects = {"/from/json": {"hash": hash_dir}}
        with open(gemini_dir / "projects.json", "w") as f:
            json.dump(projects, f)

        result = resolve_project_path(hash_dir, gemini_dir)
        assert result == "/from/json"

    def test_project_path_in_summary(self, tmp_path: Path):
        """Resolved project path populates summary fields."""
        gemini_dir = tmp_path / ".gemini"
        hash_dir = "proj_hash"
        chats_dir = gemini_dir / "tmp" / hash_dir / "chats"
        chats_dir.mkdir(parents=True)

        project_root = gemini_dir / "tmp" / hash_dir / ".project_root"
        project_root.write_text("/Users/dev/cool-project")

        session_file = chats_dir / "session-1.json"
        _write_session_json(session_file, _make_session())

        results = _parser.parse_file(session_file)
        summary, _ = results[0]
        assert summary.project_name == "cool-project"
        assert summary.project_id == "Users-dev-cool-project"


# ─── TestDuration
class TestDuration:
    """Tests for duration calculation from startTime/lastUpdated."""

    def test_duration_calculated(self, tmp_path: Path):
        """Duration is computed as lastUpdated - startTime in seconds."""
        data = _make_session(
            start_time="2025-01-15T10:00:00Z",
            last_updated="2025-01-15T10:30:00Z",
        )
        path = tmp_path / "session.json"
        _write_session_json(path, data)

        summary, _ = _parser.parse_file(path)[0]
        assert summary.duration == 1800

    def test_zero_duration(self, tmp_path: Path):
        """Same start and end times give zero duration."""
        data = _make_session(
            start_time="2025-01-15T10:00:00Z",
            last_updated="2025-01-15T10:00:00Z",
        )
        path = tmp_path / "session.json"
        _write_session_json(path, data)

        summary, _ = _parser.parse_file(path)[0]
        assert summary.duration == 0

    def test_missing_timestamps(self, tmp_path: Path):
        """Missing timestamps produce zero duration."""
        data = _make_session()
        data.pop("startTime", None)
        data.pop("lastUpdated", None)
        path = tmp_path / "session.json"
        _write_session_json(path, data)

        summary, _ = _parser.parse_file(path)[0]
        assert summary.duration == 0

    def test_missing_last_updated(self, tmp_path: Path):
        """Missing lastUpdated alone produces zero duration."""
        data = _make_session()
        data.pop("lastUpdated", None)
        path = tmp_path / "session.json"
        _write_session_json(path, data)

        summary, _ = _parser.parse_file(path)[0]
        assert summary.duration == 0

    def test_short_duration(self, tmp_path: Path):
        """Sub-minute durations are calculated correctly."""
        data = _make_session(
            start_time="2025-01-15T10:00:00Z",
            last_updated="2025-01-15T10:00:45Z",
        )
        path = tmp_path / "session.json"
        _write_session_json(path, data)

        summary, _ = _parser.parse_file(path)[0]
        assert summary.duration == 45


# ─── TestToolEnrichment
class TestToolEnrichment:
    """Tests that parse_file enriches tool calls with category and summary."""

    def test_read_file_enriched(self, tmp_path: Path):
        messages = [
            {
                "type": "gemini",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "Reading...",
                "toolCalls": [
                    {
                        "id": "tc-1",
                        "name": "ReadFile",
                        "args": {"path": "src/app.ts"},
                    },
                ],
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        tc = parsed[0].tool_calls[0]
        print(f"  name={tc.name}, category={tc.category}, summary={tc.summary}")
        # ReadFile is not in the map, so it falls back to "other"
        # and summary picks up the first string value
        assert tc.category == "other"
        assert tc.summary == "src/app.ts"

    def test_bash_tool_enriched(self, tmp_path: Path):
        messages = [
            {
                "type": "gemini",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "Running...",
                "toolCalls": [
                    {
                        "id": "tc-1",
                        "name": "Bash",
                        "args": {"command": "pytest -v"},
                    },
                ],
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        tc = parsed[0].tool_calls[0]
        assert tc.category == "shell"
        assert tc.summary == "pytest -v"

    def test_multiple_tools_all_enriched(self, tmp_path: Path):
        messages = [
            {
                "type": "gemini",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "Working...",
                "toolCalls": [
                    {"id": "tc-1", "name": "Read", "args": {"file_path": "/a.py"}},
                    {"id": "tc-2", "name": "Edit", "args": {"file_path": "/b.py"}},
                    {"id": "tc-3", "name": "Grep", "args": {"pattern": "TODO"}},
                ],
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))

        _, parsed = _parser.parse_file(path)[0]
        categories = [tc.category for tc in parsed[0].tool_calls]
        assert categories == ["file_read", "file_write", "search"]
