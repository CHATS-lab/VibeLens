"""Unit tests for vibelens.ingest.codex parser."""

import json
from pathlib import Path

from vibelens.ingest.parsers.codex import CodexParser, _parse_structured_output
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Trajectory

_parser = CodexParser()


def _write_rollout(path: Path, entries: list[dict]) -> None:
    """Write rollout entries as JSONL to a file."""
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _meta_entry(
    session_id: str = "sess-1",
    cwd: str = "/home/user/project",
    timestamp: str = "2025-01-15T10:00:00Z",
    cli_version: str | None = None,
    source: str | None = None,
    originator: str | None = None,
) -> dict:
    """Build a session_meta rollout entry."""
    payload: dict = {"id": session_id, "cwd": cwd, "timestamp": timestamp}
    if cli_version:
        payload["cli_version"] = cli_version
    if source:
        payload["source"] = source
    if originator:
        payload["originator"] = originator
    return {"type": "session_meta", "timestamp": timestamp, "payload": payload}


def _turn_context_entry(
    model: str = "gpt-5.4",
    timestamp: str = "2025-01-15T10:00:01Z",
    reasoning_effort: str | None = None,
    sandbox: str | None = None,
    approval_policy: str | None = None,
    cwd: str | None = None,
) -> dict:
    """Build a turn_context rollout entry."""
    payload: dict = {"model": model}
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    if sandbox:
        payload["sandbox"] = sandbox
    if approval_policy:
        payload["approval_policy"] = approval_policy
    if cwd:
        payload["cwd"] = cwd
    return {"type": "turn_context", "timestamp": timestamp, "payload": payload}


def _user_msg_entry(
    text: str = "Hello",
    timestamp: str = "2025-01-15T10:00:01Z",
) -> dict:
    """Build a user response_item entry."""
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        },
    }


def _assistant_msg_entry(
    text: str = "Hi there",
    timestamp: str = "2025-01-15T10:00:02Z",
) -> dict:
    """Build an assistant response_item entry."""
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        },
    }


def _function_call_entry(
    call_id: str = "fc-1",
    name: str = "shell",
    arguments: str = '{"command": "ls"}',
    timestamp: str = "2025-01-15T10:00:03Z",
) -> dict:
    """Build a function_call response_item entry."""
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": arguments,
        },
    }


def _function_call_output_entry(
    call_id: str = "fc-1",
    output: str = "file1.txt\nfile2.txt",
    timestamp: str = "2025-01-15T10:00:04Z",
) -> dict:
    """Build a function_call_output response_item entry."""
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {"type": "function_call_output", "call_id": call_id, "output": output},
    }


def _reasoning_entry(
    text: str = "Let me think about this...",
    timestamp: str = "2025-01-15T10:00:05Z",
) -> dict:
    """Build a reasoning response_item entry."""
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {"type": "reasoning", "summary": [{"text": text}]},
    }


def _token_count_entry(
    input_tokens: int = 500,
    output_tokens: int = 200,
    cached_input_tokens: int = 100,
    reasoning_output_tokens: int = 0,
    timestamp: str = "2025-01-15T10:00:06Z",
    total_token_usage: dict | None = None,
) -> dict:
    """Build a token_count event_msg entry."""
    info: dict = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_input_tokens,
    }
    if reasoning_output_tokens:
        info["reasoning_output_tokens"] = reasoning_output_tokens
    if total_token_usage:
        info["total_token_usage"] = total_token_usage
    return {
        "type": "event_msg",
        "timestamp": timestamp,
        "payload": {"type": "token_count", "info": info},
    }


