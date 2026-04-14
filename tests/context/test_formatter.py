"""Tests for src/vibelens/context/formatter.py."""

import os
from datetime import datetime, timezone

from vibelens.context.formatter import (
    build_metadata_block,
    format_agent_message,
    format_user_prompt,
    shorten_path,
    summarize_tool_args,
)
from vibelens.context.params import ContextParams
from vibelens.models.enums import StepSource
from vibelens.models.trajectories.agent import Agent
from vibelens.models.trajectories.step import Step
from vibelens.models.trajectories.tool_call import ToolCall
from vibelens.models.trajectories.trajectory import Trajectory


def _make_trajectory(
    session_id: str = "sess-abc",
    project_path: str | None = None,
    timestamp: datetime | None = None,
    steps: list[Step] | None = None,
) -> Trajectory:
    """Build a minimal Trajectory for testing."""
    if steps is None:
        steps = [
            Step(step_id="s1", source=StepSource.USER, message="hello"),
        ]
    return Trajectory(
        session_id=session_id,
        agent=Agent(name="claude-code"),
        project_path=project_path,
        timestamp=timestamp,
        steps=steps,
    )


def _make_params(
    user_prompt_max_chars: int = 100,
    user_prompt_head_chars: int = 60,
    user_prompt_tail_chars: int = 40,
    bash_command_max_chars: int = 80,
    tool_arg_max_chars: int = 50,
    shorten_home_prefix: bool = True,
    path_max_segments: int = 3,
    agent_message_max_chars: int = 100,
    agent_message_head_chars: int = 70,
    agent_message_tail_chars: int = 30,
) -> ContextParams:
    """Build a ContextParams with sensible test defaults."""
    return ContextParams(
        user_prompt_max_chars=user_prompt_max_chars,
        user_prompt_head_chars=user_prompt_head_chars,
        user_prompt_tail_chars=user_prompt_tail_chars,
        bash_command_max_chars=bash_command_max_chars,
        tool_arg_max_chars=tool_arg_max_chars,
        error_truncate_chars=200,
        include_non_error_obs=False,
        observation_max_chars=0,
        agent_message_max_chars=agent_message_max_chars,
        agent_message_head_chars=agent_message_head_chars,
        agent_message_tail_chars=agent_message_tail_chars,
        shorten_home_prefix=shorten_home_prefix,
        path_max_segments=path_max_segments,
    )


# --- build_metadata_block ---


def test_build_metadata_block_contains_session_id() -> None:
    """Metadata block starts with SESSION header containing the session ID."""
    traj = _make_trajectory(session_id="my-session-123")
    block = build_metadata_block(traj)
    assert block.startswith("=== SESSION: my-session-123 ===")
    print(f"PASS: session header present — {block.splitlines()[0]}")


def test_build_metadata_block_contains_project() -> None:
    """Metadata block includes project path when set."""
    traj = _make_trajectory(project_path="/home/user/myproject")
    block = build_metadata_block(traj)
    assert "PROJECT: /home/user/myproject" in block
    print(f"PASS: project path present — {block}")


def test_build_metadata_block_step_counts() -> None:
    """Metadata block shows total step count and per-source breakdown when include_details=True."""
    steps = [
        Step(step_id="s1", source=StepSource.USER, message="prompt"),
        Step(step_id="s2", source=StepSource.AGENT, message="response"),
        Step(step_id="s3", source=StepSource.USER, message="follow-up"),
    ]
    traj = _make_trajectory(steps=steps)
    block = build_metadata_block(traj, include_details=True)
    assert "STEPS: 3 (user=2, agent=1)" in block
    print(f"PASS: step counts correct — {block}")


def test_build_metadata_block_tool_summary() -> None:
    """Metadata block shows tool usage counts sorted by frequency when include_details=True."""
    tc_bash1 = ToolCall(tool_call_id="tc1", function_name="Bash", arguments={"command": "ls"})
    tc_bash2 = ToolCall(tool_call_id="tc2", function_name="Bash", arguments={"command": "pwd"})
    tc_read = ToolCall(tool_call_id="tc3", function_name="Read", arguments={"file_path": "/a"})
    steps = [
        Step(step_id="s1", source=StepSource.USER, message="go"),
        Step(
            step_id="s2",
            source=StepSource.AGENT,
            message="ok",
            tool_calls=[tc_bash1, tc_bash2, tc_read],
        ),
    ]
    traj = _make_trajectory(steps=steps)
    block = build_metadata_block(traj, include_details=True)
    # Bash(2) must appear before Read(1) since it's more frequent
    assert "Bash(2)" in block
    assert "Read(1)" in block
    bash_pos = block.index("Bash(2)")
    read_pos = block.index("Read(1)")
    assert bash_pos < read_pos, "Bash should appear before Read (higher count)"
    print(f"PASS: tool summary correct and sorted — {block}")


