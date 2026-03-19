"""Unit tests for vibelens.ingest.codex parser."""

import json
from pathlib import Path

from vibelens.ingest.parsers.base import is_error_content
from vibelens.ingest.parsers.codex import (
    CodexParser,
    _parse_structured_output,
    compute_session_tokens_max,
)
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Metrics, Step, Trajectory

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
) -> dict:
    """Build a session_meta rollout entry."""
    payload = {"id": session_id, "cwd": cwd, "timestamp": timestamp}
    return {"type": "session_meta", "timestamp": timestamp, "payload": payload}


def _turn_context_entry(
    model: str = "gpt-5.4",
    timestamp: str = "2025-01-15T10:00:01Z",
) -> dict:
    """Build a turn_context rollout entry."""
    return {
        "type": "turn_context",
        "timestamp": timestamp,
        "payload": {"model": model},
    }


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
        "payload": {
            "type": "function_call_output",
            "call_id": call_id,
            "output": output,
        },
    }


def _reasoning_entry(
    text: str = "Let me think about this...",
    timestamp: str = "2025-01-15T10:00:05Z",
) -> dict:
    """Build a reasoning response_item entry."""
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {
            "type": "reasoning",
            "summary": [{"text": text}],
        },
    }


def _token_count_entry(
    input_tokens: int = 500,
    output_tokens: int = 200,
    cached_tokens: int = 100,
    timestamp: str = "2025-01-15T10:00:06Z",
) -> dict:
    """Build a token_count event_msg entry."""
    return {
        "type": "event_msg",
        "timestamp": timestamp,
        "payload": {
            "type": "token_count",
            "info": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "input_tokens_details": {"cached_tokens": cached_tokens},
            },
        },
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
        results = _parser.parse_file(rollout)
        assert len(results) == 1
        traj = results[0]
        assert isinstance(traj, Trajectory)
        steps = traj.steps
        print(f"  traj: id={traj.session_id}")
        print(f"  steps: {len(steps)}")
        for s in steps:
            msg = s.message[:50] if isinstance(s.message, str) else str(s.message)[:50]
            print(f"    source={s.source}, model_name={s.model_name}, message={msg}")
        assert traj.session_id == "sess-1"
        assert len(steps) == 2
        assert steps[0].source == StepSource.USER
        assert steps[0].message == "Hello"
        assert steps[1].source == StepSource.AGENT
        assert steps[1].message == "Hi there"

    def test_metadata_extraction(self, tmp_path: Path):
        """Session ID, project path, first message, and duration are all extracted correctly."""
        # Session ID from meta payload
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
        results = _parser.parse_file(rollout_meta)
        traj = results[0]
        print(f"  session_id={traj.session_id}")
        print(f"  project_path={traj.project_path}")
        print(f"  first_message={traj.first_message}")
        print(f"  duration={traj.final_metrics and traj.final_metrics.duration}")

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
        fallback_traj = _parser.parse_file(rollout_fallback)[0]
        assert fallback_traj.session_id == "rollout-fallback"

    def test_edge_cases(self, tmp_path: Path):
        """Empty file, missing file, meta-only, and developer role are handled gracefully."""
        # Empty file returns empty
        empty_rollout = tmp_path / "rollout-empty.jsonl"
        empty_rollout.write_text("")
        assert _parser.parse_file(empty_rollout) == []

        # Missing file returns empty
        assert _parser.parse_file(tmp_path / "does-not-exist.jsonl") == []

        # Meta-only (no messages) returns empty
        meta_only = tmp_path / "rollout-meta-only.jsonl"
        _write_rollout(meta_only, [_meta_entry()])
        assert _parser.parse_file(meta_only) == []

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
        dev_steps = _parser.parse_file(dev_rollout)[0].steps
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
                _function_call_output_entry(
                    call_id="fc-1",
                    output="file1.txt",
                ),
                # Turn 2: multiple calls in same turn
                _assistant_msg_entry("Let me run", timestamp=f"{t}05Z"),
                _function_call_entry(
                    call_id="fc-2",
                    name="shell",
                    timestamp=f"{t}06Z",
                ),
                _function_call_output_entry(
                    call_id="fc-2",
                    output="output-2",
                    timestamp=f"{t}07Z",
                ),
                _function_call_entry(
                    call_id="fc-3",
                    name="read_file",
                    timestamp=f"{t}08Z",
                ),
                _function_call_output_entry(
                    call_id="fc-3",
                    output="output-3",
                    timestamp=f"{t}09Z",
                ),
                # Turn 3: trailing tool calls flushed at end
                _assistant_msg_entry("checking", timestamp=f"{t}10Z"),
                _function_call_entry(
                    call_id="fc-last",
                    name="shell",
                    timestamp=f"{t}11Z",
                ),
                _function_call_output_entry(
                    call_id="fc-last",
                    output="done",
                    timestamp=f"{t}12Z",
                ),
            ],
        )
        results = _parser.parse_file(rollout)
        steps = results[0].steps
        agent_steps = [s for s in steps if s.source == StepSource.AGENT]
        print(f"  agent_steps: {len(agent_steps)}")
        for step in agent_steps:
            print(f"    tool_calls={len(step.tool_calls)}, message={step.message[:30]}")

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
        results = _parser.parse_file(rollout)
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
        results = _parser.parse_file(rollout)
        steps = results[0].steps
        user_steps = [s for s in steps if s.source == StepSource.USER]
        agent_steps = [s for s in steps if s.source == StepSource.AGENT]

        for a in agent_steps:
            msg = a.message[:30] if isinstance(a.message, str) else str(a.message)[:30]
            print(f"    agent model_name={a.model_name}, message={msg}")

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
        """Token counts attach to agent steps, not user steps."""
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
                    cached_tokens=100,
                ),
            ],
        )
        results = _parser.parse_file(rollout)
        steps = results[0].steps
        agent_step = [s for s in steps if s.source == StepSource.AGENT][0]
        user_step = [s for s in steps if s.source == StepSource.USER][0]

        print(f"  agent metrics: {agent_step.metrics}")
        print(f"  user metrics: {user_step.metrics}")

        # Agent step has token metrics attached
        assert agent_step.metrics is not None
        assert agent_step.metrics.prompt_tokens == 500
        assert agent_step.metrics.completion_tokens == 200
        assert agent_step.metrics.cached_tokens == 100

        # User step has no metrics
        assert user_step.metrics is None


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

        results = _parser.parse_file(rollout)
        assert len(results) == 1
        steps = results[0].steps
        print(f"  steps parsed: {len(steps)}")
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
                        "summary": [
                            {"text": "First thought"},
                            {"text": "Second thought"},
                        ],
                    },
                },
            ],
        )
        results = _parser.parse_file(rollout)
        steps = results[0].steps
        agent_steps = [s for s in steps if s.source == StepSource.AGENT]

        print(f"  turn1 thinking: {agent_steps[0].reasoning_content}")
        print(f"  turn2 thinking: {agent_steps[1].reasoning_content}")

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
        results = _parser.parse_file(rollout)
        steps = results[0].steps
        agent_step = steps[0]
        assert agent_step.reasoning_content is not None
        # "Same thought" appears once, "Different thought" once
        lines = agent_step.reasoning_content.split("\n")
        print(f"  reasoning lines: {lines}")
        assert len(lines) == 2
        assert "Same thought" in lines
        assert "Different thought" in lines


