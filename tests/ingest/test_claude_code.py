"""Unit tests for vibelens.ingest.claude_code parser."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vibelens.ingest.parsers.base import MAX_FIRST_MESSAGE_LENGTH, is_error_content
from vibelens.ingest.parsers.claude_code import (
    ClaudeCodeParser,
    _decompose_raw_content,
    _extract_git_branches,
)
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import (
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
)

_parser = ClaudeCodeParser()


@pytest.fixture
def claude_dir(tmp_path: Path) -> Path:
    """Create a minimal ~/.claude directory structure."""
    d = tmp_path / ".claude"
    d.mkdir()
    (d / "projects").mkdir()
    return d


@pytest.fixture
def project_dir(claude_dir: Path) -> Path:
    """Create a project subdirectory."""
    p = claude_dir / "projects" / "-Users-Test-MyProject"
    p.mkdir(parents=True)
    return p


def _write_history(claude_dir: Path, entries: list[dict]) -> None:
    """Write entries to history.jsonl."""
    with open(claude_dir / "history.jsonl", "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _write_session(path: Path, entries: list[dict]) -> None:
    """Write entries to a session .jsonl file."""
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


class TestDecomposeRawContent:
    def test_plain_and_empty_strings(self):
        """Plain strings, empty strings, and whitespace all produce expected text output."""
        # Plain string passes through
        message, reasoning, tool_calls, obs = _decompose_raw_content("Hello world")
        assert message == "Hello world"
        assert reasoning is None
        assert tool_calls == []
        assert obs is None

        # Empty string
        message, _, tool_calls, _ = _decompose_raw_content("")
        assert message == ""
        assert tool_calls == []

        # Whitespace is stripped to empty
        message, _, _, _ = _decompose_raw_content("   ")
        assert message == ""
        print("  plain/empty/whitespace strings handled correctly")

    def test_content_block_types(self):
        """Text, thinking, and tool_use blocks are each decomposed correctly."""
        # Text block
        message, _, _, _ = _decompose_raw_content([{"type": "text", "text": "Hello"}])
        assert message == "Hello"

        # Thinking block
        _, reasoning, _, _ = _decompose_raw_content([{"type": "thinking", "thinking": "hmm"}])
        assert reasoning == "hmm"

        # Tool use block
        _, _, tool_calls, _ = _decompose_raw_content(
            [
                {
                    "type": "tool_use",
                    "id": "tu-1",
                    "name": "Bash",
                    "input": {"command": "ls"},
                }
            ]
        )
        assert len(tool_calls) == 1
        assert tool_calls[0].function_name == "Bash"
        assert tool_calls[0].tool_call_id == "tu-1"
        assert tool_calls[0].arguments == {"command": "ls"}
        print("  text/thinking/tool_use blocks decomposed correctly")

    def test_tool_result_block(self):
        """Tool result blocks produce observation with source_call_id linkage."""
        _, _, _, obs = _decompose_raw_content(
            [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu-1",
                    "content": "file contents",
                    "is_error": False,
                }
            ]
        )
        assert obs is not None
        assert obs.results[0].source_call_id == "tu-1"

    def test_mixed_blocks(self):
        """Multiple block types in one content array are all extracted."""
        message, reasoning, tool_calls, _ = _decompose_raw_content(
            [
                {"type": "thinking", "thinking": "Let me think"},
                {"type": "text", "text": "Here is my answer"},
                {"type": "tool_use", "id": "tu-1", "name": "Read", "input": {}},
            ]
        )
        assert reasoning == "Let me think"
        assert message == "Here is my answer"
        assert len(tool_calls) == 1
        print("  mixed blocks: thinking + text + tool_use decomposed")

    def test_tool_use_with_results(self):
        """Tool results are injected via the result map,
        including errors and multiple calls."""
        # Matching result
        raw = [{"type": "tool_use", "id": "tu-1", "name": "Read", "input": {}}]
        results = {"tu-1": {"output": "file content", "is_error": False}}
        _, _, tool_calls, obs = _decompose_raw_content(raw, results)
        assert len(tool_calls) == 1
        assert obs is not None
        assert obs.results[0].source_call_id == "tu-1"
        assert obs.results[0].content == "file content"

        # Error result uses "[ERROR]" prefix
        results_err = {"tu-1": {"output": "command not found", "is_error": True}}
        _, _, _, obs_err = _decompose_raw_content(raw, results_err)
        assert obs_err is not None
        assert "[ERROR]" in obs_err.results[0].content

        # Multiple tool calls with results
        raw_multi = [
            {"type": "tool_use", "id": "tu-1", "name": "Read", "input": {}},
            {"type": "text", "text": "intermediate"},
            {"type": "tool_use", "id": "tu-2", "name": "Edit", "input": {}},
        ]
        results_multi = {
            "tu-1": {"output": "content", "is_error": False},
            "tu-2": {"output": "edited", "is_error": False},
        }
        _, _, tool_calls_m, obs_m = _decompose_raw_content(raw_multi, results_multi)
        assert len(tool_calls_m) == 2
        assert obs_m is not None
        assert len(obs_m.results) == 2
        print("  tool results injected: normal, error, multiple calls")


class TestParseHistoryIndex:
    def test_basic_history_parsing(self, claude_dir: Path):
        """Covers single session fields, multi-entry dedup, sort order, since filter, and limit."""
        _write_history(
            claude_dir,
            [
                {
                    "sessionId": "old",
                    "display": "Old message",
                    "timestamp": 1700000000000,
                    "project": "/Users/Test/ProjA",
                },
                {
                    "sessionId": "old",
                    "display": "Second old entry",
                    "timestamp": 1700000001000,
                    "project": "/Users/Test/ProjA",
                },
                {
                    "sessionId": "mid",
                    "display": "Mid message",
                    "timestamp": 1710000000000,
                    "project": "/Users/Test/ProjB",
                },
                {
                    "sessionId": "new1",
                    "display": "New1",
                    "timestamp": 1720000000000,
                    "project": "/p",
                },
                {
                    "sessionId": "new2",
                    "display": "New2",
                    "timestamp": 1730000000000,
                    "project": "/p",
                },
            ],
        )
        # All sessions returned, sorted newest-first
        result = _parser.parse_history_index(claude_dir)
        assert len(result) == 4
        assert result[0].session_id == "new2"
        assert result[-1].session_id == "old"

        # Session fields
        old_traj = [t for t in result if t.session_id == "old"][0]
        assert old_traj.project_path == "/Users/Test/ProjA"
        assert old_traj.first_message == "Old message"
        assert old_traj.final_metrics.total_steps == 2
        print(f"  parsed {len(result)} sessions, sorted newest-first")

        # since filter
        since = datetime(2024, 3, 1, tzinfo=UTC)
        filtered = _parser.parse_history_index(claude_dir, since=since)
        filtered_ids = {t.session_id for t in filtered}
        assert "old" not in filtered_ids
        assert "new1" in filtered_ids
        print(f"  since filter kept {len(filtered)} of 4 sessions")

        # limit
        limited = _parser.parse_history_index(claude_dir, limit=2)
        assert len(limited) == 2
        print(f"  limit=2 returned {len(limited)} sessions")

    def test_edge_cases(self, claude_dir: Path):
        """Missing file, empty file, malformed JSON, missing sessionId, and blank lines."""
        # Missing history file
        assert _parser.parse_history_index(claude_dir) == []

        # Empty history file
        (claude_dir / "history.jsonl").write_text("")
        assert _parser.parse_history_index(claude_dir) == []

        # Malformed JSON + missing sessionId + blank lines mixed with valid entry
        with open(claude_dir / "history.jsonl", "w") as f:
            f.write("NOT VALID JSON\n")
            f.write("\n")
            no_id = {"display": "No session id", "timestamp": 1000000, "project": "/p"}
            f.write(json.dumps(no_id) + "\n")
            valid = {"sessionId": "s1", "display": "Valid", "timestamp": 1000000, "project": "/p"}
            f.write(json.dumps(valid) + "\n")
            f.write("\n")
        result = _parser.parse_history_index(claude_dir)
        assert len(result) == 1
        assert result[0].session_id == "s1"
        print("  edge cases: missing/empty/malformed/blank all handled")

    def test_first_message_truncated(self, claude_dir: Path):
        """Long first_message is truncated with '...' suffix."""
        long_message = "x" * 500
        _write_history(
            claude_dir,
            [{"sessionId": "s1", "display": long_message, "timestamp": 1000000, "project": "/p"}],
        )
        result = _parser.parse_history_index(claude_dir)
        # Truncation adds "..." suffix beyond the max length
        assert len(result[0].first_message) == MAX_FIRST_MESSAGE_LENGTH + 3
        assert result[0].first_message.endswith("...")
        print(f"  truncated to {len(result[0].first_message)} chars")


class TestParseSessionJsonl:
    def test_basic_parsing(self, tmp_path: Path):
        """User message, assistant content, timestamp, and usage are all parsed correctly."""
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "user",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "timestamp": 1707734674932,
                    "message": {"role": "user", "content": "Hello"},
                },
                {
                    "type": "assistant",
                    "uuid": "m2",
                    "sessionId": "s1",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Hi there"}],
                        "model": "claude-sonnet-4-6",
                        "usage": {
                            "input_tokens": 500,
                            "output_tokens": 200,
                            "cache_read_input_tokens": 100,
                        },
                    },
                },
            ],
        )
        result = _parser.parse_session_jsonl(f)
        assert len(result) == 2

        # User step
        user_step = result[0]
        assert user_step.source == StepSource.USER
        assert user_step.message == "Hello"
        assert user_step.timestamp is not None
        assert user_step.timestamp.tzinfo == UTC

        # Assistant step
        agent_step = result[1]
        assert agent_step.model_name == "claude-sonnet-4-6"
        assert agent_step.metrics is not None
        # prompt_tokens = input_tokens + cache_read_input_tokens (Harbor-aligned)
        assert agent_step.metrics.prompt_tokens == 600
        assert agent_step.metrics.cached_tokens == 100
        print(f"  parsed {len(result)} steps with timestamps and usage")

    def test_tool_use_pairing(self, tmp_path: Path):
        """Tool use in assistant message is paired with tool result from next user message."""
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "Let me read that."},
                            {
                                "type": "tool_use",
                                "id": "tu-1",
                                "name": "Read",
                                "input": {"file_path": "/tmp/test.py"},
                            },
                        ],
                    },
                },
                {
                    "type": "user",
                    "uuid": "m2",
                    "sessionId": "s1",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tu-1",
                                "content": "print('hello')",
                            }
                        ],
                    },
                },
            ],
        )
        result = _parser.parse_session_jsonl(f)
        agent_step = [s for s in result if s.source == StepSource.AGENT][0]
        assert len(agent_step.tool_calls) == 1
        assert agent_step.tool_calls[0].function_name == "Read"
        assert agent_step.observation is not None
        assert agent_step.observation.results[0].content == "print('hello')"
        print("  tool_use paired with tool_result via tool_use_id")

    def test_error_marking(self, tmp_path: Path):
        """Tool results with is_error=True produce error-marked observation content."""
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tu-1",
                                "name": "Bash",
                                "input": {"command": "bad"},
                            },
                        ],
                    },
                },
                {
                    "type": "user",
                    "uuid": "m2",
                    "sessionId": "s1",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tu-1",
                                "content": "command not found",
                                "is_error": True,
                            }
                        ],
                    },
                },
            ],
        )
        result = _parser.parse_session_jsonl(f)
        agent_step = [s for s in result if s.source == StepSource.AGENT][0]
        assert agent_step.observation is not None
        assert is_error_content(agent_step.observation.results[0].content)
        print("  error tool results marked with [ERROR] prefix")

    def test_edge_cases(self, tmp_path: Path):
        """Nonexistent file, empty file, non-relevant types, malformed lines, and sidechain flag."""
        # Nonexistent file
        assert _parser.parse_session_jsonl(tmp_path / "missing.jsonl") == []

        # Empty file
        empty = tmp_path / "empty.jsonl"
        empty.write_text("")
        assert _parser.parse_session_jsonl(empty) == []

        # Non-relevant types filtered + malformed lines skipped
        mixed = tmp_path / "mixed.jsonl"
        with open(mixed, "w") as fh:
            fh.write("INVALID JSON\n")
            sys_entry = {
                "type": "system",
                "uuid": "m0",
                "message": {"role": "system", "content": "sys"},
            }
            fh.write(json.dumps(sys_entry) + "\n")
            user_entry = {
                "type": "user",
                "uuid": "m1",
                "sessionId": "s1",
                "message": {"role": "user", "content": "valid"},
            }
            fh.write(json.dumps(user_entry) + "\n")
        result = _parser.parse_session_jsonl(mixed)
        assert len(result) == 1
        assert result[0].source == StepSource.USER

        # Sidechain flag in extra
        sidechain = tmp_path / "sidechain.jsonl"
        _write_session(
            sidechain,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "isSidechain": True,
                    "message": {"role": "assistant", "content": "sub-agent response"},
                }
            ],
        )
        sc_result = _parser.parse_session_jsonl(sidechain)
        assert sc_result[0].extra is not None
        assert sc_result[0].extra.get("is_sidechain") is True
        print("  edge cases: missing/empty/filtered/malformed/sidechain all handled")


class TestMetadataViaAssembleTrajectory:
    """Tests that assemble_trajectory auto-computes first_message and final_metrics."""

    def test_metrics_aggregation(self):
        """Step count, token sums, and tool call count are aggregated across steps."""
        steps = [
            Step(
                step_id="m1",
                source=StepSource.AGENT,
                metrics=Metrics(
                    prompt_tokens=100,
                    completion_tokens=50,
                    cached_tokens=30,
                    cache_creation_tokens=20,
                ),
                tool_calls=[ToolCall(function_name="Read"), ToolCall(function_name="Edit")],
            ),
            Step(
                step_id="m2",
                source=StepSource.AGENT,
                metrics=Metrics(
                    prompt_tokens=200,
                    completion_tokens=100,
                    cached_tokens=70,
                    cache_creation_tokens=10,
                ),
                tool_calls=[ToolCall(function_name="Bash")],
            ),
            Step(step_id="m3", source=StepSource.USER, message="hi"),
        ]
        traj = _parser.assemble_trajectory(
            session_id="test", agent=_parser.build_agent("claude-code"), steps=steps
        )
        # Step count includes all steps
        assert traj.final_metrics.total_steps == 3

        # Token aggregation
        assert traj.final_metrics.total_prompt_tokens == 300
        assert traj.final_metrics.total_completion_tokens == 150
        assert traj.final_metrics.total_cache_read == 100
        assert traj.final_metrics.total_cache_write == 30

        # Tool call count
        assert traj.final_metrics.tool_call_count == 3

        # Steps without metrics contribute zero
        steps_no_metrics = [Step(step_id="m1", source=StepSource.USER)]
        traj_no = _parser.assemble_trajectory(
            session_id="test2", agent=_parser.build_agent("claude-code"), steps=steps_no_metrics
        )
        assert traj_no.final_metrics.total_prompt_tokens == 0
        step_count = traj.final_metrics.total_steps
        tc_count = traj.final_metrics.tool_call_count
        print(f"  metrics aggregated: {step_count} steps, {tc_count} tool calls")

    def test_first_message(self):
        """First user message is extracted and truncated when too long."""
        # First user message found even when agent speaks first
        steps = [
            Step(step_id="m1", source=StepSource.AGENT, message="I'll help"),
            Step(step_id="m2", source=StepSource.USER, message="Fix the bug"),
        ]
        traj = _parser.assemble_trajectory(
            session_id="test", agent=_parser.build_agent("claude-code"), steps=steps
        )
        assert traj.first_message == "Fix the bug"

        # Long first message is truncated
        long = "x" * 500
        steps_long = [Step(step_id="m1", source=StepSource.USER, message=long)]
        traj_long = _parser.assemble_trajectory(
            session_id="test2", agent=_parser.build_agent("claude-code"), steps=steps_long
        )
        assert len(traj_long.first_message) == MAX_FIRST_MESSAGE_LENGTH + 3
        print("  first_message extraction and truncation verified")

    def test_duration(self):
        """Duration computed from first/last timestamps, zero for single or missing timestamps."""
        t1 = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2025, 1, 1, 10, 5, 0, tzinfo=UTC)

        # Two timestamps produce 300s duration
        steps = [
            Step(step_id="m1", source=StepSource.USER, timestamp=t1),
            Step(step_id="m2", source=StepSource.AGENT, timestamp=t2),
        ]
        traj = _parser.assemble_trajectory(
            session_id="test", agent=_parser.build_agent("claude-code"), steps=steps
        )
        assert traj.final_metrics.duration == 300

        # Single timestamp produces zero duration
        traj_single = _parser.assemble_trajectory(
            session_id="test2",
            agent=_parser.build_agent("claude-code"),
            steps=[Step(step_id="m1", source=StepSource.USER, timestamp=t1)],
        )
        assert traj_single.final_metrics.duration == 0

        # No timestamps produce zero duration
        traj_none = _parser.assemble_trajectory(
            session_id="test3",
            agent=_parser.build_agent("claude-code"),
            steps=[
                Step(step_id="m1", source=StepSource.USER),
                Step(step_id="m2", source=StepSource.AGENT),
            ],
        )
        assert traj_none.final_metrics.duration == 0
        print("  duration: 300s, 0s (single), 0s (no timestamps)")


class TestSubagentParsing:
    def test_subagent_trajectories(self, tmp_path: Path):
        """Subagent JSONL files produce separate Trajectory objects
        linked via parent_trajectory_ref."""
        main_file = tmp_path / "session-abc.jsonl"
        _write_session(
            main_file,
            [
                {
                    "type": "user",
                    "uuid": "m1",
                    "sessionId": "session-abc",
                    "message": {"role": "user", "content": "Main message"},
                },
                {
                    "type": "assistant",
                    "uuid": "m2",
                    "sessionId": "session-abc",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tu-agent-1",
                                "name": "Agent",
                                "input": {"prompt": "do something"},
                            }
                        ],
                    },
                },
                {
                    "type": "user",
                    "uuid": "m3",
                    "sessionId": "session-abc",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tu-agent-1",
                                "content": "Task completed. agentId: 001",
                            }
                        ],
                    },
                },
            ],
        )

        subagent_dir = tmp_path / "session-abc" / "subagents"
        subagent_dir.mkdir(parents=True)
        for agent_id in ["agent-001", "agent-002"]:
            _write_session(
                subagent_dir / f"{agent_id}.jsonl",
                [
                    {
                        "type": "assistant",
                        "uuid": f"sa-{agent_id}",
                        "sessionId": "session-abc",
                        "message": {"role": "assistant", "content": f"from {agent_id}"},
                    }
                ],
            )

        trajectories = _parser.parse_file(main_file)
        print(f"  total trajectories: {len(trajectories)}")
        for traj in trajectories:
            print(f"    session_id={traj.session_id}, steps={len(traj.steps)}")
            if traj.parent_trajectory_ref:
                print(f"    parent_trajectory_ref={traj.parent_trajectory_ref.session_id}")

        # Main + 2 sub-agents
        assert len(trajectories) == 3
        main_traj = trajectories[0]
        assert len(main_traj.steps) >= 1

        # Sub-agent trajectories link back to parent via parent_trajectory_ref
        sub_trajs = trajectories[1:]
        for sub_traj in sub_trajs:
            assert sub_traj.parent_trajectory_ref is not None
            assert sub_traj.parent_trajectory_ref.session_id == main_traj.session_id

        sub_session_ids = {t.session_id for t in sub_trajs}
        assert sub_session_ids == {"agent-001", "agent-002"}

    def test_no_subagent_scenarios(self, tmp_path: Path):
        """No subagent dir and empty subagent dir both produce only the main trajectory."""
        # No subagent directory at all
        main_file = tmp_path / "session.jsonl"
        _write_session(
            main_file,
            [
                {
                    "type": "user",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {"role": "user", "content": "solo"},
                }
            ],
        )
        trajectories = _parser.parse_file(main_file)
        print(f"  no subagent dir: {len(trajectories)} trajectories")
        assert len(trajectories) == 1

        # Empty subagent directory
        main_file2 = tmp_path / "session2.jsonl"
        _write_session(
            main_file2,
            [
                {
                    "type": "user",
                    "uuid": "m1",
                    "sessionId": "s2",
                    "message": {"role": "user", "content": "solo2"},
                }
            ],
        )
        (tmp_path / "session2" / "subagents").mkdir(parents=True)
        trajectories2 = _parser.parse_file(main_file2)
        assert len(trajectories2) == 1
        print(f"  empty subagent dir: {len(trajectories2)} trajectories")

        # parse_session_jsonl excludes subagent messages from main session
        main_file3 = tmp_path / "session3.jsonl"
        _write_session(
            main_file3,
            [
                {
                    "type": "user",
                    "uuid": "m1",
                    "sessionId": "session3",
                    "message": {"role": "user", "content": "Main only"},
                }
            ],
        )
        sa_dir = tmp_path / "session3" / "subagents"
        sa_dir.mkdir(parents=True)
        _write_session(
            sa_dir / "agent-x.jsonl",
            [
                {
                    "type": "assistant",
                    "uuid": "sa-1",
                    "sessionId": "session3",
                    "message": {"role": "assistant", "content": "Subagent"},
                }
            ],
        )
        main_steps = _parser.parse_session_jsonl(main_file3)
        assert len(main_steps) == 1
        assert main_steps[0].message == "Main only"
        print("  main session excludes subagent messages")


class TestDiscoverSubagentOnlySessions:
    def test_discover_subagent_only_sessions(self, tmp_path: Path):
        """Finds session dirs with only subagent files,
        ignores dirs with root JSONL, tool-only, empty, or nonexistent."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Session with root JSONL — should NOT be returned
        (project_dir / "has-root.jsonl").write_text("{}\n")
        sa_dir = project_dir / "has-root" / "subagents"
        sa_dir.mkdir(parents=True)
        (sa_dir / "agent-a1.jsonl").write_text("{}\n")

        # Session with only subagent data — SHOULD be returned
        sa_dir2 = project_dir / "subagent-only" / "subagents"
        sa_dir2.mkdir(parents=True)
        (sa_dir2 / "agent-b1.jsonl").write_text("{}\n")

        # Tool-only dir — should NOT be returned
        (project_dir / "tool-only" / "tool-results").mkdir(parents=True)

        # Empty subagent dir — should NOT be returned
        (project_dir / "empty-sa" / "subagents").mkdir(parents=True)

        result = _parser.discover_subagent_only_sessions(project_dir)
        print(f"  discovered: {[p.name for p in result]}")
        assert len(result) == 1
        assert result[0].parent.name == "subagent-only"

        # Nonexistent project dir
        assert _parser.discover_subagent_only_sessions(tmp_path / "nonexistent") == []

        # Directory with only root JSONL, no session subdirs
        flat_dir = tmp_path / "flat"
        flat_dir.mkdir()
        (flat_dir / "session.jsonl").write_text("{}\n")
        assert _parser.discover_subagent_only_sessions(flat_dir) == []
        print("  subagent-only discovery: correct filtering verified")


