"""Unit tests for vibelens.ingest.parsers.openclaw parser."""

import json
from pathlib import Path

import pytest

from vibelens.ingest.parsers.base import is_error_content
from vibelens.ingest.parsers.openclaw import (
    OpenClawParser,
    _build_metrics,
    _collect_tool_results,
    _decompose_content,
    _extract_session_meta,
)
from vibelens.models.enums import StepSource

_parser = OpenClawParser()


def _make_event(**kwargs) -> str:
    """Serialize a single event dict to a JSONL line."""
    return json.dumps(kwargs)


def _build_session(
    session_id: str = "sess-abc",
    cwd: str = "/home/user/project",
    model_provider: str = "anthropic",
    model_id: str = "claude-sonnet-4-5",
    messages: list[dict] | None = None,
) -> str:
    """Assemble a minimal valid OpenClaw JSONL session string."""
    if messages is None:
        messages = [
            {
                "type": "message",
                "id": "step-1",
                "timestamp": "2025-01-15T10:00:00Z",
                "message": {"role": "user", "content": "Hello"},
            },
            {
                "type": "message",
                "id": "step-2",
                "timestamp": "2025-01-15T10:00:05Z",
                "message": {
                    "role": "assistant",
                    "content": "Hi there",
                    "model": model_id,
                    "usage": {"input": 100, "output": 50},
                },
            },
        ]
    lines = [
        _make_event(type="session", id=session_id, cwd=cwd),
        _make_event(
            type="model_change", provider=model_provider, modelId=model_id
        ),
    ]
    for msg in messages:
        lines.append(json.dumps(msg))
    return "\n".join(lines)