class TestStructuredOutput:
    """Tests for structured output prefix stripping and error detection."""

    def test_structured_output_parsing(self):
        """Exit code stripping, error detection, multiline output, and passthrough all work."""
        # Exit code 0: prefix stripped, no error
        cleaned, has_error = _parse_structured_output(
            "Exit code: 0\nWall time: 1.23s\nOutput:\nactual output here"
        )
        assert cleaned == "actual output here"
        assert has_error is False

        # Non-zero exit code: error detected
        cleaned, has_error = _parse_structured_output(
            "Exit code: 1\nWall time: 0.5s\nOutput:\nerror message"
        )
        assert cleaned == "error message"
        assert has_error is True

        # Multiline output after prefix
        cleaned, _ = _parse_structured_output(
            "Exit code: 0\nWall time: 2.00s\nOutput:\nline1\nline2\nline3"
        )
        assert cleaned == "line1\nline2\nline3"

        # No prefix: returned as-is
        cleaned, has_error = _parse_structured_output("plain output without prefix")
        assert cleaned == "plain output without prefix"
        assert has_error is False

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
        results = _parser.parse_file(rollout)
        steps = results[0].steps
        agent_steps = [s for s in steps if s.source == StepSource.AGENT]

        # Error case: marked with error prefix, content preserved
        err_obs = agent_steps[0].observation.results[0]
        print(f"  error content: {err_obs.content}")
        assert is_error_content(err_obs.content)
        assert "command not found: foo" in err_obs.content

        # Success case: no error prefix
        ok_obs = agent_steps[1].observation.results[0]
        print(f"  success content: {ok_obs.content}")
        assert not is_error_content(ok_obs.content)
        assert ok_obs.content == "file1.txt"


class TestTokenStrategyMax:
    """Tests for compute_session_tokens_max using max-not-sum strategy."""

    def test_max_token_strategy(self):
        """Max strategy picks per-field max across steps, handles empty/missing metrics."""
        # Multiple steps: takes max, not sum
        steps_multi = [
            Step(
                step_id="m1",
                source=StepSource.AGENT,
                metrics=Metrics(prompt_tokens=100, completion_tokens=50),
            ),
            Step(
                step_id="m2",
                source=StepSource.AGENT,
                metrics=Metrics(prompt_tokens=300, completion_tokens=80),
            ),
            Step(
                step_id="m3",
                source=StepSource.AGENT,
                metrics=Metrics(prompt_tokens=200, completion_tokens=120),
            ),
        ]
        max_in, max_out = compute_session_tokens_max(steps_multi)
        print(f"  multi: max_in={max_in}, max_out={max_out}")
        assert max_in == 300
        assert max_out == 120

        # Empty step list returns zeros
        max_in, max_out = compute_session_tokens_max([])
        assert max_in == 0
        assert max_out == 0

        # Steps without metrics return zeros
        steps_no_metrics = [
            Step(step_id="m1", source=StepSource.AGENT),
            Step(step_id="m2", source=StepSource.USER),
        ]
        max_in, max_out = compute_session_tokens_max(steps_no_metrics)
        assert max_in == 0
        assert max_out == 0

        # Mixed: steps with and without metrics
        steps_mixed = [
            Step(step_id="m1", source=StepSource.USER),
            Step(
                step_id="m2",
                source=StepSource.AGENT,
                metrics=Metrics(prompt_tokens=400, completion_tokens=150),
            ),
            Step(step_id="m3", source=StepSource.AGENT),
        ]
        max_in, max_out = compute_session_tokens_max(steps_mixed)
        assert max_in == 400
        assert max_out == 150

        # Cross-max: different fields maximize independently
        steps_cross = [
            Step(
                step_id="m1",
                source=StepSource.AGENT,
                metrics=Metrics(prompt_tokens=999, completion_tokens=1),
            ),
            Step(
                step_id="m2",
                source=StepSource.AGENT,
                metrics=Metrics(prompt_tokens=1, completion_tokens=999),
            ),
        ]
        max_in, max_out = compute_session_tokens_max(steps_cross)
        assert max_in == 999
        assert max_out == 999