class TestParseFile:
    """Tests for CodexParser.parse_file basic rollout parsing."""

    def test_basic_rollout(self, tmp_path: Path):
        """Parses a minimal rollout with user + assistant messages."""
        rollout = tmp_path / "rollout-2025-sess-1.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                _user_msg_entry("Hello"),
                _assistant_msg_entry("Hi there"),
            ],
        )
        results = _parser.parse(rollout)
        assert len(results) == 1
        traj = results[0]
        assert isinstance(traj, Trajectory)
        steps = traj.steps
        assert traj.session_id == "sess-1"
        assert len(steps) == 2
        assert steps[0].source == StepSource.USER
        assert steps[0].message == "Hello"
        assert steps[1].source == StepSource.AGENT
        assert steps[1].message == "Hi there"

    def test_metadata_extraction(self, tmp_path: Path):
        """Session ID, project path, first message, and duration are all extracted correctly."""
        rollout_meta = tmp_path / "rollout-meta.jsonl"
        _write_rollout(
            rollout_meta,
            [
                _meta_entry(session_id="custom-id", cwd="/Users/dev/my-awesome-project"),
                _assistant_msg_entry("I start first", timestamp="2025-01-15T10:00:00Z"),
                _user_msg_entry("Fix the bug in main.py", timestamp="2025-01-15T10:02:30Z"),
                _assistant_msg_entry("Done", timestamp="2025-01-15T10:05:00Z"),
            ],
        )
        results = _parser.parse(rollout_meta)
        traj = results[0]

        assert traj.session_id == "custom-id"
        assert traj.project_path == "/Users/dev/my-awesome-project"
        assert traj.first_message == "Fix the bug in main.py"
        assert traj.final_metrics is not None
        assert traj.final_metrics.duration == 300

        # Session ID falls back to filename when meta lacks 'id'
        rollout_fallback = tmp_path / "rollout-fallback.jsonl"
        _write_rollout(
            rollout_fallback,
            [
                {
                    "type": "session_meta",
                    "timestamp": "2025-01-15T10:00:00Z",
                    "payload": {"cwd": "/tmp"},
                },
                _user_msg_entry(),
            ],
        )
        fallback_traj = _parser.parse(rollout_fallback)[0]
        assert fallback_traj.session_id == "rollout-fallback"

    def test_edge_cases(self, tmp_path: Path):
        """Empty file, missing file, meta-only, and developer role are handled gracefully."""
        # Empty file returns empty
        empty_rollout = tmp_path / "rollout-empty.jsonl"
        empty_rollout.write_text("")
        assert _parser.parse(empty_rollout) == []

        # Missing file returns empty
        assert _parser.parse(tmp_path / "does-not-exist.jsonl") == []

        # Meta-only (no messages) returns empty
        meta_only = tmp_path / "rollout-meta-only.jsonl"
        _write_rollout(meta_only, [_meta_entry()])
        assert _parser.parse(meta_only) == []

        # Developer role messages are filtered out
        dev_rollout = tmp_path / "rollout-dev.jsonl"
        _write_rollout(
            dev_rollout,
            [
                _meta_entry(),
                {
                    "type": "response_item",
                    "timestamp": "2025-01-15T10:00:01Z",
                    "payload": {
                        "type": "message",
                        "role": "developer",
                        "content": [{"type": "input_text", "text": "System prompt"}],
                    },
                },
                _user_msg_entry("Hello"),
            ],
        )
        dev_steps = _parser.parse(dev_rollout)[0].steps
        assert len(dev_steps) == 1
        assert dev_steps[0].source == StepSource.USER


class TestFunctionCallPairing:
    """Tests for function_call + function_call_output linked by call_id."""

    def test_function_call_pairing(self, tmp_path: Path):
        """Single call+output, multiple calls in same turn, and trailing flush all work."""
        t = "2025-01-15T10:00:"
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                # Turn 1: single call + output
                _assistant_msg_entry("Let me check"),
                _function_call_entry(call_id="fc-1", name="shell"),
                _function_call_output_entry(call_id="fc-1", output="file1.txt"),
                # Turn 2: multiple calls in same turn
                _assistant_msg_entry("Let me run", timestamp=f"{t}05Z"),
                _function_call_entry(call_id="fc-2", name="shell", timestamp=f"{t}06Z"),
                _function_call_output_entry(call_id="fc-2", output="output-2", timestamp=f"{t}07Z"),
                _function_call_entry(call_id="fc-3", name="read_file", timestamp=f"{t}08Z"),
                _function_call_output_entry(call_id="fc-3", output="output-3", timestamp=f"{t}09Z"),
                # Turn 3: trailing tool calls flushed at end
                _assistant_msg_entry("checking", timestamp=f"{t}10Z"),
                _function_call_entry(call_id="fc-last", name="shell", timestamp=f"{t}11Z"),
                _function_call_output_entry(call_id="fc-last", output="done", timestamp=f"{t}12Z"),
            ],
        )
        results = _parser.parse(rollout)
        steps = results[0].steps
        agent_steps = [s for s in steps if s.source == StepSource.AGENT]

        # Turn 1: single paired call
        turn1 = agent_steps[0]
        assert len(turn1.tool_calls) == 1
        assert turn1.tool_calls[0].function_name == "shell"
        assert turn1.tool_calls[0].tool_call_id == "fc-1"
        assert turn1.observation is not None
        assert turn1.observation.results[0].content == "file1.txt"

        # Turn 2: two calls in same turn
        turn2 = agent_steps[1]
        assert len(turn2.tool_calls) == 2
        assert turn2.tool_calls[0].function_name == "shell"
        assert turn2.observation.results[0].content == "output-2"
        assert turn2.tool_calls[1].function_name == "read_file"
        assert turn2.observation.results[1].content == "output-3"

        # Turn 3: trailing flush
        turn3 = agent_steps[2]
        assert len(turn3.tool_calls) == 1
        assert turn3.tool_calls[0].tool_call_id == "fc-last"

    def test_missing_output(self, tmp_path: Path):
        """function_call without matching output still creates the tool call."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry(),
                _function_call_entry(call_id="fc-orphan", name="shell"),
                _user_msg_entry("next"),
            ],
        )
        results = _parser.parse(rollout)
        steps = results[0].steps
        agent_step = steps[0]
        assert len(agent_step.tool_calls) == 1


class TestPerTurnModelTracking:
    """Tests for turn_context model changes applied per-turn."""

    def test_model_tracking(self, tmp_path: Path):
        """Model from turn_context applies to agent steps, not user steps, and tracks changes."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(model="gpt-5.4"),
                _user_msg_entry(timestamp="2025-01-15T10:00:01Z"),
                _assistant_msg_entry("first", timestamp="2025-01-15T10:00:02Z"),
                _turn_context_entry(model="gpt-4-mini"),
                _user_msg_entry("second q", timestamp="2025-01-15T10:00:03Z"),
                _assistant_msg_entry("second", timestamp="2025-01-15T10:00:04Z"),
            ],
        )
        results = _parser.parse(rollout)
        steps = results[0].steps
        user_steps = [s for s in steps if s.source == StepSource.USER]
        agent_steps = [s for s in steps if s.source == StepSource.AGENT]

        # User steps never get model assignment
        for user_step in user_steps:
            assert user_step.model_name is None

        # Agent steps track model per turn_context
        assert agent_steps[0].model_name == "gpt-5.4"
        assert agent_steps[1].model_name == "gpt-4-mini"
        step_models = sorted({s.model_name for s in agent_steps if s.model_name})
        assert step_models == ["gpt-4-mini", "gpt-5.4"]


