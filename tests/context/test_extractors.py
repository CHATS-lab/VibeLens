"""Tests for src/vibelens/context/extractors.py."""

from datetime import datetime

from vibelens.context.extractors import (
    DetailExtractor,
    MetadataExtractor,
    SummaryExtractor,
)
from vibelens.context.params import ContextParams
from vibelens.models.enums import StepSource
from vibelens.models.trajectories.agent import Agent
from vibelens.models.trajectories.observation import Observation
from vibelens.models.trajectories.observation_result import ObservationResult
from vibelens.models.trajectories.step import Step
from vibelens.models.trajectories.tool_call import ToolCall
from vibelens.models.trajectories.trajectory import Trajectory
from vibelens.models.trajectories.trajectory_ref import TrajectoryRef


def _make_trajectory(
    session_id: str = "sess-main",
    steps: list[Step] | None = None,
    parent_trajectory_ref: TrajectoryRef | None = None,
    extra: dict | None = None,
    timestamp: datetime | None = None,
    project_path: str | None = "~/Projects/VibeLens",
) -> Trajectory:
    """Build a minimal Trajectory for testing."""
    if steps is None:
        steps = [Step(step_id="s1", source=StepSource.USER, message="hello")]
    return Trajectory(
        session_id=session_id,
        agent=Agent(name="claude-code"),
        steps=steps,
        parent_trajectory_ref=parent_trajectory_ref,
        extra=extra,
        created_at=timestamp,
        project_path=project_path,
    )


def _make_step(
    step_id: str,
    source: StepSource = StepSource.USER,
    message: str = "msg",
    timestamp: datetime | None = None,
    tool_calls: list[ToolCall] | None = None,
    observation: Observation | None = None,
) -> Step:
    """Build a minimal Step for testing."""
    return Step(
        step_id=step_id,
        source=source,
        message=message,
        timestamp=timestamp,
        tool_calls=tool_calls or [],
        observation=observation,
    )


def _make_compaction_agent(
    session_id: str, summary: str, parent_session_id: str = "sess-main", ts: datetime | None = None
) -> Trajectory:
    """Build a compaction sub-agent trajectory with one AGENT step."""
    agent_step = _make_step("cs1", source=StepSource.AGENT, message=summary, timestamp=ts)
    return _make_trajectory(
        session_id=session_id,
        steps=[agent_step],
        parent_trajectory_ref=TrajectoryRef(session_id=parent_session_id),
        extra={"is_compaction_agent": True},
        timestamp=ts,
        project_path=None,
    )


def _make_tool_call(
    tool_call_id: str, function_name: str, arguments: dict | None = None
) -> ToolCall:
    """Build a ToolCall for testing."""
    return ToolCall(
        tool_call_id=tool_call_id, function_name=function_name, arguments=arguments or {}
    )


def _make_observation(tool_call_id: str, content: str) -> Observation:
    """Build an Observation with one result for testing."""
    return Observation(results=[ObservationResult(source_call_id=tool_call_id, content=content)])


def test_metadata_extractor_first_prompt_only() -> None:
    """MetadataExtractor includes only the first user prompt, not subsequent steps."""
    steps = [
        _make_step("s1", StepSource.USER, "First user prompt"),
        _make_step("s2", StepSource.AGENT, "Agent response"),
        _make_step("s3", StepSource.USER, "Second user prompt"),
    ]
    traj = _make_trajectory(steps=steps)
    extractor = MetadataExtractor()
    result = extractor.extract([traj])

    assert "First user prompt" in result.context_text
    assert "Second user prompt" not in result.context_text
    assert "Agent response" not in result.context_text
    print(f"PASS: only first user prompt included — {result.context_text[:100]}")


def test_metadata_extractor_ignores_compaction() -> None:
    """MetadataExtractor produces no COMPACTION block even when compaction agents exist."""
    compaction = _make_compaction_agent(
        session_id="sess-compact",
        summary="The session involved refactoring auth...",
        ts=datetime(2024, 1, 1, 0, 0, 0),
    )
    main_step = _make_step(
        "m1", StepSource.USER, "User request", timestamp=datetime(2024, 1, 1, 1, 0, 0)
    )
    main = _make_trajectory(steps=[main_step], timestamp=datetime(2024, 1, 1, 0, 0, 0))
    extractor = MetadataExtractor()
    result = extractor.extract([main, compaction])

    assert "COMPACTION" not in result.context_text
    print("PASS: MetadataExtractor ignores compaction agents")