def _write_session(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


class TestParseFile:
    """Tests for OpenClawParser.parse_file high-level behavior."""

    def test_basic_session(self, tmp_path: Path):
        """Parse a valid session and verify trajectory identity and step counts."""
        path = tmp_path / "session.jsonl"
        _write_session(path, _build_session(session_id="abc-123", cwd="/dev/repo"))

        results = _parser.parse_file(path)
        assert len(results) == 1
        traj = results[0]

        assert traj.session_id == "abc-123"
        assert traj.agent.name == "openclaw"
        assert traj.project_path == "/dev/repo"
        assert len(traj.steps) == 2

        user_steps = [s for s in traj.steps if s.source == StepSource.USER]
        agent_steps = [s for s in traj.steps if s.source == StepSource.AGENT]
        assert len(user_steps) == 1
        assert len(agent_steps) == 1

    def test_empty_file(self, tmp_path: Path):
        """Empty file returns empty list."""
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        assert _parser.parse_file(path) == []

    def test_missing_file(self, tmp_path: Path):
        """Non-existent file returns empty list."""
        assert _parser.parse_file(tmp_path / "missing.jsonl") == []

    def test_no_valid_messages_returns_empty(self, tmp_path: Path):
        """Session with only header events and no message steps returns empty."""
        content = "\n".join([
            _make_event(type="session", id="no-msgs", cwd="/tmp"),
            _make_event(type="model_change", provider="anthropic", modelId="claude"),
        ])
        path = tmp_path / "no-msgs.jsonl"
        _write_session(path, content)
        assert _parser.parse_file(path) == []

    def test_session_id_falls_back_to_filename(self, tmp_path: Path):
        """When no session event present, session_id comes from filename stem."""
        content = "\n".join([
            _make_event(type="message", id="s1", timestamp="2025-01-15T10:00:00Z",
                        message={"role": "user", "content": "hi"}),
        ])
        path = tmp_path / "my-session-stem.jsonl"
        _write_session(path, content)
        results = _parser.parse_file(path)
        assert len(results) == 1
        assert results[0].session_id == "my-session-stem"


class TestSessionMeta:
    """Tests for _extract_session_meta parsing header events."""

    def test_session_event_sets_id_and_cwd(self):
        entries = [{"type": "session", "id": "sess-xyz", "cwd": "/usr/local/app"}]
        meta = _extract_session_meta(entries)
        assert meta["session_id"] == "sess-xyz"
        assert meta["cwd"] == "/usr/local/app"

    def test_model_from_model_change(self):
        entries = [
            {"type": "model_change", "provider": "anthropic", "modelId": "claude-sonnet-4-5"},
        ]
        meta = _extract_session_meta(entries)
        assert meta["model"] == "anthropic/claude-sonnet-4-5"

    def test_model_change_without_provider(self):
        entries = [{"type": "model_change", "provider": "", "modelId": "gpt-5"}]
        meta = _extract_session_meta(entries)
        assert meta["model"] == "gpt-5"

    def test_model_from_custom_snapshot(self):
        entries = [
            {"type": "custom", "customType": "model-snapshot",
             "data": {"provider": "openai", "modelId": "gpt-5"}},
        ]
        meta = _extract_session_meta(entries)
        assert meta["model"] == "openai/gpt-5"

    def test_model_fallback_from_first_assistant_message(self):
        """model_change absent: falls back to first real assistant message model."""
        entries = [
            {"type": "message", "message": {
                "role": "assistant", "model": "gemini-3", "content": "hi"
            }},
        ]
        meta = _extract_session_meta(entries)
        assert meta["model"] == "gemini-3"

    def test_model_change_takes_precedence_over_fallback(self):
        """model_change header wins over assistant message model field."""
        entries = [
            {"type": "model_change", "provider": "anthropic", "modelId": "claude-opus-4-7"},
            {"type": "message", "message": {
                "role": "assistant", "model": "some-other-model", "content": "hi"
            }},
        ]
        meta = _extract_session_meta(entries)
        assert meta["model"] == "anthropic/claude-opus-4-7"

    def test_delivery_mirror_model_ignored(self):
        """delivery-mirror model is not treated as a real fallback model."""
        entries = [
            {"type": "message", "message": {
                "role": "assistant", "model": "delivery-mirror", "content": "hi"
            }},
        ]
        meta = _extract_session_meta(entries)
        assert meta["model"] is None

    def test_empty_entries(self):
        meta = _extract_session_meta([])
        assert meta["session_id"] is None
        assert meta["model"] is None
        assert meta["cwd"] is None


class TestContentDecomposition:
    """Tests for _decompose_content splitting text, thinking, and tool calls."""

    def test_string_content(self):
        message, reasoning, tool_calls = _decompose_content("plain string")
        assert message == "plain string"
        assert reasoning is None
        assert tool_calls == []

    def test_empty_string(self):
        message, reasoning, tool_calls = _decompose_content("")
        assert message == ""
        assert reasoning is None
        assert tool_calls == []

    def test_non_string_non_list(self):
        message, reasoning, tool_calls = _decompose_content(42)
        assert message == ""
        assert reasoning is None
        assert tool_calls == []

    def test_text_blocks(self):
        blocks = [{"type": "text", "text": "Hello"}, {"type": "text", "text": "World"}]
        message, reasoning, tool_calls = _decompose_content(blocks)
        assert message == "Hello\n\nWorld"
        assert reasoning is None
        assert tool_calls == []

    def test_thinking_block(self):
        blocks = [
            {"type": "thinking", "thinking": "I should respond carefully"},
            {"type": "text", "text": "Here is my answer"},
        ]
        message, reasoning, tool_calls = _decompose_content(blocks)
        assert message == "Here is my answer"
        assert reasoning == "I should respond carefully"

    def test_tool_call_block(self):
        blocks = [
            {"type": "text", "text": "Let me check"},
            {"type": "toolCall", "id": "tc-1", "name": "ReadFile",
             "arguments": {"path": "main.py"}},
        ]
        message, reasoning, tool_calls = _decompose_content(blocks)
        assert message == "Let me check"
        assert len(tool_calls) == 1
        tc = tool_calls[0]
        assert tc.tool_call_id == "tc-1"
        assert tc.function_name == "ReadFile"
        assert tc.arguments == {"path": "main.py"}

    def test_multiple_tool_calls(self):
        blocks = [
            {"type": "toolCall", "id": "tc-1", "name": "Read", "arguments": {}},
            {"type": "toolCall", "id": "tc-2", "name": "Write", "arguments": {}},
        ]
        _, _, tool_calls = _decompose_content(blocks)
        assert len(tool_calls) == 2
        assert [tc.function_name for tc in tool_calls] == ["Read", "Write"]

    def test_non_dict_blocks_skipped(self):
        blocks = ["not a dict", {"type": "text", "text": "valid"}]
        message, _, _ = _decompose_content(blocks)
        assert message == "valid"

    def test_empty_list(self):
        message, reasoning, tool_calls = _decompose_content([])
        assert message == ""
        assert reasoning is None
        assert tool_calls == []


class TestMetrics:
    """Tests for _build_metrics usage field mapping."""

    def test_full_usage(self):
        usage = {
            "input": 100,
            "output": 50,
            "cacheRead": 20,
            "cacheWrite": 5,
            "cost": {"total": 0.012},
        }
        m = _build_metrics(usage)
        assert m is not None
        assert m.prompt_tokens == 120  # input + cacheRead
        assert m.completion_tokens == 50
        assert m.cached_tokens == 20
        assert m.cache_creation_tokens == 5
        assert m.cost_usd == pytest.approx(0.012)

    def test_partial_usage(self):
        m = _build_metrics({"input": 200})
        assert m is not None
        assert m.prompt_tokens == 200
        assert m.completion_tokens == 0
        assert m.cached_tokens == 0
        assert m.cost_usd is None

    def test_none_usage(self):
        assert _build_metrics(None) is None

    def test_empty_usage(self):
        assert _build_metrics({}) is None

    def test_cost_not_dict_ignored(self):
        usage = {"input": 10, "output": 5, "cost": "not-a-dict"}
        m = _build_metrics(usage)
        assert m is not None
        assert m.cost_usd is None

    def test_metrics_in_full_parse(self, tmp_path: Path):
        """Metrics from usage block are attached to agent step."""
        messages = [
            {
                "type": "message", "id": "s1", "timestamp": "2025-01-15T10:00:00Z",
                "message": {
                    "role": "assistant", "content": "Done",
                    "usage": {"input": 300, "output": 100, "cacheRead": 50,
                              "cacheWrite": 10, "cost": {"total": 0.025}},
                },
            },
        ]
        content = _build_session(messages=messages)
        path = tmp_path / "metrics.jsonl"
        _write_session(path, content)
        traj = _parser.parse_file(path)[0]
        agent_steps = [s for s in traj.steps if s.source == StepSource.AGENT]
        assert len(agent_steps) == 1
        m = agent_steps[0].metrics
        assert m is not None
        assert m.prompt_tokens == 350  # 300 + 50
        assert m.completion_tokens == 100
        assert m.cached_tokens == 50


class TestToolCallsAndObservations:
    """Tests for tool call linking with toolResult messages."""

    def test_tool_call_linked_to_result(self, tmp_path: Path):
        """A toolResult message is consumed and attached as an observation."""
        messages = [
            {
                "type": "message", "id": "s1", "timestamp": "2025-01-15T10:00:00Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "toolCall", "id": "tc-1",
                                 "name": "Read", "arguments": {"path": "x.py"}}],
                },
            },
            {
                "type": "message", "id": "s2", "timestamp": "2025-01-15T10:00:01Z",
                "message": {
                    "role": "toolResult", "toolCallId": "tc-1",
                    "content": "file contents here", "isError": False,
                },
            },
        ]
        content = _build_session(messages=messages)
        path = tmp_path / "tc.jsonl"
        _write_session(path, content)
        traj = _parser.parse_file(path)[0]

        agent_steps = [s for s in traj.steps if s.source == StepSource.AGENT]
        assert len(agent_steps) == 1
        step = agent_steps[0]
        assert len(step.tool_calls) == 1
        assert step.tool_calls[0].function_name == "Read"
        assert step.observation is not None
        assert step.observation.results[0].content == "file contents here"
        assert not is_error_content(step.observation.results[0].content)

    def test_error_tool_result(self, tmp_path: Path):
        """isError=True marks the observation result as an error."""
        messages = [
            {
                "type": "message", "id": "s1", "timestamp": "2025-01-15T10:00:00Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "toolCall", "id": "tc-err",
                                 "name": "Bash", "arguments": {}}],
                },
            },
            {
                "type": "message", "id": "s2", "timestamp": "2025-01-15T10:00:01Z",
                "message": {
                    "role": "toolResult", "toolCallId": "tc-err",
                    "content": "Permission denied", "isError": True,
                },
            },
        ]
        content = _build_session(messages=messages)
        path = tmp_path / "tc-err.jsonl"
        _write_session(path, content)
        traj = _parser.parse_file(path)[0]
        agent_steps = [s for s in traj.steps if s.source == StepSource.AGENT]
        obs = agent_steps[0].observation
        assert obs is not None
        assert is_error_content(obs.results[0].content)

    def test_tool_result_not_a_step(self, tmp_path: Path):
        """toolResult-role messages are consumed but never become steps."""
        messages = [
            {
                "type": "message", "id": "s1", "timestamp": "2025-01-15T10:00:00Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "toolCall", "id": "tc-1",
                                 "name": "Search", "arguments": {}}],
                },
            },
            {
                "type": "message", "id": "s2", "timestamp": "2025-01-15T10:00:01Z",
                "message": {"role": "toolResult", "toolCallId": "tc-1", "content": "results"},
            },
        ]
        content = _build_session(messages=messages)
        path = tmp_path / "no-result-step.jsonl"
        _write_session(path, content)
        traj = _parser.parse_file(path)[0]
        # Only assistant step; toolResult should not appear as a step
        assert all(s.source in (StepSource.USER, StepSource.AGENT) for s in traj.steps)

    def test_multiple_tool_calls_final_metrics(self, tmp_path: Path):
        """final_metrics.tool_call_count reflects total tool calls across all steps."""
        messages = [
            {
                "type": "message", "id": "s1", "timestamp": "2025-01-15T10:00:00Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "toolCall", "id": "tc-1", "name": "Read", "arguments": {}},
                        {"type": "toolCall", "id": "tc-2", "name": "Write", "arguments": {}},
                        {"type": "toolCall", "id": "tc-3", "name": "Bash", "arguments": {}},
                    ],
                },
            },
        ]
        content = _build_session(messages=messages)
        path = tmp_path / "multi-tc.jsonl"
        _write_session(path, content)
        traj = _parser.parse_file(path)[0]
        assert traj.final_metrics is not None
        assert traj.final_metrics.tool_call_count == 3

    def test_collect_tool_results(self):
        """_collect_tool_results builds a mapping from toolCallId to result data."""
        message_entries = [
            {"type": "message", "message": {
                "role": "toolResult", "toolCallId": "tc-1",
                "content": "output text", "isError": False,
            }},
            {"type": "message", "message": {
                "role": "toolResult", "toolCallId": "tc-2",
                "content": "error text", "isError": True,
            }},
            # non-toolResult should be ignored
            {"type": "message", "message": {"role": "user", "content": "hello"}},
        ]
        result_map = _collect_tool_results(message_entries)
        assert "tc-1" in result_map
        assert result_map["tc-1"]["output"] == "output text"
        assert result_map["tc-1"]["is_error"] is False
        assert "tc-2" in result_map
        assert result_map["tc-2"]["is_error"] is True
        assert "user" not in result_map