class TestTokenCountAttachment:
    """Tests for event_msg token_count parsed and attached."""

    def test_token_count(self, tmp_path: Path):
        """Token counts attach to agent steps with aligned prompt_tokens."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                _user_msg_entry(),
                _assistant_msg_entry(),
                _token_count_entry(
                    input_tokens=500,
                    output_tokens=200,
                    cached_input_tokens=100,
                ),
            ],
        )
        results = _parser.parse(rollout)
        steps = results[0].steps
        agent_step = [s for s in steps if s.source == StepSource.AGENT][0]
        user_step = [s for s in steps if s.source == StepSource.USER][0]

        # Agent step has token metrics attached with aligned prompt_tokens
        assert agent_step.metrics is not None
        # prompt_tokens = input_tokens + cached_input_tokens = 500 + 100
        assert agent_step.metrics.prompt_tokens == 600
        assert agent_step.metrics.completion_tokens == 200
        assert agent_step.metrics.cache_read_tokens == 100

        # User step has no metrics
        assert user_step.metrics is None

    def test_reasoning_output_tokens_in_extra(self, tmp_path: Path):
        """reasoning_output_tokens are captured in Metrics.extra."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                _user_msg_entry(),
                _assistant_msg_entry(),
                _token_count_entry(
                    input_tokens=500,
                    output_tokens=200,
                    cached_input_tokens=100,
                    reasoning_output_tokens=50,
                ),
            ],
        )
        results = _parser.parse(rollout)
        agent_step = [s for s in results[0].steps if s.source == StepSource.AGENT][0]
        assert agent_step.metrics is not None
        assert agent_step.metrics.extra is not None
        assert agent_step.metrics.extra["reasoning_output_tokens"] == 50


class TestMalformedInput:
    """Tests for graceful handling of malformed JSONL and missing fields."""

    def test_malformed_input_handling(self, tmp_path: Path):
        """Invalid JSON, blanks, missing payload, and unknown types are handled."""
        rollout = tmp_path / "rollout.jsonl"
        with open(rollout, "w", encoding="utf-8") as f:
            # Invalid JSON line
            f.write("NOT VALID JSON\n")
            f.write(json.dumps(_meta_entry()) + "\n")
            # Blank / whitespace lines
            f.write("\n")
            f.write("   \n")
            # Broken JSON
            f.write("{broken\n")
            # Entry without payload field
            f.write(
                json.dumps(
                    {
                        "type": "response_item",
                        "timestamp": "2025-01-15T10:00:01Z",
                    }
                )
                + "\n"
            )
            # Entry with unknown type
            f.write(
                json.dumps(
                    {
                        "type": "unknown_type",
                        "timestamp": "2025-01-15T10:00:02Z",
                        "payload": {"data": "irrelevant"},
                    }
                )
                + "\n"
            )
            # Valid user message
            f.write(json.dumps(_user_msg_entry("valid")) + "\n")

        results = _parser.parse(rollout)
        assert len(results) == 1
        steps = results[0].steps
        assert len(steps) == 1
        assert steps[0].message == "valid"


