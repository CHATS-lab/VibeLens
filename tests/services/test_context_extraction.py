"""Tests for context extraction module.

Tests compaction detection via extra flag, full-step extraction,
tool arg summarization, and non-compaction fallback.
"""

from datetime import UTC, datetime

from vibelens.models.analysis.step_ref import StepRef
from vibelens.models.context import SessionContextBatch
from vibelens.models.trajectories.step import Step, ToolCall
from vibelens.models.trajectories.trajectory import Trajectory
from vibelens.models.trajectories.trajectory_ref import TrajectoryRef
from vibelens.services.context_extraction import (
    _find_compaction_agents,
    _find_main_trajectory,
    _summarize_tool_args,
    extract_session_context,
)
from vibelens.services.context_params import PRESET_DETAIL


def _make_step(step_id: str, source: str, message: str, tool_calls: list | None = None) -> Step:
    """Build a minimal Step for testing."""
    return Step(step_id=step_id, source=source, message=message, tool_calls=tool_calls or [])


def _make_trajectory(
    session_id: str,
    steps: list[Step],
    project_path: str | None = None,
    parent_ref: TrajectoryRef | None = None,
    timestamp: datetime | None = None,
    extra: dict | None = None,
) -> Trajectory:
    """Build a minimal Trajectory for testing."""
    return Trajectory(
        session_id=session_id,
        agent={"name": "claude_code"},
        steps=steps,
        project_path=project_path,
        parent_trajectory_ref=parent_ref,
        timestamp=timestamp,
        extra=extra,
    )


def test_extract_without_compaction():
    """Sessions without compaction include user messages and agent tool info."""
    main = _make_trajectory(
        session_id="session-1",
        project_path="/home/user/project",
        steps=[
            _make_step("s1", "user", "Fix the login bug"),
            _make_step(
                "s2",
                "agent",
                "I'll fix it",
                tool_calls=[
                    ToolCall(
                        tool_call_id="tc1",
                        function_name="Edit",
                        arguments={"file_path": "src/auth.py"},
                    )
                ],
            ),
            _make_step("s3", "user", "Looks good, thanks"),
        ],
    )

    ctx = extract_session_context([main])

    assert ctx.session_id == "session-1"
    assert ctx.project_path == "/home/user/project"
    assert "=== SESSION: session-1 ===" in ctx.context_text
    assert "PROJECT: /home/user/project" in ctx.context_text
    assert "Fix the login bug" in ctx.context_text
    assert "fn=Edit" in ctx.context_text
    assert "file_path=src/auth.py" in ctx.context_text
    print(f"Context:\n{ctx.context_text}")


def test_extract_with_compaction():
    """Sessions with compaction include summaries and ALL steps (no duplication)."""
    ts_base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    ts_compact = datetime(2024, 1, 1, 12, 30, 0, tzinfo=UTC)
    ts_after = datetime(2024, 1, 1, 12, 31, 0, tzinfo=UTC)

    main = _make_trajectory(
        session_id="session-2",
        project_path="/home/user/project",
        timestamp=ts_base,
        steps=[
            Step(
                step_id="s1",
                source="user",
                message="Add dark mode",
                tool_calls=[],
                timestamp=ts_base,
            ),
            Step(
                step_id="s2",
                source="agent",
                message="Working on it",
                tool_calls=[],
                timestamp=ts_base,
            ),
            Step(
                step_id="s3",
                source="user",
                message="Also add light theme",
                tool_calls=[],
                timestamp=ts_compact,
            ),
            Step(
                step_id="s4",
                source="agent",
                message="Adding themes",
                tool_calls=[
                    ToolCall(
                        tool_call_id="tc2",
                        function_name="Edit",
                        arguments={"file_path": "theme.css"},
                    )
                ],
                timestamp=ts_after,
            ),
        ],
    )

    compaction = _make_trajectory(
        session_id="acompact-123",
        timestamp=ts_compact,
        extra={"is_compaction_agent": True},
        steps=[
            _make_step("cs1", "system", "Compact context"),
            _make_step(
                "cs2",
                "agent",
                "Summary: User requested dark mode. Agent started implementation.",
            ),
        ],
    )

    ctx = extract_session_context([main, compaction])

    assert ctx.session_id == "session-2"
    # Compaction summary interleaved chronologically (not grouped at top)
    assert "COMPACTION SUMMARY 1" in ctx.context_text
    assert "User requested dark mode" in ctx.context_text
    assert "Add dark mode" in ctx.context_text
    assert "Also add light theme" in ctx.context_text

    # Verify no duplication: each user message appears exactly once
    assert ctx.context_text.count("Add dark mode") == 1
    assert ctx.context_text.count("Also add light theme") == 1

    # Verify interleaving: compaction summary appears AFTER pre-compaction steps
    # but BEFORE post-compaction steps
    summary_pos = ctx.context_text.index("COMPACTION SUMMARY 1")
    dark_mode_pos = ctx.context_text.index("Add dark mode")
    edit_pos = ctx.context_text.index("fn=Edit")
    assert dark_mode_pos < summary_pos, "Pre-compaction step should precede summary"
    assert summary_pos < edit_pos, "Summary should precede post-compaction step"

    # Steps use 0-indexed IDs
    assert "[step_id=0]" in ctx.context_text
    assert ctx.step_index2id is not None

    print(f"Context:\n{ctx.context_text}")