class TestDiscover:
    """Tests for OpenClawParser.discover_session_files."""

    def test_finds_session_files(self, tmp_path: Path):
        """JSONL files under agents/*/sessions/ are discovered."""
        sessions_dir = tmp_path / "agents" / "main" / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "sess-1.jsonl").write_text("{}")
        (sessions_dir / "sess-2.jsonl").write_text("{}")

        files = _parser.discover_session_files(tmp_path)
        names = {f.name for f in files}
        assert "sess-1.jsonl" in names
        assert "sess-2.jsonl" in names

    def test_excludes_clean_files(self, tmp_path: Path):
        """Files ending in -clean.jsonl are excluded."""
        sessions_dir = tmp_path / "agents" / "main" / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "sess-1.jsonl").write_text("{}")
        (sessions_dir / "sess-1-clean.jsonl").write_text("{}")

        files = _parser.discover_session_files(tmp_path)
        names = {f.name for f in files}
        assert "sess-1.jsonl" in names
        assert "sess-1-clean.jsonl" not in names

    def test_only_sessions_subdir(self, tmp_path: Path):
        """JSONL files outside sessions/ are not included."""
        (tmp_path / "agents" / "main").mkdir(parents=True)
        (tmp_path / "agents" / "main" / "loose.jsonl").write_text("{}")
        sessions_dir = tmp_path / "agents" / "main" / "sessions"
        sessions_dir.mkdir()
        (sessions_dir / "real.jsonl").write_text("{}")

        files = _parser.discover_session_files(tmp_path)
        names = {f.name for f in files}
        assert "real.jsonl" in names
        assert "loose.jsonl" not in names

    def test_missing_agents_dir(self, tmp_path: Path):
        """Returns empty list when agents/ does not exist."""
        assert _parser.discover_session_files(tmp_path) == []