class TestMetricsDedup:
    def test_streaming_chunks_merged_into_single_step(self, tmp_path: Path):
        """Consecutive entries with same message.id are merged into one step."""
        f = tmp_path / "session.jsonl"
        shared_msg_id = "msg_abc123"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {
                        "id": shared_msg_id,
                        "role": "assistant",
                        "content": [{"type": "text", "text": "First chunk"}],
                        "model": "claude-sonnet-4-6",
                        "usage": {"input_tokens": 500, "output_tokens": 200},
                    },
                },
                {
                    "type": "assistant",
                    "uuid": "m2",
                    "sessionId": "s1",
                    "message": {
                        "id": shared_msg_id,
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Second chunk"}],
                        "model": "claude-sonnet-4-6",
                        "usage": {"input_tokens": 500, "output_tokens": 200},
                    },
                },
            ],
        )
        result = _parser.parse_session_jsonl(f)
        assert len(result) == 1
        assert result[0].step_id == shared_msg_id
        assert "First chunk" in result[0].message
        assert "Second chunk" in result[0].message
        assert result[0].metrics is not None
        assert result[0].metrics.prompt_tokens == 500


class TestStepExtraMetadata:
    def test_step_extra_metadata_preserved(self, tmp_path: Path):
        """Entry with stop_reason, cwd, requestId, service_tier all captured in step.extra."""
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "cwd": "/home/user/project",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Done."}],
                        "stop_reason": "end_turn",
                        "requestId": "req-xyz",
                        "service_tier": "standard",
                    },
                },
            ],
        )
        result = _parser.parse_session_jsonl(f)
        assert len(result) == 1
        extra = result[0].extra
        assert extra is not None
        assert extra["stop_reason"] == "end_turn"
        assert extra["cwd"] == "/home/user/project"
        assert extra["request_id"] == "req-xyz"
        assert extra["service_tier"] == "standard"