class TestReasoningExtraction:
    """Tests for reasoning entries extracted and deduped."""

    def test_reasoning_extraction(self, tmp_path: Path):
        """Reasoning attaches to agent steps, flushes at end, and handles multi-item summaries."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                # Turn 1: reasoning attaches to preceding agent msg
                _assistant_msg_entry("My answer"),
                _reasoning_entry("Let me think about this..."),
                _user_msg_entry("next", timestamp="2025-01-15T10:00:06Z"),
                # Turn 2: multi-item summary, trailing flush
                _assistant_msg_entry("response", timestamp="2025-01-15T10:00:07Z"),
                {
                    "type": "response_item",
                    "timestamp": "2025-01-15T10:00:08Z",
                    "payload": {
                        "type": "reasoning",
                        "summary": [{"text": "First thought"}, {"text": "Second thought"}],
                    },
                },
            ],
        )
        results = _parser.parse(rollout)
        steps = results[0].steps
        agent_steps = [s for s in steps if s.source == StepSource.AGENT]

        # Turn 1: single reasoning attached
        assert agent_steps[0].reasoning_content is not None
        assert "Let me think about this..." in agent_steps[0].reasoning_content

        # Turn 2: multi-item summary, flushed at end of file
        assert "First thought" in agent_steps[1].reasoning_content
        assert "Second thought" in agent_steps[1].reasoning_content

    def test_reasoning_deduplication(self, tmp_path: Path):
        """Identical reasoning entries are deduplicated by content hash."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry("answer"),
                _reasoning_entry("Same thought"),
                _reasoning_entry("Same thought"),
                _reasoning_entry("Different thought"),
                _user_msg_entry("ok"),
            ],
        )
        results = _parser.parse(rollout)
        steps = results[0].steps
        agent_step = steps[0]
        assert agent_step.reasoning_content is not None
        # "Same thought" appears once, "Different thought" once
        lines = agent_step.reasoning_content.split("\n")
        assert len(lines) == 2
        assert "Same thought" in lines
        assert "Different thought" in lines


class TestStructuredOutput:
    """Tests for structured output prefix stripping and error detection."""

    def test_structured_output_parsing(self):
        """Exit code stripping, error detection, multiline output, and passthrough all work."""
        # Exit code 0: prefix stripped, no error, metadata extracted
        cleaned, has_error, metadata = _parse_structured_output(
            "Exit code: 0\nWall time: 1.23s\nOutput:\nactual output here"
        )
        assert cleaned == "actual output here"
        assert has_error is False
        assert metadata is not None
        assert metadata["exit_code"] == 0
        assert metadata["wall_time_sec"] == 1.23

        # Non-zero exit code: error detected
        cleaned, has_error, metadata = _parse_structured_output(
            "Exit code: 1\nWall time: 0.5s\nOutput:\nerror message"
        )
        assert cleaned == "error message"
        assert has_error is True
        assert metadata["exit_code"] == 1
        assert metadata["wall_time_sec"] == 0.5

        # Multiline output after prefix
        cleaned, _, metadata = _parse_structured_output(
            "Exit code: 0\nWall time: 2.00s\nOutput:\nline1\nline2\nline3"
        )
        assert cleaned == "line1\nline2\nline3"
        assert metadata["wall_time_sec"] == 2.0

        # No prefix: returned as-is with None metadata
        cleaned, has_error, metadata = _parse_structured_output("plain output without prefix")
        assert cleaned == "plain output without prefix"
        assert has_error is False
        assert metadata is None

    def test_error_detection_via_rollout(self, tmp_path: Path):
        """Non-zero exit code marks error, zero exit code keeps clean content."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                # Error tool call
                _assistant_msg_entry("running"),
                _function_call_entry(call_id="fc-err", name="shell"),
                _function_call_output_entry(
                    call_id="fc-err",
                    output="Exit code: 127\nWall time: 0.01s\nOutput:\ncommand not found: foo",
                ),
                _user_msg_entry("next", timestamp="2025-01-15T10:00:05Z"),
                # Success tool call
                _assistant_msg_entry("listing", timestamp="2025-01-15T10:00:06Z"),
                _function_call_entry(
                    call_id="fc-ok",
                    name="shell",
                    timestamp="2025-01-15T10:00:07Z",
                ),
                _function_call_output_entry(
                    call_id="fc-ok",
                    output="Exit code: 0\nWall time: 0.50s\nOutput:\nfile1.txt",
                    timestamp="2025-01-15T10:00:08Z",
                ),
                _user_msg_entry("done", timestamp="2025-01-15T10:00:09Z"),
            ],
        )
        results = _parser.parse(rollout)
        steps = results[0].steps
        agent_steps = [s for s in steps if s.source == StepSource.AGENT]

        # Error case: is_error=True, content preserved verbatim
        err_obs = agent_steps[0].observation.results[0]
        assert err_obs.is_error is True
        assert "command not found: foo" in err_obs.content

        # Success case: is_error=False
        ok_obs = agent_steps[1].observation.results[0]
        assert ok_obs.is_error is False
        assert ok_obs.content == "file1.txt"


class TestSessionMetadata:
    """Tests for enriched session metadata extraction."""

    def test_cli_version_and_model_on_agent(self, tmp_path: Path):
        """cli_version and model from metadata appear on the Agent object."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(cli_version="1.2.3"),
                _turn_context_entry(model="gpt-5.4"),
                _user_msg_entry(),
                _assistant_msg_entry(),
            ],
        )
        traj = _parser.parse(rollout)[0]
        assert traj.agent.version == "1.2.3"
        assert traj.agent.model_name == "gpt-5.4"

    def test_source_and_originator_in_extra(self, tmp_path: Path):
        """source and originator from session_meta appear in trajectory extra."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(source="vscode", originator="user-xyz"),
                _turn_context_entry(),
                _user_msg_entry(),
                _assistant_msg_entry(),
            ],
        )
        traj = _parser.parse(rollout)[0]
        assert traj.extra is not None
        assert traj.extra["source"] == "vscode"
        assert traj.extra["originator"] == "user-xyz"

    def test_reasoning_effort_in_extra(self, tmp_path: Path):
        """reasoning_effort from first turn_context appears in trajectory extra."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(reasoning_effort="high"),
                _user_msg_entry(),
                _assistant_msg_entry(),
            ],
        )
        traj = _parser.parse(rollout)[0]
        assert traj.extra is not None
        assert traj.extra["reasoning_effort"] == "high"

    def test_sandbox_and_approval_policy(self, tmp_path: Path):
        """sandbox_policy and approval_policy from turn_context appear in trajectory extra."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(sandbox="read-only", approval_policy="on-failure"),
                _user_msg_entry(),
                _assistant_msg_entry(),
            ],
        )
        traj = _parser.parse(rollout)[0]
        assert traj.extra is not None
        assert traj.extra["sandbox_policy"] == "read-only"
        assert traj.extra["approval_policy"] == "on-failure"

    def test_no_extra_when_no_metadata(self, tmp_path: Path):
        """When no enriched metadata is present, extra is None or diagnostics-only."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                _user_msg_entry(),
                _assistant_msg_entry(),
            ],
        )
        traj = _parser.parse(rollout)[0]
        # No extra metadata, no diagnostics issues
        assert traj.extra is None


