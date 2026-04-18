"""Tests for Hermes Agent JSONL parser."""

import json
from pathlib import Path

import pytest

from vibelens.ingest.parsers.hermes import HERMES_DATA_DIR, HermesParser
from vibelens.models.enums import AgentType, StepSource
from vibelens.models.trajectories import Trajectory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASIC_SESSION = [
    {
        "role": "session_meta",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "terminal",
                    "description": "Run shell commands",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        "model": "anthropic/claude-sonnet-4",
        "platform": "slack",
        "timestamp": "2026-04-18T19:26:00.214787",
    },
    {
        "role": "user",
        "content": "What do you think about this tool?",
        "timestamp": "2026-04-18T19:26:05.000000",
    },
    {
        "role": "assistant",
        "content": "Let me check it out.",
        "reasoning": "I should look at the repo first.",
        "finish_reason": "tool_calls",
        "tool_calls": [
            {
                "id": "call_001",
                "call_id": "call_001",
                "type": "function",
                "function": {
                    "name": "terminal",
                    "arguments": '{"command": "curl -s https://api.github.com/repos/example"}',
                },
            }
        ],
        "timestamp": "2026-04-18T19:26:10.000000",
    },
    {
        "role": "tool",
        "content": '{"output": "some data", "exit_code": 0}',
        "tool_call_id": "call_001",
        "timestamp": "2026-04-18T19:26:12.000000",
    },
    {
        "role": "assistant",
        "content": "Here's what I found: it looks good.",
        "reasoning": None,
        "finish_reason": "stop",
        "timestamp": "2026-04-18T19:26:15.000000",
    },
]


ERROR_SESSION = [
    {
        "role": "session_meta",
        "tools": [],
        "model": "anthropic/claude-opus-4",
        "platform": "cli",
        "timestamp": "2026-04-18T20:00:00.000000",
    },
    {
        "role": "user",
        "content": "Delete everything",
        "timestamp": "2026-04-18T20:00:05.000000",
    },
    {
        "role": "assistant",
        "content": "",
        "finish_reason": "tool_calls",
        "tool_calls": [
            {
                "id": "call_err",
                "call_id": "call_err",
                "type": "function",
                "function": {
                    "name": "terminal",
                    "arguments": '{"command": "rm -rf /"}',
                },
            }
        ],
        "timestamp": "2026-04-18T20:00:10.000000",
    },
    {
        "role": "tool",
        "content": '{"success": false, "error": "Permission denied"}',
        "tool_call_id": "call_err",
        "timestamp": "2026-04-18T20:00:11.000000",
    },
    {
        "role": "assistant",
        "content": "I can't do that.",
        "finish_reason": "stop",
        "timestamp": "2026-04-18T20:00:12.000000",
    },
]