class TestToolResultMetadata:
    def test_tool_result_metadata_in_observation_extra(self, tmp_path: Path):
        """toolUseResult metadata populates ObservationResult.extra."""
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tu-1",
                                "name": "Bash",
                                "input": {"command": "ls"},
                            }
                        ],
                    },
                },
                {
                    "type": "user",
                    "uuid": "m2",
                    "sessionId": "s1",
                    "toolUseResult": {
                        "stdout": "file1.py\nfile2.py",
                        "stderr": "",
                        "exitCode": 0,
                    },
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tu-1",
                                "content": "file1.py\nfile2.py",
                            }
                        ],
                    },
                },
            ],
        )
        result = _parser.parse_session_jsonl(f)
        agent_step = [s for s in result if s.source == StepSource.AGENT][0]
        assert agent_step.observation is not None
        obs_extra = agent_step.observation.results[0].extra
        assert obs_extra is not None
        assert obs_extra["exit_code"] == 0
        assert obs_extra["stdout"] == "file1.py\nfile2.py"
        assert obs_extra["stderr"] == ""


class TestQueueOperationHandling:
    """Tests for queue-operation (enqueue/dequeue/remove) handling."""

    def test_enqueue_remove_creates_user_step(self, tmp_path: Path):
        """Enqueue + remove pair produces a user step with extra.is_queued_prompt."""
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "user",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "timestamp": 1707734674000,
                    "message": {"role": "user", "content": "Initial prompt"},
                },
                {
                    "type": "assistant",
                    "uuid": "m2",
                    "sessionId": "s1",
                    "timestamp": 1707734675000,
                    "message": {"role": "assistant", "content": "Working on it..."},
                },
                {
                    "type": "queue-operation",
                    "operation": "enqueue",
                    "sessionId": "s1",
                    "timestamp": 1707734676000,
                    "content": "Actually, also do this other thing",
                },
                {
                    "type": "queue-operation",
                    "operation": "remove",
                    "sessionId": "s1",
                    "timestamp": 1707734676000,
                },
            ],
        )
        result = _parser.parse_session_jsonl(f)
        # Should have 3 steps: user, assistant, synthetic user from enqueue
        assert len(result) == 3
        queued_step = result[2]
        assert queued_step.source == StepSource.USER
        assert queued_step.message == "Actually, also do this other thing"
        assert queued_step.extra is not None
        assert queued_step.extra.get("is_queued_prompt") is True

    def test_enqueue_dequeue_no_duplicate(self, tmp_path: Path):
        """Enqueue + dequeue pair does NOT create a synthetic step."""
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "user",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "timestamp": 1707734674000,
                    "message": {"role": "user", "content": "Initial prompt"},
                },
                {
                    "type": "queue-operation",
                    "operation": "enqueue",
                    "sessionId": "s1",
                    "timestamp": 1707734676000,
                    "content": "Follow-up message",
                },
                {
                    "type": "queue-operation",
                    "operation": "dequeue",
                    "sessionId": "s1",
                    "timestamp": 1707734676000,
                },
                {
                    "type": "user",
                    "uuid": "m2",
                    "sessionId": "s1",
                    "timestamp": 1707734677000,
                    "message": {"role": "user", "content": "Follow-up message"},
                },
            ],
        )
        result = _parser.parse_session_jsonl(f)
        # Should have exactly 2 user steps (original + dequeued regular message)
        # NO synthetic step from enqueue
        assert len(result) == 2
        assert all(s.source == StepSource.USER for s in result)
        assert result[0].message == "Initial prompt"
        assert result[1].message == "Follow-up message"
        # Neither should be marked as queued
        for step in result:
            if step.extra:
                assert step.extra.get("is_queued_prompt") is not True

    def test_enqueue_step_has_correct_timestamp(self, tmp_path: Path):
        """Synthetic enqueue step uses the enqueue event's timestamp."""
        f = tmp_path / "session.jsonl"
        enqueue_ts = 1707734676000
        _write_session(
            f,
            [
                {
                    "type": "queue-operation",
                    "operation": "enqueue",
                    "sessionId": "s1",
                    "timestamp": enqueue_ts,
                    "content": "Queued message",
                },
                {
                    "type": "queue-operation",
                    "operation": "remove",
                    "sessionId": "s1",
                    "timestamp": enqueue_ts,
                },
            ],
        )
        result = _parser.parse_session_jsonl(f)
        assert len(result) == 1
        step = result[0]
        assert step.timestamp is not None
        # Timestamp should correspond to enqueue_ts (1707734676000 ms)
        assert step.timestamp.year == 2024
        assert step.step_id.startswith(f"enqueue-{enqueue_ts}-")