def test_find_main_trajectory():
    """Main trajectory is the one without parent_trajectory_ref."""
    main = _make_trajectory("main-1", [_make_step("s1", "user", "hi")])
    sub = _make_trajectory(
        "sub-1",
        [_make_step("s1", "agent", "subagent")],
        parent_ref=TrajectoryRef(session_id="main-1"),
    )

    result = _find_main_trajectory([sub, main])
    assert result.session_id == "main-1"


def test_find_compaction_agents():
    """Compaction agents are identified by extra flag, not session_id prefix."""
    main = _make_trajectory("main-1", [_make_step("s1", "user", "hi")])
    compact1 = _make_trajectory(
        "acompact-a",
        [_make_step("s1", "system", "compact")],
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
        extra={"is_compaction_agent": True},
    )
    compact2 = _make_trajectory(
        "acompact-b",
        [_make_step("s1", "system", "compact")],
        timestamp=datetime(2024, 1, 1, 13, 0, tzinfo=UTC),
        extra={"is_compaction_agent": True},
    )
    regular_sub = _make_trajectory(
        "agent-sub-1",
        [_make_step("s1", "agent", "sub")],
        parent_ref=TrajectoryRef(session_id="main-1"),
    )

    result = _find_compaction_agents([main, compact1, compact2, regular_sub])
    assert len(result) == 2
    assert result[0].session_id == "acompact-a"
    assert result[1].session_id == "acompact-b"


def test_extra_flag_required_for_compaction():
    """Session_id prefix alone does NOT trigger compaction detection — extra flag is required."""
    main = _make_trajectory("main-1", [_make_step("s1", "user", "hi")])
    # Has compaction-like session_id but no extra flag
    fake_compact = _make_trajectory(
        "acompact-fake",
        [_make_step("s1", "system", "compact")],
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
    )

    result = _find_compaction_agents([main, fake_compact])
    assert len(result) == 0
    print("Correctly ignored trajectory with compaction prefix but no extra flag")


def test_summarize_tool_args():
    """Tool args are summarized per tool-specific rules."""
    params = PRESET_DETAIL

    # Edit: show file_path only
    edit_args = {"file_path": "src/foo.py", "old_string": "xxx", "new_string": "yyy"}
    assert "file_path=src/foo.py" in _summarize_tool_args("Edit", edit_args, params)

    # Bash: show command (truncated)
    result = _summarize_tool_args("Bash", {"command": "pytest tests/ -v -s --tb=short"}, params)
    assert "command=" in result

    # Grep: show pattern and path
    result = _summarize_tool_args("Grep", {"pattern": "def foo", "path": "src/"}, params)
    assert "pattern=def foo" in result
    assert "path=src/" in result

    # Unknown tool: best effort
    result = _summarize_tool_args("CustomTool", {"file_path": "x.py", "other": "value"}, params)
    assert "file_path=x.py" in result

    # None args
    assert _summarize_tool_args("Edit", None, params) == ""

    print("All tool arg tests passed")


def test_linked_session_refs():
    """Context captures prev_trajectory_ref and next_trajectory_ref."""
    main = _make_trajectory("session-3", [_make_step("s1", "user", "hello")])
    main.prev_trajectory_ref = TrajectoryRef(session_id="session-2")
    main.next_trajectory_ref = TrajectoryRef(session_id="session-4")

    ctx = extract_session_context([main])

    assert ctx.prev_trajectory_ref_id == "session-2"
    assert ctx.next_trajectory_ref_id == "session-4"