class TestCustomToolCall:
    """Tests for custom_tool_call and custom_tool_call_output handling."""

    def test_custom_tool_call_parsed(self, tmp_path: Path):
        """custom_tool_call entries are parsed with arguments from 'input' field."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                _assistant_msg_entry("Using custom tool"),
                {
                    "type": "response_item",
                    "timestamp": "2025-01-15T10:00:03Z",
                    "payload": {
                        "type": "custom_tool_call",
                        "call_id": "ctc-1",
                        "name": "my_custom_tool",
                        "input": {"key": "value"},
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2025-01-15T10:00:04Z",
                    "payload": {
                        "type": "custom_tool_call_output",
                        "call_id": "ctc-1",
                        "output": "custom result",
                    },
                },
                _user_msg_entry("ok", timestamp="2025-01-15T10:00:05Z"),
            ],
        )
        traj = _parser.parse(rollout)[0]
        agent_step = [s for s in traj.steps if s.source == StepSource.AGENT][0]
        assert len(agent_step.tool_calls) == 1
        tc = agent_step.tool_calls[0]
        assert tc.function_name == "my_custom_tool"
        assert tc.tool_call_id == "ctc-1"
        assert tc.arguments == {"key": "value"}
        assert agent_step.observation is not None
        assert agent_step.observation.results[0].content == "custom result"


class TestFinalTokenUsage:
    """Tests for total_token_usage extraction to trajectory extra."""

    def test_total_token_usage_in_extra(self, tmp_path: Path):
        """Last token_count with total_token_usage is captured in trajectory extra."""
        total_usage = {
            "input_tokens": 5000,
            "output_tokens": 2000,
            "cached_input_tokens": 3000,
        }
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                _user_msg_entry(),
                _assistant_msg_entry(),
                _token_count_entry(total_token_usage=total_usage),
            ],
        )
        traj = _parser.parse(rollout)[0]
        assert traj.extra is not None
        assert traj.extra["total_token_usage"] == total_usage

    def test_no_total_token_usage(self, tmp_path: Path):
        """When no total_token_usage is present, it is not in extra."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                _user_msg_entry(),
                _assistant_msg_entry(),
                _token_count_entry(),
            ],
        )
        traj = _parser.parse(rollout)[0]
        # No total_token_usage, no session extra, no diagnostics
        assert traj.extra is None

    def test_token_count_with_null_info_does_not_crash(self, tmp_path: Path):
        """Codex aborts a turn before producing usage stats; ``info`` is null.

        Previously ``.get("info", {})`` returned None because the key is
        present, which crashed ``.get("total_token_usage")``. Guard with
        ``or {}`` so aborted sessions still parse.
        """
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                _user_msg_entry("hello"),
                # token_count with info=null, as produced by Codex when a
                # session is cancelled before the first assistant response.
                {
                    "type": "event_msg",
                    "timestamp": "2025-01-15T10:00:05Z",
                    "payload": {
                        "type": "token_count",
                        "info": None,
                        "rate_limits": None,
                    },
                },
            ],
        )
        trajectories = _parser.parse(rollout)
        assert len(trajectories) == 1
        traj = trajectories[0]
        # No usage → no total_token_usage in extra
        assert (traj.extra or {}).get("total_token_usage") is None


