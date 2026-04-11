"""Unit tests for vibelens.ingest.gemini parser."""

import json
from pathlib import Path

from vibelens.ingest.parsers.base import is_error_content
from vibelens.ingest.parsers.gemini import (
    GeminiParser,
    _extract_thinking,
    _parse_gemini_tokens,
    resolve_project_path,
)
from vibelens.models.enums import StepSource

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


class TestParseFile:
    """Tests for GeminiParser.parse_file high-level behavior."""

    def test_basic_session(self, tmp_path: Path):
        """Parse a standard session and verify all core trajectory fields."""
        path = tmp_path / "session-1.json"
        _write_session_json(path, _make_session(session_id="abc"))

        results = _parser.parse_file(path)
        assert len(results) == 1
        traj = results[0]
        print(f"  traj: id={traj.session_id}, agent={traj.agent.name}")
        print(f"  first_message={traj.first_message}")
        print(f"  steps: {len(traj.steps)}")
        for s in traj.steps:
            print(f"    source={s.source}, model_name={s.model_name}")

        # Session identity
        assert traj.session_id == "abc"
        assert traj.agent.name == "gemini"
        assert len(traj.steps) == 2

        # Model name propagated to agent steps
        agent_steps = [s for s in traj.steps if s.source == StepSource.AGENT]
        model_names = [s.model_name for s in agent_steps if s.model_name]
        assert "gemini-2.5-pro" in model_names

        # First user message extracted
        assert traj.first_message == "Hello"

        # Source normalization: gemini -> AGENT, user -> USER
        user_steps = [s for s in traj.steps if s.source == StepSource.USER]
        assert len(user_steps) == 1
        assert len(agent_steps) == 1

    def test_edge_cases(self, tmp_path: Path):
        """Empty file, missing file, missing/empty session ID, and empty messages all return []."""
        # Empty file
        empty_path = tmp_path / "empty.json"
        empty_path.write_text("")
        assert _parser.parse_file(empty_path) == []

        # Non-existent file
        assert _parser.parse_file(tmp_path / "missing.json") == []

        # Missing sessionId key
        data_no_id = _make_session()
        data_no_id.pop("sessionId")
        no_id_path = tmp_path / "no-id.json"
        _write_session_json(no_id_path, data_no_id)
        assert _parser.parse_file(no_id_path) == []

        # Empty sessionId string
        empty_id_path = tmp_path / "empty-id.json"
        _write_session_json(empty_id_path, _make_session(session_id=""))
        assert _parser.parse_file(empty_id_path) == []

        # Empty message list
        no_msgs_path = tmp_path / "no-msgs.json"
        _write_session_json(no_msgs_path, _make_session(messages=[]))
        assert _parser.parse_file(no_msgs_path) == []

    def test_content_formats(self, tmp_path: Path):
        """Various user content types: array, string, empty array, non-string coercion."""
        # Content array concatenation
        array_msgs = [
            {
                "type": "user",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": [{"text": "Line one"}, {"text": "Line two"}],
            },
        ]
        path = tmp_path / "array.json"
        _write_session_json(path, _make_session(messages=array_msgs))
        traj = _parser.parse_file(path)[0]
        assert traj.steps[0].message == "Line one\nLine two"

        # Plain string content
        string_msgs = [
            {
                "type": "user",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "Just a string",
            },
        ]
        path = tmp_path / "string.json"
        _write_session_json(path, _make_session(messages=string_msgs))
        traj = _parser.parse_file(path)[0]
        assert traj.steps[0].message == "Just a string"

        # Empty content array produces empty string
        empty_msgs = [
            {
                "type": "user",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": [],
            },
            {
                "type": "gemini",
                "id": "m2",
                "timestamp": "2025-01-15T10:00:05Z",
                "content": "reply",
            },
        ]
        path = tmp_path / "empty-content.json"
        _write_session_json(path, _make_session(messages=empty_msgs))
        traj = _parser.parse_file(path)[0]
        user_step = [s for s in traj.steps if s.source == StepSource.USER][0]
        assert user_step.message == ""

        # Non-list, non-string content coerced to string
        numeric_msgs = [
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
        path = tmp_path / "numeric.json"
        _write_session_json(path, _make_session(messages=numeric_msgs))
        traj = _parser.parse_file(path)[0]
        user_step = [s for s in traj.steps if s.source == StepSource.USER][0]
        assert user_step.message == "42"


class TestThinkingExtraction:
    """Tests for _extract_thinking helper and integration with parsing."""

    def test_thinking_helper(self):
        """Exercise all branches: subject+desc, desc-only, empty, missing, multi, non-dict."""
        # Subject and description formatted as [Subject] desc
        raw = {"thoughts": [{"subject": "Analysis", "description": "Thinking deeply"}]}
        assert _extract_thinking(raw) == "[Analysis] Thinking deeply"

        # Description only omits brackets
        raw = {"thoughts": [{"description": "Just a thought"}]}
        assert _extract_thinking(raw) == "Just a thought"

        # Empty thoughts list returns None
        assert _extract_thinking({"thoughts": []}) is None

        # Missing thoughts key returns None
        assert _extract_thinking({}) is None

        # Multiple thoughts joined by newlines
        raw = {
            "thoughts": [
                {"subject": "Step 1", "description": "First"},
                {"subject": "Step 2", "description": "Second"},
            ]
        }
        assert _extract_thinking(raw) == "[Step 1] First\n[Step 2] Second"

        # Non-dict items skipped
        raw = {
            "thoughts": [
                "not a dict",
                {"subject": "OK", "description": "Valid"},
            ]
        }
        assert _extract_thinking(raw) == "[OK] Valid"

    def test_thinking_in_full_parse(self, tmp_path: Path):
        """Thinking is attached to parsed steps."""
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

        traj = _parser.parse_file(path)[0]
        print(f"  reasoning_content: {traj.steps[0].reasoning_content}")
        assert traj.steps[0].reasoning_content == "[Reason] Because..."


class TestToolCalls:
    """Tests for embedded tool call parsing."""

    def test_tool_call_parsing(self, tmp_path: Path):
        """Tool call with result, multiple calls, and final metrics tool count."""
        # Single tool call with functionResponse result
        messages_single = [
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
                                    "response": {"output": "file content"},
                                }
                            }
                        ],
                        "status": "ok",
                    }
                ],
            },
        ]
        path = tmp_path / "single-tc.json"
        _write_session_json(path, _make_session(messages=messages_single))
        traj = _parser.parse_file(path)[0]
        tc = traj.steps[0].tool_calls[0]
        assert tc.function_name == "ReadFile"
        assert tc.tool_call_id == "tc-1"
        assert tc.arguments == {"path": "test.py"}
        assert traj.steps[0].observation is not None
        assert traj.steps[0].observation.results[0].content == "file content"
        assert not is_error_content(traj.steps[0].observation.results[0].content)

        # Multiple tool calls in one step
        messages_multi = [
            {
                "type": "gemini",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "Working...",
                "toolCalls": [
                    {"id": "tc-1", "name": "Read", "args": {}},
                    {"id": "tc-2", "name": "Write", "args": {}},
                    {"id": "tc-3", "name": "Bash", "args": {}},
                ],
            },
        ]
        path = tmp_path / "multi-tc.json"
        _write_session_json(path, _make_session(messages=messages_multi))
        traj = _parser.parse_file(path)[0]
        assert len(traj.steps[0].tool_calls) == 3
        names = [tc.function_name for tc in traj.steps[0].tool_calls]
        assert names == ["Read", "Write", "Bash"]
        # Final metrics reflect total tool count
        assert traj.final_metrics is not None
        assert traj.final_metrics.tool_call_count == 3

    def test_tool_call_errors(self, tmp_path: Path):
        """Error status marks content, missing result yields no observation content."""
        # Error status
        error_msgs = [
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
        path = tmp_path / "error-tc.json"
        _write_session_json(path, _make_session(messages=error_msgs))
        traj = _parser.parse_file(path)[0]
        assert traj.steps[0].observation is not None
        assert is_error_content(traj.steps[0].observation.results[0].content)

        # Missing result array
        no_result_msgs = [
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
        path = tmp_path / "no-result-tc.json"
        _write_session_json(path, _make_session(messages=no_result_msgs))
        traj = _parser.parse_file(path)[0]
        if traj.steps[0].observation:
            assert traj.steps[0].observation.results[0].content is None
            assert not is_error_content(traj.steps[0].observation.results[0].content)


class TestMalformedInput:
    """Tests for malformed or invalid input handling."""

    def test_malformed_input(self, tmp_path: Path):
        """Bad JSON, invalid types, non-dict messages, and non-dict tool calls are handled."""
        # Non-parseable JSON
        bad_path = tmp_path / "bad.json"
        bad_path.write_text("{not valid json!!!}")
        assert _parser.parse_file(bad_path) == []

        # Unrecognized message types are skipped
        invalid_type_msgs = [
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
        path = tmp_path / "invalid-type.json"
        _write_session_json(path, _make_session(messages=invalid_type_msgs))
        traj = _parser.parse_file(path)[0]
        assert len(traj.steps) == 1
        assert traj.steps[0].source == StepSource.USER

        # Non-dict items in messages array are skipped
        non_dict_msgs = [
            "not a dict",
            42,
            {
                "type": "gemini",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "valid",
            },
        ]
        path = tmp_path / "non-dict-msgs.json"
        _write_session_json(path, _make_session(messages=non_dict_msgs))
        traj = _parser.parse_file(path)[0]
        assert len(traj.steps) == 1
        assert traj.steps[0].message == "valid"

        # Non-dict items in toolCalls are skipped
        non_dict_tc_msgs = [
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
        path = tmp_path / "non-dict-tc.json"
        _write_session_json(path, _make_session(messages=non_dict_tc_msgs))
        traj = _parser.parse_file(path)[0]
        assert len(traj.steps[0].tool_calls) == 1


class TestGeminiTokens:
    """Tests for Gemini token parsing."""

    def test_token_parsing(self, tmp_path: Path):
        """Full fields, partial fields, None, extra fields, and integration with parse."""
        # Full token fields
        metrics = _parse_gemini_tokens({"input": 100, "output": 50, "cached": 20})
        assert metrics.prompt_tokens == 100
        assert metrics.completion_tokens == 50
        assert metrics.cached_tokens == 20

        # Partial tokens: missing fields default to zero
        metrics = _parse_gemini_tokens({"input": 200})
        assert metrics.prompt_tokens == 200
        assert metrics.completion_tokens == 0
        assert metrics.cached_tokens == 0

        # None returns None
        assert _parse_gemini_tokens(None) is None

        # Extra Gemini-specific fields (thoughts, tool, total) are ignored
        tokens_extra = {
            "input": 100,
            "output": 50,
            "cached": 10,
            "thoughts": 30,
            "tool": 20,
            "total": 210,
        }
        metrics = _parse_gemini_tokens(tokens_extra)
        assert metrics.prompt_tokens == 100
        assert metrics.completion_tokens == 50
        assert metrics.cached_tokens == 10

        # Tokens in full parse are attached to step metrics
        messages = [
            {
                "type": "gemini",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "answer",
                "model": "gemini-2.5-pro",
                "tokens": {"input": 500, "output": 200, "cached": 100},
            },
        ]
        path = tmp_path / "session.json"
        _write_session_json(path, _make_session(messages=messages))
        traj = _parser.parse_file(path)[0]
        assert traj.steps[0].metrics is not None
        assert traj.steps[0].metrics.prompt_tokens == 500
        assert traj.steps[0].metrics.completion_tokens == 200
        assert traj.steps[0].metrics.cached_tokens == 100


class TestProjectHashResolution:
    """Tests for resolve_project_path with different strategies."""

    def test_project_path_resolution(self, tmp_path: Path):
        """All resolution strategies: .project_root, projects.json, fallback, precedence."""
        gemini_dir = tmp_path / ".gemini"

        # .project_root file is read
        hash_dir = "abc123hash"
        project_dir = gemini_dir / "tmp" / hash_dir
        project_dir.mkdir(parents=True)
        (project_dir / ".project_root").write_text("/Users/dev/my-project")
        assert resolve_project_path(hash_dir, gemini_dir) == "/Users/dev/my-project"

        # projects.json reverse lookup by hash
        (gemini_dir / "tmp" / "def456hash").mkdir(parents=True)
        projects = {
            "/Users/dev/my-app": {"hash": "def456hash"},
            "/Users/dev/other": {"hash": "ghi789hash"},
        }
        with open(gemini_dir / "projects.json", "w") as f:
            json.dump(projects, f)
        assert resolve_project_path("def456hash", gemini_dir) == "/Users/dev/my-app"

        # Fallback to hash string when nothing resolves
        assert resolve_project_path("unknown_hash", gemini_dir) == "unknown_hash"

        # .project_root takes precedence over projects.json
        priority_hash = "priority_hash"
        priority_dir = gemini_dir / "tmp" / priority_hash
        priority_dir.mkdir(parents=True)
        (priority_dir / ".project_root").write_text("/from/root/file")
        projects["/from/projects/json"] = {"hash": priority_hash}
        with open(gemini_dir / "projects.json", "w") as f:
            json.dump(projects, f)
        assert resolve_project_path(priority_hash, gemini_dir) == "/from/root/file"

        # Empty .project_root falls through to projects.json
        empty_root_hash = "empty_root_hash"
        empty_root_dir = gemini_dir / "tmp" / empty_root_hash
        empty_root_dir.mkdir(parents=True)
        (empty_root_dir / ".project_root").write_text("   \n  ")
        projects["/from/json"] = {"hash": empty_root_hash}
        with open(gemini_dir / "projects.json", "w") as f:
            json.dump(projects, f)
        assert resolve_project_path(empty_root_hash, gemini_dir) == "/from/json"

    def test_project_path_in_trajectory(self, tmp_path: Path):
        """Resolved project path populates trajectory project_path."""
        gemini_dir = tmp_path / ".gemini"
        hash_dir = "proj_hash"
        chats_dir = gemini_dir / "tmp" / hash_dir / "chats"
        chats_dir.mkdir(parents=True)

        project_root = gemini_dir / "tmp" / hash_dir / ".project_root"
        project_root.write_text("/Users/dev/cool-project")

        session_file = chats_dir / "session-1.json"
        _write_session_json(session_file, _make_session())

        results = _parser.parse_file(session_file)
        traj = results[0]
        assert traj.project_path == "/Users/dev/cool-project"


class TestDuration:
    """Tests for duration calculation from step timestamps."""

    def test_duration(self, tmp_path: Path):
        """Standard, zero, short, and missing-header timestamp durations."""
        # Standard 5-second gap from default messages
        path = tmp_path / "standard.json"
        _write_session_json(path, _make_session())
        traj = _parser.parse_file(path)[0]
        assert traj.final_metrics is not None
        assert traj.final_metrics.duration == 5

        # Same timestamps give zero duration
        zero_msgs = [
            {
                "type": "user",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": [{"text": "Hello"}],
            },
            {
                "type": "gemini",
                "id": "m2",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": "Hi there",
                "model": "gemini-2.5-pro",
            },
        ]
        path = tmp_path / "zero.json"
        _write_session_json(path, _make_session(messages=zero_msgs))
        traj = _parser.parse_file(path)[0]
        assert traj.final_metrics is not None
        assert traj.final_metrics.duration == 0

        # Sub-minute (45-second) duration
        short_msgs = [
            {
                "type": "user",
                "id": "m1",
                "timestamp": "2025-01-15T10:00:00Z",
                "content": [{"text": "Hello"}],
            },
            {
                "type": "gemini",
                "id": "m2",
                "timestamp": "2025-01-15T10:00:45Z",
                "content": "Hi there",
                "model": "gemini-2.5-pro",
            },
        ]
        path = tmp_path / "short.json"
        _write_session_json(path, _make_session(messages=short_msgs))
        traj = _parser.parse_file(path)[0]
        assert traj.final_metrics is not None
        assert traj.final_metrics.duration == 45

        # Missing session-level timestamps still produce valid duration from step timestamps
        data = _make_session()
        data.pop("startTime", None)
        data.pop("lastUpdated", None)
        path = tmp_path / "no-header-ts.json"
        _write_session_json(path, data)
        traj = _parser.parse_file(path)[0]
        assert traj.final_metrics is not None
        assert isinstance(traj.final_metrics.duration, int)