def test_metadata_extractor_custom_params() -> None:
    """MetadataExtractor accepts custom ContextParams."""
    custom = ContextParams(
        user_prompt_max_chars=10,
        user_prompt_head_chars=7,
        user_prompt_tail_chars=3,
        bash_command_max_chars=0,
        tool_arg_max_chars=0,
        error_truncate_chars=100,
        include_non_error_obs=False,
        observation_max_chars=0,
        agent_message_max_chars=0,
        agent_message_head_chars=0,
        agent_message_tail_chars=0,
        shorten_home_prefix=True,
        path_max_segments=1,
    )
    steps = [_make_step("s1", StepSource.USER, "A" * 30)]
    traj = _make_trajectory(steps=steps)
    extractor = MetadataExtractor(params=custom)
    result = extractor.extract([traj])

    assert extractor.params == custom
    # Prompt was longer than 10 chars so it must be truncated
    assert "[...truncated...]" in result.context_text
    is_truncated = "[...truncated...]" in result.context_text
    print(f"PASS: custom params accepted and applied — truncated={is_truncated}")


def test_metadata_extractor_has_metadata_block() -> None:
    """MetadataExtractor output includes compact header (SESSION, PROJECT) without STEPS/TOOLS."""
    tc = _make_tool_call("tc1", "Edit", {"file_path": "/a/b.py"})
    steps = [
        _make_step("s1", StepSource.USER, "do something"),
        _make_step("s2", StepSource.AGENT, "ok", tool_calls=[tc]),
    ]
    traj = _make_trajectory(session_id="abc123", steps=steps)
    extractor = MetadataExtractor()
    result = extractor.extract([traj], session_index=0)

    assert "=== SESSION: abc123 (index=0) ===" in result.context_text
    assert "STEPS:" not in result.context_text
    assert "TOOLS:" not in result.context_text
    print(f"PASS: compact metadata block present — {result.context_text.splitlines()[:5]}")


def test_summary_extractor_with_compaction() -> None:
    """SummaryExtractor includes COMPACTION SUMMARY and skips step-by-step agent content."""
    compaction = _make_compaction_agent(
        session_id="sess-compact",
        summary="JWT migration completed successfully.",
        ts=datetime(2024, 1, 1, 0, 0, 0),
    )
    ts_user = datetime(2024, 1, 1, 1, 0, 0)
    ts_agent = datetime(2024, 1, 1, 1, 1, 0)
    steps = [
        _make_step("s1", StepSource.USER, "Refactor auth", timestamp=ts_user),
        _make_step("s2", StepSource.AGENT, "Working on it...", timestamp=ts_agent),
    ]
    main = _make_trajectory(steps=steps, timestamp=ts_user)
    extractor = SummaryExtractor()
    result = extractor.extract([main, compaction])

    assert "COMPACTION SUMMARY (latest)" in result.context_text
    assert "JWT migration completed successfully." in result.context_text
    # Agent step-by-step content should NOT appear
    assert "Working on it..." not in result.context_text
    print(f"PASS: compaction summary present, agent steps omitted — {result.context_text[:200]}")


def test_summary_extractor_uses_latest_compaction() -> None:
    """SummaryExtractor shows only the latest compaction summary when multiple exist."""
    compaction_old = _make_compaction_agent(
        session_id="sess-compact-old",
        summary="Earlier summary text.",
        ts=datetime(2024, 1, 1, 0, 0, 0),
    )
    compaction_new = _make_compaction_agent(
        session_id="sess-compact-new",
        summary="Later summary text — more accurate.",
        ts=datetime(2024, 1, 2, 0, 0, 0),
    )
    ts_main = datetime(2024, 1, 3, 0, 0, 0)
    steps = [_make_step("m1", StepSource.USER, "main prompt", timestamp=ts_main)]
    main = _make_trajectory(steps=steps, timestamp=ts_main)
    extractor = SummaryExtractor()
    result = extractor.extract([main, compaction_old, compaction_new])

    assert "Later summary text" in result.context_text
    assert "Earlier summary text" not in result.context_text
    print(f"PASS: only latest compaction summary shown — {result.context_text}")