def _make_jsonl(events: list[dict]) -> str:
    """Convert a list of event dicts to JSONL string."""
    return "\n".join(json.dumps(e) for e in events)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHermesParser:
    parser = HermesParser()

    def test_agent_type(self):
        assert self.parser.AGENT_TYPE == AgentType.HERMES

    def test_local_data_dir(self):
        assert self.parser.LOCAL_DATA_DIR == HERMES_DATA_DIR
        assert self.parser.LOCAL_DATA_DIR.name == "sessions"

    def test_parse_basic_session(self):
        content = _make_jsonl(BASIC_SESSION)
        trajectories = self.parser.parse(
            content, source_path="/home/user/.hermes/sessions/20260418_192600_abc123.jsonl"
        )

        assert len(trajectories) == 1
        t = trajectories[0]

        # Session ID from filename
        assert t.session_id == "hermes-20260418_192600_abc123"

        # Agent metadata
        assert t.agent.name == AgentType.HERMES.value
        assert t.agent.model_name == "anthropic/claude-sonnet-4"

        # Steps: user, assistant(w/ tool_calls), assistant(final) = 3
        # (tool results are attached as observations, not separate steps)
        assert len(t.steps) == 3

        # Step 1: user
        assert t.steps[0].source == StepSource.USER
        assert "What do you think" in str(t.steps[0].message)

        # Step 2: assistant with tool call + observation
        assert t.steps[1].source == StepSource.AGENT
        assert t.steps[1].reasoning_content == "I should look at the repo first."
        assert len(t.steps[1].tool_calls) == 1
        assert t.steps[1].tool_calls[0].tool_name == "terminal"
        assert t.steps[1].observation is not None
        assert len(t.steps[1].observation.results) == 1
        assert t.steps[1].observation.results[0].source_call_id == "call_001"

        # Step 3: assistant final response
        assert t.steps[2].source == StepSource.AGENT
        assert "looks good" in str(t.steps[2].message)
        assert len(t.steps[2].tool_calls) == 0

    def test_parse_error_result(self):
        content = _make_jsonl(ERROR_SESSION)
        trajectories = self.parser.parse(content)

        assert len(trajectories) == 1
        t = trajectories[0]

        # The tool result with success=false, error key should be flagged
        step_with_tool = t.steps[1]
        assert len(step_with_tool.tool_calls) == 1
        obs_result = step_with_tool.observation.results[0]
        assert obs_result.content.startswith("[ERROR] ")

    def test_parse_empty_content(self):
        content = ""
        trajectories = self.parser.parse(content)
        assert trajectories == []

    def test_parse_invalid_json_lines(self):
        lines = [
            json.dumps(BASIC_SESSION[0]),
            "this is not json",
            json.dumps(BASIC_SESSION[1]),
        ]
        content = "\n".join(lines)
        trajectories = self.parser.parse(content)
        # Should still parse the valid lines, skip the bad one
        assert len(trajectories) == 1

    def test_session_id_from_path(self):
        path = "/home/user/.hermes/sessions/20260418_192555_4077bccc.jsonl"
        sid = self.parser._extract_session_id(path)
        assert sid == "hermes-20260418_192555_4077bccc"

    def test_session_id_no_path(self):
        sid = self.parser._extract_session_id(None)
        assert sid.startswith("hermes-")

    def test_discover_session_files_empty(self, tmp_path):
        files = self.parser.discover_session_files(tmp_path)
        assert files == []

    def test_discover_session_files_with_data(self, tmp_path):
        # Create fake session files
        (tmp_path / "20260418_192555_abc.jsonl").write_text("{}")
        (tmp_path / "20260418_193000_def.jsonl").write_text("{}")
        (tmp_path / "session_20260418_192555_abc.json").write_text("{}")  # full dump, skip
        (tmp_path / "other.txt").write_text("not a session")

        files = self.parser.discover_session_files(tmp_path)
        assert len(files) == 2
        assert all(f.suffix == ".jsonl" for f in files)
        # Sorted by name (chronological)
        assert files[0].name == "20260418_192555_abc.jsonl"

    def test_first_message_extraction(self):
        content = _make_jsonl(BASIC_SESSION)
        trajectories = self.parser.parse(content)
        assert trajectories[0].first_message is not None
        assert "What do you think" in trajectories[0].first_message

    def test_final_metrics(self):
        content = _make_jsonl(BASIC_SESSION)
        trajectories = self.parser.parse(content)
        t = trajectories[0]
        assert t.final_metrics is not None
        assert t.final_metrics.total_steps == 3
        assert t.final_metrics.tool_call_count == 1

    def test_multiple_tool_calls(self):
        """Test an assistant step with multiple tool calls."""
        events = [
            {"role": "session_meta", "tools": [], "model": "test", "timestamp": "2026-04-18T20:00:00Z"},
            {"role": "user", "content": "Do two things", "timestamp": "2026-04-18T20:00:05Z"},
            {
                "role": "assistant",
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call_a",
                        "call_id": "call_a",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path": "/tmp/a.txt"}'},
                    },
                    {
                        "id": "call_b",
                        "call_id": "call_b",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path": "/tmp/b.txt"}'},
                    },
                ],
                "timestamp": "2026-04-18T20:00:10Z",
            },
            {
                "role": "tool",
                "content": '{"content": "file a", "total_lines": 10, "exit_code": 0}',
                "tool_call_id": "call_a",
                "timestamp": "2026-04-18T20:00:11Z",
            },
            {
                "role": "tool",
                "content": '{"content": "file b", "total_lines": 5, "exit_code": 0}',
                "tool_call_id": "call_b",
                "timestamp": "2026-04-18T20:00:11Z",
            },
            {
                "role": "assistant",
                "content": "Here are both files.",
                "finish_reason": "stop",
                "timestamp": "2026-04-18T20:00:15Z",
            },
        ]
        content = "\n".join(json.dumps(e) for e in events)
        trajectories = self.parser.parse(content)
        t = trajectories[0]

        # 3 steps: user, assistant(w/ 2 tools), assistant(final)
        assert len(t.steps) == 3
        assert len(t.steps[1].tool_calls) == 2
        assert len(t.steps[1].observation.results) == 2
        assert t.final_metrics.tool_call_count == 2