class TestToolResultMetadata:
    """Tests for exit_code and wall_time in ObservationResult.extra."""

    def test_exit_code_and_wall_time_in_obs_extra(self, tmp_path: Path):
        """Structured output metadata (exit_code, wall_time_sec) is in ObservationResult.extra."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                _assistant_msg_entry("running"),
                _function_call_entry(call_id="fc-1", name="shell"),
                _function_call_output_entry(
                    call_id="fc-1",
                    output="Exit code: 0\nWall time: 1.50s\nOutput:\nresult data",
                ),
                _user_msg_entry("next", timestamp="2025-01-15T10:00:05Z"),
            ],
        )
        traj = _parser.parse(rollout)[0]
        agent_step = [s for s in traj.steps if s.source == StepSource.AGENT][0]
        obs_result = agent_step.observation.results[0]
        assert obs_result.content == "result data"
        assert obs_result.extra is not None
        assert obs_result.extra["exit_code"] == 0
        assert obs_result.extra["wall_time_sec"] == 1.50

    def test_no_metadata_for_plain_output(self, tmp_path: Path):
        """Plain output without structured prefix has no extra metadata."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                _assistant_msg_entry("running"),
                _function_call_entry(call_id="fc-1", name="shell"),
                _function_call_output_entry(call_id="fc-1", output="plain output"),
                _user_msg_entry("next", timestamp="2025-01-15T10:00:05Z"),
            ],
        )
        traj = _parser.parse(rollout)[0]
        agent_step = [s for s in traj.steps if s.source == StepSource.AGENT][0]
        obs_result = agent_step.observation.results[0]
        assert obs_result.content == "plain output"
        assert obs_result.extra is None


class TestStepExtra:
    """Tests for step-level extra dict (cwd, reasoning_effort)."""

    def test_step_extra_from_turn_context(self, tmp_path: Path):
        """Agent steps get cwd and reasoning_effort in extra from turn_context."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(
                    model="gpt-5.4", cwd="/home/user/project", reasoning_effort="high"
                ),
                _user_msg_entry(),
                _assistant_msg_entry(),
            ],
        )
        traj = _parser.parse(rollout)[0]
        agent_step = [s for s in traj.steps if s.source == StepSource.AGENT][0]
        assert agent_step.extra is not None
        assert agent_step.extra["cwd"] == "/home/user/project"
        assert agent_step.extra["reasoning_effort"] == "high"

    def test_user_steps_no_extra(self, tmp_path: Path):
        """User steps do not get step extra."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(cwd="/home/user/project", reasoning_effort="high"),
                _user_msg_entry(),
                _assistant_msg_entry(),
            ],
        )
        traj = _parser.parse(rollout)[0]
        user_step = [s for s in traj.steps if s.source == StepSource.USER][0]
        assert user_step.extra is None