def test_system_only_trajectory():
    """Trajectory with only a system step produces header-only context (no user/agent content)."""
    main = _make_trajectory(
        "system-only-session",
        [_make_step("s1", "system", "Internal prompt")],
        project_path="/test/project",
    )

    ctx = extract_session_context([main])

    assert ctx.session_id == "system-only-session"
    assert ctx.project_path == "/test/project"
    assert "=== SESSION: system-only-session ===" in ctx.context_text
    # System steps are skipped, so no step IDs assigned
    assert ctx.step_index2id == {}
    print(f"System-only trajectory context:\n{ctx.context_text}")


def test_tool_calls_without_observations():
    """Agent steps with tool calls but no observation are still included."""
    main = _make_trajectory(
        "no-obs-session",
        steps=[
            _make_step("s1", "user", "Read the config"),
            Step(
                step_id="s2",
                source="agent",
                message="Reading config",
                tool_calls=[
                    ToolCall(
                        tool_call_id="tc1",
                        function_name="Read",
                        arguments={"file_path": "config.yaml"},
                    ),
                    ToolCall(
                        tool_call_id="tc2",
                        function_name="Grep",
                        arguments={"pattern": "port", "path": "src/"},
                    ),
                ],
                observation=None,
            ),
        ],
    )

    ctx = extract_session_context([main])

    assert "fn=Read" in ctx.context_text
    assert "fn=Grep" in ctx.context_text
    assert "file_path=config.yaml" in ctx.context_text
    assert "ERROR" not in ctx.context_text
    print(f"No-observation context:\n{ctx.context_text}")


def test_session_context_batch_properties():
    """SessionContextBatch exposes all_trajectories and resolve_step_ref."""
    traj_a = _make_trajectory(
        "sess-a",
        [_make_step("s1", "user", "hello"), _make_step("s2", "agent", "hi")],
    )
    traj_b = _make_trajectory("sess-b", [_make_step("s3", "user", "world")])

    ctx_a = extract_session_context([traj_a])
    ctx_b = extract_session_context([traj_b])

    batch = SessionContextBatch(
        contexts=[ctx_a, ctx_b], session_ids=["sess-a", "sess-b"], skipped_session_ids=["sess-c"]
    )

    assert len(batch.all_trajectories) == 2
    assert batch.session_ids == ["sess-a", "sess-b"]
    assert batch.skipped_session_ids == ["sess-c"]
    print(f"all_trajectories: {len(batch.all_trajectories)}")
    print(f"session_ids: {batch.session_ids}")


def test_session_context_batch_resolve_step_ref():
    """resolve_step_ref resolves 0-indexed refs to real UUIDs and validates."""
    traj = _make_trajectory(
        "sess-a",
        [_make_step("real-uuid-1", "user", "hello"), _make_step("real-uuid-2", "agent", "hi")],
    )
    ctx = extract_session_context([traj])
    batch = SessionContextBatch(contexts=[ctx], session_ids=["sess-a"], skipped_session_ids=[])

    # Synthetic index "0" should resolve to real-uuid-1
    ref = StepRef(session_id="sess-a", start_step_id="0")
    result = batch.resolve_step_ref(ref)
    assert result is not None
    assert result.start_step_id == "real-uuid-1"

    # Invalid session should return None
    bad_ref = StepRef(session_id="nonexistent", start_step_id="0")
    assert batch.resolve_step_ref(bad_ref) is None

    # Invalid step index should return None
    bad_step_ref = StepRef(session_id="sess-a", start_step_id="999")
    assert batch.resolve_step_ref(bad_step_ref) is None

    print(f"Resolved ref: {result}")


def test_session_context_batch_bool_and_len():
    """Empty SessionContextBatch is falsy, non-empty is truthy."""
    empty = SessionContextBatch(contexts=[], session_ids=[], skipped_session_ids=[])
    assert not empty
    assert len(empty) == 0

    traj = _make_trajectory("sess-a", [_make_step("s1", "user", "hello")])
    ctx = extract_session_context([traj])
    non_empty = SessionContextBatch(contexts=[ctx], session_ids=["sess-a"], skipped_session_ids=[])
    assert non_empty
    assert len(non_empty) == 1

    # Iteration works
    items = list(non_empty)
    assert len(items) == 1
    assert items[0].session_id == "sess-a"
    print(f"Empty: bool={bool(empty)}, len={len(empty)}")
    print(f"Non-empty: bool={bool(non_empty)}, len={len(non_empty)}")