class TestStepValidatorHardening:
    def test_orphaned_observation_raises_error(self):
        """Step with observation referencing non-existent tool_call raises ValueError."""
        with pytest.raises(ValueError, match="non-existent tool_call IDs"):
            Step(
                step_id="s1",
                source=StepSource.AGENT,
                tool_calls=[ToolCall(tool_call_id="tc-1", function_name="Read")],
                observation=Observation(
                    results=[
                        ObservationResult(source_call_id="tc-1", content="ok"),
                        ObservationResult(source_call_id="tc-GHOST", content="bad"),
                    ]
                ),
            )

    def test_orphaned_tool_call_warns(self, caplog: pytest.LogCaptureFixture):
        """Step with tool_call but no matching observation succeeds with warning."""
        with caplog.at_level(logging.WARNING):
            step = Step(
                step_id="s1",
                source=StepSource.AGENT,
                tool_calls=[
                    ToolCall(tool_call_id="tc-1", function_name="Read"),
                    ToolCall(tool_call_id="tc-2", function_name="Edit"),
                ],
                observation=Observation(
                    results=[ObservationResult(source_call_id="tc-1", content="ok")]
                ),
            )
        assert step is not None
        assert "tc-2" in caplog.text


class TestSubagentLinkageValidation:
    def test_subagent_linkage_warns_on_broken_ref(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        """Parsing session with missing subagent file logs warning but succeeds."""
        main_file = tmp_path / "session-abc.jsonl"
        _write_session(
            main_file,
            [
                {
                    "type": "user",
                    "uuid": "m1",
                    "sessionId": "session-abc",
                    "message": {"role": "user", "content": "Main message"},
                },
                {
                    "type": "assistant",
                    "uuid": "m2",
                    "sessionId": "session-abc",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tu-agent-1",
                                "name": "Task",
                                "input": {"prompt": "do something"},
                            }
                        ],
                    },
                },
                {
                    "type": "user",
                    "uuid": "m3",
                    "sessionId": "session-abc",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tu-agent-1",
                                "content": "Task completed. agentId: 001",
                            }
                        ],
                    },
                },
            ],
        )

        # Create subagent dir with agent-001 (matched) and agent-002 (unmatched)
        subagent_dir = tmp_path / "session-abc" / "subagents"
        subagent_dir.mkdir(parents=True)
        for agent_id in ["agent-001", "agent-002"]:
            _write_session(
                subagent_dir / f"{agent_id}.jsonl",
                [
                    {
                        "type": "assistant",
                        "uuid": f"sa-{agent_id}",
                        "sessionId": "session-abc",
                        "message": {"role": "assistant", "content": f"from {agent_id}"},
                    }
                ],
            )

        with caplog.at_level(logging.WARNING):
            trajectories = _parser.parse_file(main_file)

        # Should succeed with main + 2 sub-agents
        assert len(trajectories) == 3

        # agent-002 is not referenced by any parent step — should warn
        assert "not referenced by parent" in caplog.text