class TestMalformedInput:
    """Tests for resilience against malformed JSONL input."""

    def test_invalid_json_lines_skipped(self, tmp_path: Path):
        """Invalid JSON lines are skipped; valid lines still produce steps."""
        lines = [
            _make_event(type="session", id="s1", cwd="/tmp"),
            "{not valid json",
            _make_event(type="message", id="m1", timestamp="2025-01-15T10:00:00Z",
                        message={"role": "user", "content": "valid"}),
        ]
        path = tmp_path / "mixed.jsonl"
        _write_session(path, "\n".join(lines))
        results = _parser.parse_file(path)
        assert len(results) == 1
        assert len(results[0].steps) == 1

    def test_unknown_event_types_ignored(self, tmp_path: Path):
        """Unknown event types (e.g. 'custom') do not cause failures."""
        lines = [
            _make_event(type="session", id="s1", cwd="/tmp"),
            _make_event(type="unknown_event", data="whatever"),
            _make_event(type="message", id="m1", timestamp="2025-01-15T10:00:00Z",
                        message={"role": "user", "content": "hi"}),
        ]
        path = tmp_path / "unknown.jsonl"
        _write_session(path, "\n".join(lines))
        results = _parser.parse_file(path)
        assert len(results) == 1

    def test_unknown_role_skipped(self, tmp_path: Path):
        """Messages with unrecognized roles are skipped."""
        lines = [
            _make_event(type="session", id="s1", cwd="/tmp"),
            _make_event(type="message", id="m1", timestamp="2025-01-15T10:00:00Z",
                        message={"role": "system", "content": "sys prompt"}),
            _make_event(type="message", id="m2", timestamp="2025-01-15T10:00:01Z",
                        message={"role": "user", "content": "real message"}),
        ]
        path = tmp_path / "unknown-role.jsonl"
        _write_session(path, "\n".join(lines))
        results = _parser.parse_file(path)
        assert len(results) == 1
        assert len(results[0].steps) == 1
        assert results[0].steps[0].message == "real message"