def test_build_metadata_block_no_index() -> None:
    """Without session_index, the header omits the index tag."""
    traj = _make_trajectory(session_id="sess-xyz")
    block = build_metadata_block(traj, session_index=None)
    assert "index=" not in block
    assert block.startswith("=== SESSION: sess-xyz ===")
    print(f"PASS: no index tag when session_index=None — {block.splitlines()[0]}")


def test_build_metadata_block_with_index() -> None:
    """With session_index, the header includes the index tag."""
    traj = _make_trajectory(session_id="sess-xyz")
    block = build_metadata_block(traj, session_index=5)
    assert "=== SESSION: sess-xyz (index=5) ===" in block
    print(f"PASS: index tag present — {block.splitlines()[0]}")


def test_build_metadata_block_timestamp() -> None:
    """Metadata block includes timestamp in YYYY-MM-DD HH:MM format."""
    ts = datetime(2024, 6, 15, 12, 0, 0)
    traj = _make_trajectory(timestamp=ts)
    block = build_metadata_block(traj)
    assert "TIMESTAMP: 2024-06-15 12:00" in block
    print(f"PASS: timestamp present — {block}")


def test_format_user_prompt_short() -> None:
    """Short prompts within the limit are returned unchanged."""
    params = _make_params(user_prompt_max_chars=100)
    msg = "short message"
    result = format_user_prompt(msg, params)
    assert result == msg
    print(f"PASS: short prompt unchanged — {repr(result)}")


def test_format_user_prompt_truncated() -> None:
    """Long prompts are truncated with head/tail and a marker."""
    params = _make_params(
        user_prompt_max_chars=20,
        user_prompt_head_chars=10,
        user_prompt_tail_chars=5,
    )
    msg = "A" * 10 + "B" * 10 + "C" * 5
    result = format_user_prompt(msg, params)
    assert "[...truncated...]" in result
    assert result.startswith("A" * 10)
    assert result.endswith("C" * 5)
    print(f"PASS: long prompt truncated with marker — {repr(result)}")


def test_format_agent_message_short() -> None:
    """Short agent messages within the limit are returned unchanged."""
    params = _make_params(agent_message_max_chars=200)
    msg = "I will help you."
    result = format_agent_message(msg, params)
    assert result == msg
    print(f"PASS: short agent message unchanged — {repr(result)}")


def test_format_agent_message_truncated() -> None:
    """Long agent messages are truncated with head/tail and a marker."""
    params = _make_params(
        agent_message_max_chars=20,
        agent_message_head_chars=10,
        agent_message_tail_chars=5,
    )
    msg = "X" * 10 + "Y" * 10 + "Z" * 5
    result = format_agent_message(msg, params)
    assert "[...truncated...]" in result
    assert result.startswith("X" * 10)
    assert result.endswith("Z" * 5)
    print(f"PASS: long agent message truncated — {repr(result)}")


def test_summarize_tool_args_known_tool() -> None:
    """Known tools show only their relevant arg keys."""
    params = _make_params(tool_arg_max_chars=50)
    args = {"file_path": "/a/b/c.py", "irrelevant_key": "ignored"}
    result = summarize_tool_args("Read", args, params)
    assert "file_path=" in result
    assert "irrelevant_key" not in result
    print(f"PASS: Read tool shows only file_path — {repr(result)}")


def test_summarize_tool_args_bash() -> None:
    """Bash tool shows command argument."""
    params = _make_params(bash_command_max_chars=80)
    args = {"command": "ls -la /tmp"}
    result = summarize_tool_args("Bash", args, params)
    assert "command=" in result
    assert "ls -la /tmp" in result
    print(f"PASS: Bash tool shows command — {repr(result)}")


def test_summarize_tool_args_none() -> None:
    """None arguments return empty string."""
    params = _make_params()
    result = summarize_tool_args("Read", None, params)
    assert result == ""
    print("PASS: None arguments return empty string")


def test_summarize_tool_args_unknown_tool_fallback() -> None:
    """Unknown tools fall back to checking common keys."""
    params = _make_params(tool_arg_max_chars=50)
    args = {"query": "search term", "other": "ignored"}
    result = summarize_tool_args("UnknownTool", args, params)
    assert "query=" in result
    assert "search term" in result
    print(f"PASS: unknown tool falls back to common keys — {repr(result)}")