def test_summary_extractor_without_compaction() -> None:
    """SummaryExtractor falls back to all user prompts when no compaction agents exist."""
    steps = [
        _make_step("s1", StepSource.USER, "First question"),
        _make_step("s2", StepSource.AGENT, "I will help"),
        _make_step("s3", StepSource.USER, "Follow-up question"),
        _make_step("s4", StepSource.AGENT, "Done"),
    ]
    traj = _make_trajectory(steps=steps)
    extractor = SummaryExtractor()
    result = extractor.extract([traj])

    # Both user prompts should appear
    assert "First question" in result.context_text
    assert "Follow-up question" in result.context_text
    # Agent messages should NOT appear
    assert "I will help" not in result.context_text
    assert "Done" not in result.context_text
    assert "COMPACTION" not in result.context_text
    print(f"PASS: fallback shows all user prompts, no agent messages — {result.context_text[:200]}")


# ---------------------------------------------------------------------------
# DetailExtractor tests
# ---------------------------------------------------------------------------
def test_detail_extractor_includes_everything() -> None:
    """DetailExtractor output includes user prompts, agent messages, and TOOL lines."""
    tc = _make_tool_call("tc1", "Read", {"file_path": "/src/main.py"})
    obs = _make_observation("tc1", "file contents here")
    steps = [
        _make_step("s1", StepSource.USER, "Read the file for me"),
        _make_step("s2", StepSource.AGENT, "Reading now", tool_calls=[tc], observation=obs),
    ]
    traj = _make_trajectory(steps=steps)
    extractor = DetailExtractor()
    result = extractor.extract([traj])

    assert "USER: Read the file for me" in result.context_text
    assert "AGENT:" in result.context_text
    assert "TOOL: fn=Read" in result.context_text
    print(f"PASS: user, agent, and tool lines present — {result.context_text[:300]}")


def test_detail_extractor_interleaves_compaction() -> None:
    """DetailExtractor interleaves COMPACTION SUMMARY blocks between steps."""
    compaction = _make_compaction_agent(
        session_id="sess-compact",
        summary="Session so far: implemented auth module.",
        ts=datetime(2024, 1, 1, 1, 0, 0),
    )
    steps = [
        _make_step("s1", StepSource.USER, "Start task", timestamp=datetime(2024, 1, 1, 0, 30, 0)),
        _make_step("s2", StepSource.USER, "Continue task", timestamp=datetime(2024, 1, 1, 2, 0, 0)),
        # Add an agent step with tool to ensure it's not empty
        _make_step(
            "s3",
            StepSource.AGENT,
            "Working",
            timestamp=datetime(2024, 1, 1, 2, 1, 0),
            tool_calls=[_make_tool_call("tc1", "Bash", {"command": "ls"})],
            observation=_make_observation("tc1", "file1.py"),
        ),
    ]
    main = _make_trajectory(steps=steps, timestamp=datetime(2024, 1, 1, 0, 30, 0))
    extractor = DetailExtractor()
    result = extractor.extract([main, compaction])

    assert "COMPACTION SUMMARY" in result.context_text
    assert "Session so far: implemented auth module." in result.context_text
    assert "Start task" in result.context_text
    assert "Continue task" in result.context_text
    print(f"PASS: compaction interleaved with steps — {result.context_text[:400]}")


def test_detail_extractor_skips_system_steps() -> None:
    """DetailExtractor omits SYSTEM steps from the output."""
    steps = [
        _make_step("s1", StepSource.USER, "User request"),
        _make_step("s2", StepSource.SYSTEM, "System internal prompt — do not show"),
        _make_step(
            "s3",
            StepSource.AGENT,
            "Done",
            tool_calls=[_make_tool_call("tc1", "Bash", {"command": "pwd"})],
            observation=_make_observation("tc1", "/home/user"),
        ),
    ]
    traj = _make_trajectory(steps=steps)
    extractor = DetailExtractor()
    result = extractor.extract([traj])

    assert "System internal prompt" not in result.context_text
    assert "User request" in result.context_text
    print(f"PASS: system step content absent — {result.context_text[:300]}")