class TestSubAgentLinkage:
    """Tests for Codex sub-agent bidirectional linkage."""

    def test_child_parent_ref_from_forked_from_id(self, tmp_path: Path):
        """A child rollout's session_meta with forked_from_id sets parent_trajectory_ref."""
        rollout = tmp_path / "rollout-child.jsonl"
        child_meta = _meta_entry(session_id="child-id")
        # forked_from_id is on the FIRST session_meta payload
        child_meta["payload"]["forked_from_id"] = "parent-id"
        _write_rollout(
            rollout,
            [
                child_meta,
                _turn_context_entry(),
                _user_msg_entry("Worker task"),
                _assistant_msg_entry("Done"),
            ],
        )
        traj = _parser.parse(rollout)[0]
        assert traj.session_id == "child-id"
        assert traj.parent_trajectory_ref is not None
        assert traj.parent_trajectory_ref.session_id == "parent-id"

    def test_parent_subagent_ref_from_spawn_agent_output(self, tmp_path: Path):
        """A spawn_agent function_call output JSON populates subagent_trajectory_ref."""
        rollout = tmp_path / "rollout-parent.jsonl"
        spawn_output = json.dumps({"agent_id": "child-thread-id", "nickname": "Worker"})
        _write_rollout(
            rollout,
            [
                _meta_entry(session_id="parent-id"),
                _turn_context_entry(),
                _user_msg_entry("Spawn a worker"),
                _assistant_msg_entry("OK"),
                _function_call_entry(
                    call_id="call-spawn", name="spawn_agent", arguments='{"agent_type":"worker"}'
                ),
                _function_call_output_entry(call_id="call-spawn", output=spawn_output),
                _user_msg_entry("done", timestamp="2025-01-15T10:00:10Z"),
            ],
        )
        traj = _parser.parse(rollout)[0]
        agent_steps = [s for s in traj.steps if s.source == StepSource.AGENT]
        assert agent_steps, "expected at least one agent step"
        # The spawn observation should be on the agent step that owns the spawn_agent tool call
        spawn_results = [
            r
            for s in agent_steps
            if s.observation
            for r in s.observation.results
            if r.subagent_trajectory_ref
        ]
        assert len(spawn_results) == 1
        assert spawn_results[0].source_call_id == "call-spawn"
        assert spawn_results[0].subagent_trajectory_ref[0].session_id == "child-thread-id"

    def test_non_spawn_agent_tool_has_no_subagent_ref(self, tmp_path: Path):
        """Non-spawn_agent tools get no subagent_trajectory_ref, even with JSON-shaped output."""
        rollout = tmp_path / "rollout.jsonl"
        json_like_output = json.dumps({"agent_id": "not-a-real-spawn"})
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                _user_msg_entry(),
                _assistant_msg_entry(),
                _function_call_entry(call_id="fc-shell", name="shell"),
                _function_call_output_entry(call_id="fc-shell", output=json_like_output),
                _user_msg_entry("next", timestamp="2025-01-15T10:00:10Z"),
            ],
        )
        traj = _parser.parse(rollout)[0]
        for step in traj.steps:
            if not step.observation:
                continue
            for r in step.observation.results:
                assert r.subagent_trajectory_ref is None

    def test_spawn_agent_with_malformed_output_drops_ref(self, tmp_path: Path):
        """Non-JSON spawn_agent output silently drops the subagent_trajectory_ref (no crash)."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                _user_msg_entry(),
                _assistant_msg_entry(),
                _function_call_entry(call_id="fc-spawn", name="spawn_agent"),
                _function_call_output_entry(call_id="fc-spawn", output="not json at all"),
                _user_msg_entry("next", timestamp="2025-01-15T10:00:10Z"),
            ],
        )
        traj = _parser.parse(rollout)[0]
        # Output is preserved as content; the subagent ref is just None
        spawn_obs = [
            r
            for s in traj.steps
            if s.observation
            for r in s.observation.results
            if r.source_call_id == "fc-spawn"
        ]
        assert len(spawn_obs) == 1
        assert spawn_obs[0].content == "not json at all"
        assert spawn_obs[0].subagent_trajectory_ref is None


def _developer_msg_entry(text: str, timestamp: str = "2025-01-15T10:00:03Z") -> dict:
    """Build a developer response_item entry (used for <model_switch> boundary)."""
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {
            "type": "message",
            "role": "developer",
            "content": [{"type": "input_text", "text": text}],
        },
    }


class TestForkPreludeStripping:
    """Sub-agents spawned with fork_context=true inherit the parent's history,
    capped by a <model_switch> developer message. The parser strips that
    prelude so the sub-agent's first_message is its own task, not the parent's."""

    def test_fork_mode_strips_parent_history(self, tmp_path: Path):
        """fork-mode child rollouts drop pre-<model_switch> entries."""
        rollout = tmp_path / "rollout-fork.jsonl"
        child_meta = _meta_entry(session_id="child-id")
        child_meta["payload"]["forked_from_id"] = "parent-id"
        parent_meta = _meta_entry(session_id="parent-id", timestamp="2025-01-15T09:59:59Z")
        _write_rollout(
            rollout,
            [
                child_meta,
                parent_meta,
                _turn_context_entry(model="gpt-5.4"),
                _user_msg_entry("PARENT'S FIRST PROMPT"),
                _assistant_msg_entry("parent reply"),
                _function_call_entry(call_id="fc-spawn", name="spawn_agent"),
                _function_call_output_entry(
                    call_id="fc-spawn", output='{"agent_id":"child-id","nickname":"Worker"}'
                ),
                _developer_msg_entry(
                    "<model_switch>\nThe user was previously using a different model."
                ),
                _user_msg_entry("THE REAL SUB-AGENT TASK", timestamp="2025-01-15T10:00:05Z"),
                _assistant_msg_entry("sub-agent reply", timestamp="2025-01-15T10:00:06Z"),
            ],
        )
        traj = _parser.parse(rollout)[0]
        assert traj.session_id == "child-id"
        assert traj.parent_trajectory_ref is not None
        assert traj.parent_trajectory_ref.session_id == "parent-id"
        # First-message detection should pick the post-fork user prompt, not parent's.
        assert traj.first_message == "THE REAL SUB-AGENT TASK"
        # No parent steps should leak into the sub-agent's step list.
        user_steps = [s for s in traj.steps if s.source == StepSource.USER]
        assert all("PARENT'S FIRST PROMPT" not in (s.message or "") for s in user_steps)

    def test_non_fork_rollout_keeps_all_entries(self, tmp_path: Path):
        """A regular (non-fork) rollout passes through unchanged."""
        rollout = tmp_path / "rollout-regular.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(session_id="regular"),
                _turn_context_entry(),
                _user_msg_entry("hello"),
                _assistant_msg_entry("hi"),
            ],
        )
        traj = _parser.parse(rollout)[0]
        assert traj.session_id == "regular"
        assert traj.first_message == "hello"
        assert traj.parent_trajectory_ref is None

    def test_fork_mode_without_model_switch_falls_back(self, tmp_path: Path):
        """When the boundary marker is missing, keep the rollout intact (degrade gracefully)."""
        rollout = tmp_path / "rollout-no-boundary.jsonl"
        child_meta = _meta_entry(session_id="child")
        child_meta["payload"]["forked_from_id"] = "parent"
        _write_rollout(
            rollout,
            [
                child_meta,
                _meta_entry(session_id="parent", timestamp="2025-01-15T09:59:59Z"),
                _turn_context_entry(),
                _user_msg_entry("only message"),
                _assistant_msg_entry("only reply"),
            ],
        )
        # Doesn't crash; first_message picks the inherited prompt.
        traj = _parser.parse(rollout)[0]
        assert traj.first_message == "only message"
        assert traj.parent_trajectory_ref.session_id == "parent"


class TestSubAgentSqliteLookup:
    """Sub-agent rollouts whose parent → child link lives only in SQLite
    (fresh sub-agents) need _extract_parent_thread_id to surface the link."""

    def test_extract_parent_thread_id_from_subagent_source(self):
        """Sub-agent SQLite source returns the embedded parent_thread_id."""
        from vibelens.ingest.parsers.codex import _extract_parent_thread_id

        source = (
            '{"subagent":{"thread_spawn":{"parent_thread_id":"019d0e38-b3bd",'
            '"depth":1,"agent_role":"worker"}}}'
        )
        assert _extract_parent_thread_id(source) == "019d0e38-b3bd"

    def test_extract_parent_thread_id_returns_none_for_non_subagent(self):
        """Plain string sources (e.g. 'cli', 'vscode') yield None."""
        from vibelens.ingest.parsers.codex import _extract_parent_thread_id

        assert _extract_parent_thread_id("cli") is None
        assert _extract_parent_thread_id("vscode") is None
        assert _extract_parent_thread_id("") is None

    def test_extract_parent_thread_id_handles_malformed_json(self):
        """Bad JSON in source returns None instead of raising."""
        from vibelens.ingest.parsers.codex import _extract_parent_thread_id

        assert _extract_parent_thread_id('{"subagent":{not json') is None


class TestAgentRoleSignal:
    """The session_meta payload carries agent_role + agent_nickname for
    every Codex sub-agent (fresh and fork mode). The parser surfaces
    these in trajectory.extra so the storage layer can filter them
    out of the listing even when no parent_trajectory_ref is set."""

    def test_subagent_extra_includes_agent_role_and_nickname(self, tmp_path: Path):
        """Sub-agent rollouts carry agent_role/nickname in trajectory.extra."""
        rollout = tmp_path / "rollout-fresh-sub.jsonl"
        meta = _meta_entry(session_id="child-id")
        meta["payload"]["agent_role"] = "worker"
        meta["payload"]["agent_nickname"] = "Hegel"
        # Fresh-style subagent source carries the parent_thread_id directly:
        meta["payload"]["source"] = {
            "subagent": {"thread_spawn": {"parent_thread_id": "parent-id", "depth": 1}}
        }
        _write_rollout(
            rollout,
            [meta, _turn_context_entry(), _user_msg_entry("task"), _assistant_msg_entry("done")],
        )
        traj = _parser.parse(rollout)[0]
        assert traj.extra is not None
        assert traj.extra.get("agent_role") == "worker"
        assert traj.extra.get("agent_nickname") == "Hegel"

    def test_session_meta_source_dict_sets_parent_ref(self, tmp_path: Path):
        """Fresh sub-agents (no forked_from_id) recover parent_id from source."""
        rollout = tmp_path / "rollout-fresh.jsonl"
        meta = _meta_entry(session_id="fresh-child")
        meta["payload"]["agent_role"] = "worker"
        meta["payload"]["source"] = {
            "subagent": {"thread_spawn": {"parent_thread_id": "fresh-parent"}}
        }
        _write_rollout(
            rollout,
            [meta, _turn_context_entry(), _user_msg_entry("hi"), _assistant_msg_entry("hello")],
        )
        traj = _parser.parse(rollout)[0]
        assert traj.parent_trajectory_ref is not None
        assert traj.parent_trajectory_ref.session_id == "fresh-parent"

    def test_regular_session_has_no_agent_role(self, tmp_path: Path):
        """Plain Codex sessions have no agent_role in extra."""
        rollout = tmp_path / "rollout-regular.jsonl"
        _write_rollout(
            rollout,
            [_meta_entry(), _turn_context_entry(), _user_msg_entry(), _assistant_msg_entry()],
        )
        traj = _parser.parse(rollout)[0]
        assert (traj.extra or {}).get("agent_role") is None
        assert traj.parent_trajectory_ref is None