def test_summarize_tool_args_non_dict() -> None:
    """Non-dict arguments are truncated as a string."""
    params = _make_params(bash_command_max_chars=10)
    result = summarize_tool_args("SomeTool", "raw string argument longer than limit", params)
    assert result.endswith("...")
    print(f"PASS: non-dict arguments truncated — {repr(result)}")


def test_shorten_path_home_prefix() -> None:
    """Home directory prefix is replaced with ~."""
    home = os.path.expanduser("~")
    params = _make_params(shorten_home_prefix=True, path_max_segments=0)
    path = f"{home}/projects/foo/bar.py"
    result = shorten_path(path, params)
    assert result.startswith("~")
    assert not result.startswith(home)
    print(f"PASS: home prefix replaced — {repr(result)}")


def test_shorten_path_max_segments() -> None:
    """Path is trimmed to the last N segments when path_max_segments > 0."""
    params = _make_params(shorten_home_prefix=False, path_max_segments=2)
    path = "/very/long/nested/path/to/file.py"
    result = shorten_path(path, params)
    # Should keep only the last 2 segments
    assert "path" not in result or result.endswith("to/file.py")
    # The result's meaningful parts should be at most 2 deep
    pure_parts = [p for p in result.split("/") if p]
    assert len(pure_parts) <= 2, f"Expected at most 2 segments, got: {result}"
    print(f"PASS: path trimmed to last 2 segments — {repr(result)}")


def test_shorten_path_no_home_prefix_when_disabled() -> None:
    """Home prefix is NOT replaced when shorten_home_prefix is False."""
    home = os.path.expanduser("~")
    params = _make_params(shorten_home_prefix=False, path_max_segments=0)
    path = f"{home}/projects/foo.py"
    result = shorten_path(path, params)
    assert result.startswith(home)
    print(f"PASS: home prefix kept when shorten_home_prefix=False — {repr(result)}")


def test_shorten_path_no_trimming_when_zero_segments() -> None:
    """Path is not trimmed when path_max_segments is 0."""
    params = _make_params(shorten_home_prefix=False, path_max_segments=0)
    path = "/a/b/c/d/e/f.py"
    result = shorten_path(path, params)
    assert result == path
    print(f"PASS: full path preserved when path_max_segments=0 — {repr(result)}")


# --- build_metadata_block: header verbosity control ---


def _make_mixed_steps(count: int = 10) -> list[Step]:
    """Build a list of alternating USER/AGENT steps for verbosity tests."""
    return [
        Step(
            step_id=f"step-{i}",
            source=StepSource.USER if i % 3 == 0 else StepSource.AGENT,
            message=f"msg {i}",
        )
        for i in range(count)
    ]


def test_compact_header_omits_steps_and_tools() -> None:
    """Default (include_details=False) emits only SESSION, PROJECT, TIMESTAMP."""
    traj = _make_trajectory(
        session_id="test-session-001",
        project_path="/home/user/myproject",
        timestamp=datetime(2026, 4, 14, 10, 30, 0, tzinfo=timezone.utc),
        steps=_make_mixed_steps(),
    )
    header = build_metadata_block(traj)

    assert "SESSION: test-session-001" in header
    assert "PROJECT:" in header
    assert "TIMESTAMP:" in header
    assert "STEPS:" not in header
    assert "TOOLS:" not in header
    print(f"Compact header:\n{header}")


def test_detailed_header_includes_steps_and_tools() -> None:
    """include_details=True adds STEPS line (TOOLS covered by test_build_metadata_block_tool_summary)."""
    traj = _make_trajectory(
        session_id="test-session-001",
        project_path="/home/user/myproject",
        timestamp=datetime(2026, 4, 14, 10, 30, 0, tzinfo=timezone.utc),
        steps=_make_mixed_steps(),
    )
    header = build_metadata_block(traj, include_details=True)

    assert "SESSION: test-session-001" in header
    assert "STEPS:" in header
    print(f"Detailed header:\n{header}")


def test_compact_timestamp_format() -> None:
    """Compact header uses YYYY-MM-DD HH:MM format, not full ISO."""
    traj = _make_trajectory(
        timestamp=datetime(2026, 4, 14, 10, 30, 0, tzinfo=timezone.utc),
    )
    header = build_metadata_block(traj)

    assert "2026-04-14 10:30" in header
    # Should NOT contain full ISO with seconds and timezone
    assert "+00:00" not in header
    ts_lines = [line for line in header.splitlines() if "TIMESTAMP" in line]
    print(f"Timestamp line: {ts_lines}")


def test_session_index_suffix() -> None:
    """Session index suffix still works in compact mode."""
    traj = _make_trajectory()
    header = build_metadata_block(traj, session_index=3)

    assert "(index=3)" in header
    print(f"Indexed header:\n{header}")