class TestExtractGitBranches:
    def test_extracts_unique_branches(self):
        """Unique gitBranch values are collected and sorted."""
        content = "\n".join(
            json.dumps({"type": "user", "gitBranch": b})
            for b in ["feature/xyz", "main", "feature/xyz"]
        )
        result = _extract_git_branches(content)
        assert result == ["feature/xyz", "main"]

    def test_returns_none_when_absent(self):
        """Returns None when no entries have gitBranch."""
        content = json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}})
        assert _extract_git_branches(content) is None

    def test_git_branches_in_trajectory_extra(self):
        """Parsed trajectory includes git_branches in extra."""
        entries = [
            {
                "type": "user",
                "uuid": "m1",
                "sessionId": "s1",
                "gitBranch": "dev",
                "message": {"role": "user", "content": "Hello"},
            },
            {
                "type": "assistant",
                "uuid": "m2",
                "sessionId": "s1",
                "gitBranch": "dev",
                "message": {"role": "assistant", "content": "Hi"},
            },
        ]
        content = "\n".join(json.dumps(e) for e in entries)
        trajectories = _parser.parse(content)
        assert len(trajectories) == 1
        assert trajectories[0].extra is not None
        assert trajectories[0].extra["git_branches"] == ["dev"]


class TestStepExtraEnrichment:
    def test_stop_sequence_captured(self, tmp_path: Path):
        """stop_sequence from message is captured in step extra."""
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {
                        "role": "assistant",
                        "content": "done",
                        "stop_reason": "end_turn",
                        "stop_sequence": "\n\nHuman:",
                    },
                },
            ],
        )
        result = _parser.parse_session_jsonl(f)
        assert result[0].extra is not None
        assert result[0].extra["stop_sequence"] == "\n\nHuman:"

    def test_user_type_captured(self, tmp_path: Path):
        """Non-external userType is captured in step extra."""
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "userType": "internal",
                    "message": {"role": "assistant", "content": "hi"},
                },
            ],
        )
        result = _parser.parse_session_jsonl(f)
        assert result[0].extra is not None
        assert result[0].extra["user_type"] == "internal"

    def test_user_type_external_excluded(self, tmp_path: Path):
        """userType='external' is not stored in extra."""
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "userType": "external",
                    "message": {"role": "assistant", "content": "hi"},
                },
            ],
        )
        result = _parser.parse_session_jsonl(f)
        if result[0].extra:
            assert "user_type" not in result[0].extra


class TestErrorHandling:
    def test_all_invalid_json_raises(self):
        """Content where all lines fail JSON parsing raises ValueError."""
        content = "not json\nalso not json\n"
        with pytest.raises(ValueError, match="No parseable entries"):
            _parser.parse(content, source_path="test.jsonl")
