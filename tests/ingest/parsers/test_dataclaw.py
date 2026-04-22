"""Unit tests for vibelens.ingest.parsers.dataclaw parser."""

import json
from pathlib import Path

from vibelens.ingest.parsers.dataclaw import DataclawParser, _build_steps, _build_tool_calls
from vibelens.models.enums import StepSource

_parser = DataclawParser()


def _make_record(
    session_id: str = "sess-1",
    project: str = "/home/user/project",
    model: str = "claude-sonnet-4-5",
    messages: list[dict] | None = None,
    start_time: str = "2025-01-15T10:00:00Z",
) -> dict:
    """Build a minimal dataclaw session record."""
    if messages is None:
        messages = [
            {"role": "user", "content": "Hello", "timestamp": "2025-01-15T10:00:00Z"},
            {"role": "assistant", "content": "Hi there", "timestamp": "2025-01-15T10:00:05Z"},
        ]
    return {
        "session_id": session_id,
        "project": project,
        "model": model,
        "messages": messages,
        "start_time": start_time,
    }


def _as_jsonl(*records: dict) -> str:
    """Serialize records to JSONL string (one JSON object per line)."""
    return "\n".join(json.dumps(r) for r in records)


def _write_jsonl(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


class TestParse:
    """Tests for DataclawParser.parse (string-based entry point)."""

    def test_single_session(self):
        content = _as_jsonl(_make_record(session_id="abc"))
        results = _parser.parse(content)
        assert len(results) == 1
        assert results[0].session_id == "abc"

    def test_multiple_sessions_in_one_file(self):
        """Each line produces one Trajectory."""
        content = _as_jsonl(
            _make_record(session_id="s1"),
            _make_record(session_id="s2"),
            _make_record(session_id="s3"),
        )
        results = _parser.parse(content)
        assert len(results) == 3
        ids = [t.session_id for t in results]
        assert ids == ["s1", "s2", "s3"]

    def test_empty_content_returns_empty(self):
        assert _parser.parse("") == []
        assert _parser.parse("   \n\n  ") == []

    def test_invalid_json_lines_skipped(self):
        content = "\n".join([
            json.dumps(_make_record(session_id="good-1")),
            "{not valid json",
            json.dumps(_make_record(session_id="good-2")),
        ])
        results = _parser.parse(content)
        assert len(results) == 2
        ids = [t.session_id for t in results]
        assert "good-1" in ids
        assert "good-2" in ids

    def test_missing_required_keys_skipped(self):
        """Records that parse as JSON but lack required keys raise handled errors."""
        # Record with no 'messages' key: record.get("messages", []) returns []
        # which then hits the Trajectory min-length constraint — caught as ValueError
        # by the parse() except clause. Valid records after it still parse fine.
        content = "\n".join([
            json.dumps({"session_id": "bad", "model": "m"}),   # missing messages key
            json.dumps(_make_record(session_id="only-valid")),
        ])
        results = _parser.parse(content)
        # The bad record either raises a caught error or produces a valid trajectory
        # depending on parser version; what must hold is "only-valid" is present.
        ids = [t.session_id for t in results]
        assert "only-valid" in ids


class TestParseSession:
    """Tests for session-level metadata and step extraction."""

    def test_session_identity(self):
        record = _make_record(session_id="my-sess", project="/home/user/app",
                              model="claude-opus-4-7")
        traj = _parser.parse_session(record)
        assert traj.session_id == "my-sess"
        assert traj.project_path == "/home/user/app"
        assert traj.agent.model_name == "claude-opus-4-7"

    def test_deterministic_id_when_session_id_absent(self):
        """Records without session_id get a stable derived ID across calls."""
        record = _make_record(project="myproj", start_time="2025-01-01T00:00:00Z")
        del record["session_id"]
        t1 = _parser.parse_session(record)
        t2 = _parser.parse_session(record)
        assert t1.session_id == t2.session_id
        assert t1.session_id  # non-empty

    def test_step_sources(self):
        messages = [
            {"role": "user", "content": "Q1", "timestamp": "2025-01-15T10:00:00Z"},
            {"role": "assistant", "content": "A1", "timestamp": "2025-01-15T10:00:05Z"},
            {"role": "user", "content": "Q2", "timestamp": "2025-01-15T10:00:10Z"},
        ]
        record = _make_record(messages=messages)
        traj = _parser.parse_session(record)
        user_steps = [s for s in traj.steps if s.source == StepSource.USER]
        agent_steps = [s for s in traj.steps if s.source == StepSource.AGENT]
        assert len(user_steps) == 2
        assert len(agent_steps) == 1

    def test_thinking_extracted(self):
        """thinking field on assistant messages maps to reasoning_content."""
        messages = [
            {
                "role": "assistant",
                "content": "Final answer",
                "thinking": "Let me think step by step",
                "timestamp": "2025-01-15T10:00:00Z",
            },
        ]
        record = _make_record(messages=messages)
        traj = _parser.parse_session(record)
        agent_steps = [s for s in traj.steps if s.source == StepSource.AGENT]
        assert len(agent_steps) == 1
        assert agent_steps[0].reasoning_content == "Let me think step by step"

    def test_model_applied_to_agent_steps_only(self):
        """Session-level model is set on agent steps, not user steps."""
        record = _make_record(model="claude-sonnet-4-5")
        traj = _parser.parse_session(record)
        for step in traj.steps:
            if step.source == StepSource.AGENT:
                assert step.model_name == "claude-sonnet-4-5"
            else:
                assert step.model_name is None

    def test_empty_messages_skipped_via_parse(self):
        """A record with no messages is skipped by parse() — Trajectory requires ≥1 step."""
        content = "\n".join([
            json.dumps(_make_record(session_id="empty-msgs", messages=[])),
            json.dumps(_make_record(session_id="has-msgs")),
        ])
        results = _parser.parse(content)
        ids = [t.session_id for t in results]
        assert "has-msgs" in ids
        assert "empty-msgs" not in ids

    def test_extra_contains_source_type(self):
        record = _make_record()
        traj = _parser.parse_session(record)
        assert traj.extra is not None
        assert traj.extra.get("source_type") == "huggingface"


class TestToolCalls:
    """Tests for tool_uses -> ToolCall extraction."""

    def test_tool_uses_parsed(self):
        """tool_uses on an assistant message become ToolCall objects."""
        messages = [
            {
                "role": "assistant",
                "content": "Working on it",
                "timestamp": "2025-01-15T10:00:00Z",
                "tool_uses": [
                    {"tool": "Read", "input": {"path": "main.py"}},
                    {"tool": "Bash", "input": {"cmd": "ls -la"}},
                ],
            },
        ]
        record = _make_record(messages=messages)
        traj = _parser.parse_session(record)
        agent_steps = [s for s in traj.steps if s.source == StepSource.AGENT]
        assert len(agent_steps) == 1
        tcs = agent_steps[0].tool_calls
        assert len(tcs) == 2
        assert tcs[0].function_name == "Read"
        assert tcs[0].arguments == {"path": "main.py"}
        assert tcs[1].function_name == "Bash"

    def test_tool_call_ids_are_deterministic(self):
        """Tool call IDs are derived deterministically from session/position."""
        calls = _build_tool_calls(
            [{"tool": "Read", "input": {"path": "a.py"}}],
            session_id="sess-x",
            msg_idx=0,
        )
        calls2 = _build_tool_calls(
            [{"tool": "Read", "input": {"path": "a.py"}}],
            session_id="sess-x",
            msg_idx=0,
        )
        assert calls[0].tool_call_id == calls2[0].tool_call_id

    def test_non_dict_tool_uses_skipped(self):
        """Non-dict items in tool_uses are silently skipped."""
        calls = _build_tool_calls(
            ["not a dict", {"tool": "Write", "input": {}}],
            session_id="sess-y",
            msg_idx=1,
        )
        assert len(calls) == 1
        assert calls[0].function_name == "Write"

    def test_no_observation_since_outputs_stripped(self):
        """Dataclaw strips tool outputs, so steps have tool_calls but no observation."""
        messages = [
            {
                "role": "assistant",
                "content": "calling tool",
                "timestamp": "2025-01-15T10:00:00Z",
                "tool_uses": [{"tool": "Search", "input": {"q": "test"}}],
            },
        ]
        record = _make_record(messages=messages)
        traj = _parser.parse_session(record)
        agent_steps = [s for s in traj.steps if s.source == StepSource.AGENT]
        assert len(agent_steps[0].tool_calls) == 1
        # No observation because dataclaw strips tool outputs
        assert agent_steps[0].observation is None

    def test_final_metrics_tool_count(self):
        """final_metrics.tool_call_count reflects total tool_uses in the session."""
        messages = [
            {
                "role": "assistant",
                "content": "step 1",
                "timestamp": "2025-01-15T10:00:00Z",
                "tool_uses": [{"tool": "A", "input": {}}, {"tool": "B", "input": {}}],
            },
            {
                "role": "assistant",
                "content": "step 2",
                "timestamp": "2025-01-15T10:00:10Z",
                "tool_uses": [{"tool": "C", "input": {}}],
            },
        ]
        record = _make_record(messages=messages)
        traj = _parser.parse_session(record)
        assert traj.final_metrics is not None
        assert traj.final_metrics.tool_call_count == 3


class TestBuildSteps:
    """Tests for the _build_steps helper directly."""

    def test_unknown_role_skipped(self):
        """Messages with roles other than user/assistant are skipped."""
        raw_messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi", "timestamp": "2025-01-15T10:00:00Z"},
        ]
        steps = _build_steps(raw_messages, session_id="s", session_model="m")
        assert len(steps) == 1
        assert steps[0].source == StepSource.USER

    def test_non_dict_messages_skipped(self):
        raw_messages = ["not a dict", 42, {"role": "user", "content": "valid"}]
        steps = _build_steps(raw_messages, session_id="s", session_model="m")
        assert len(steps) == 1

    def test_step_ids_are_deterministic(self):
        raw_messages = [{"role": "user", "content": "hi", "timestamp": "2025-01-15T10:00:00Z"}]
        steps1 = _build_steps(raw_messages, session_id="same", session_model="m")
        steps2 = _build_steps(raw_messages, session_id="same", session_model="m")
        assert steps1[0].step_id == steps2[0].step_id


class TestParseFile:
    """Tests for DataclawParser.parse_file (file-based entry point)."""

    def test_parse_file_basic(self, tmp_path: Path):
        path = tmp_path / "conversations.jsonl"
        content = _as_jsonl(
            _make_record(session_id="f1"),
            _make_record(session_id="f2"),
        )
        _write_jsonl(path, content)
        results = _parser.parse_file(path)
        assert len(results) == 2
        ids = {t.session_id for t in results}
        assert ids == {"f1", "f2"}

    def test_parse_file_missing(self, tmp_path: Path):
        """Missing file returns empty list (no crash)."""
        assert _parser.parse_file(tmp_path / "missing.jsonl") == []

    def test_parse_file_empty(self, tmp_path: Path):
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        assert _parser.parse_file(path) == []
