"""Tests for src/vibelens/context/base.py."""

from datetime import datetime

import pytest

from vibelens.context.base import ContextExtractor, _IndexTracker
from vibelens.context.params import PRESET_DETAIL
from vibelens.models.context import SessionContext
from vibelens.models.enums import StepSource
from vibelens.models.trajectories.agent import Agent
from vibelens.models.trajectories.step import Step
from vibelens.models.trajectories.trajectory import Trajectory
from vibelens.models.trajectories.trajectory_ref import TrajectoryRef


class _StubExtractor(ContextExtractor):
    """Concrete subclass that formats only USER steps with index tracking."""

    def __init__(self) -> None:
        super().__init__(params=PRESET_DETAIL)

    def format_step(self, step: Step, tracker: _IndexTracker) -> str:
        if step.source == StepSource.USER:
            idx = tracker.assign(step.step_id)
            return f"[step_id={idx}] USER: {step.message}"
        return ""


def _make_trajectory(
    session_id: str = "sess-main",
    steps: list[Step] | None = None,
    parent_trajectory_ref: TrajectoryRef | None = None,
    prev_trajectory_ref: TrajectoryRef | None = None,
    next_trajectory_ref: TrajectoryRef | None = None,
    extra: dict | None = None,
    timestamp: datetime | None = None,
) -> Trajectory:
    """Build a minimal Trajectory for testing."""
    if steps is None:
        steps = [Step(step_id="s1", source=StepSource.USER, message="hello")]
    return Trajectory(
        session_id=session_id,
        agent=Agent(name="claude-code"),
        steps=steps,
        parent_trajectory_ref=parent_trajectory_ref,
        prev_trajectory_ref=prev_trajectory_ref,
        next_trajectory_ref=next_trajectory_ref,
        extra=extra,
        created_at=timestamp,
    )


def _make_step(
    step_id: str,
    source: StepSource = StepSource.USER,
    message: str = "msg",
    timestamp: datetime | None = None,
) -> Step:
    """Build a minimal Step for testing."""
    return Step(step_id=step_id, source=source, message=message, timestamp=timestamp)


def test_cannot_instantiate_abc() -> None:
    """ContextExtractor raises TypeError on direct instantiation."""
    with pytest.raises(TypeError):
        ContextExtractor(params=PRESET_DETAIL)  # type: ignore[abstract]
    print("PASS: ContextExtractor cannot be instantiated directly")


def test_extract_returns_session_context() -> None:
    """extract() returns a SessionContext with expected field values."""
    extractor = _StubExtractor()
    traj = _make_trajectory(session_id="sess-abc")
    result = extractor.extract([traj])
    assert isinstance(result, SessionContext)
    assert result.session_id == "sess-abc"
    assert result.context_text  # non-empty
    print(f"PASS: extract returns SessionContext for session {result.session_id!r}")


def test_extract_finds_main_trajectory() -> None:
    """extract() uses the trajectory without parent_trajectory_ref as the main."""
    parent_ref = TrajectoryRef(session_id="sess-main")
    sub_traj = _make_trajectory(
        session_id="sess-sub",
        steps=[Step(step_id="sub1", source=StepSource.USER, message="sub prompt")],
        parent_trajectory_ref=parent_ref,
    )
    main_traj = _make_trajectory(
        session_id="sess-main",
        steps=[Step(step_id="m1", source=StepSource.USER, message="main prompt")],
    )
    extractor = _StubExtractor()
    result = extractor.extract([sub_traj, main_traj])
    assert result.session_id == "sess-main"
    print(f"PASS: main trajectory found — session_id={result.session_id!r}")


def test_extract_detects_compaction_agents() -> None:
    """extract() detects compaction agents via extra['is_compaction'] flag."""
    compaction_step = _make_step("cs1", source=StepSource.AGENT, message="Compacted summary text")
    compaction_traj = _make_trajectory(
        session_id="sess-compact",
        steps=[compaction_step],
        parent_trajectory_ref=TrajectoryRef(session_id="sess-main"),
        extra={"is_compaction": True},
        timestamp=datetime(2024, 1, 1, 0, 0, 0),
    )
    main_step = _make_step(
        "m1",
        source=StepSource.USER,
        message="user prompt",
        timestamp=datetime(2024, 1, 1, 1, 0, 0),
    )
    main_traj = _make_trajectory(
        session_id="sess-main",
        steps=[main_step],
        timestamp=datetime(2024, 1, 1, 0, 0, 0),
    )
    extractor = _StubExtractor()
    result = extractor.extract([main_traj, compaction_traj])
    # Compaction summary should appear in the context text
    assert "COMPACTION SUMMARY" in result.context_text
    assert "Compacted summary text" in result.context_text
    print("PASS: compaction summary interleaved in context_text")


def test_extract_step_index_tracking() -> None:
    """extract() builds a step_index2id mapping for USER steps."""
    steps = [
        _make_step("step-a", source=StepSource.USER, message="first"),
        _make_step("step-b", source=StepSource.AGENT, message="agent response"),
        _make_step("step-c", source=StepSource.USER, message="second"),
    ]
    traj = _make_trajectory(steps=steps)
    extractor = _StubExtractor()
    result = extractor.extract([traj])

    # Only USER steps get tracked by _StubExtractor
    assert 0 in result.step_index2id
    assert result.step_index2id[0] == "step-a"
    assert 1 in result.step_index2id
    assert result.step_index2id[1] == "step-c"
    assert 2 not in result.step_index2id
    print(f"PASS: step_index2id = {result.step_index2id}")


def test_extract_chain_refs() -> None:
    """extract() propagates prev/next trajectory ref IDs to SessionContext."""
    prev_ref = TrajectoryRef(session_id="sess-prev")
    next_ref = TrajectoryRef(session_id="sess-next")
    traj = _make_trajectory(
        session_id="sess-mid",
        prev_trajectory_ref=prev_ref,
        next_trajectory_ref=next_ref,
    )
    extractor = _StubExtractor()
    result = extractor.extract([traj])
    assert result.prev_trajectory_ref_id == "sess-prev"
    assert result.next_trajectory_ref_id == "sess-next"
    print(
        f"PASS: chain refs — prev={result.prev_trajectory_ref_id!r}, "
        f"next={result.next_trajectory_ref_id!r}"
    )


def test_index_tracker_sequential() -> None:
    """_IndexTracker assigns sequential 0-based indices."""
    tracker = _IndexTracker()
    idx0 = tracker.assign("uuid-a")
    idx1 = tracker.assign("uuid-b")
    idx2 = tracker.assign("uuid-c")

    assert idx0 == 0
    assert idx1 == 1
    assert idx2 == 2
    assert tracker.index_to_real_id == {0: "uuid-a", 1: "uuid-b", 2: "uuid-c"}
    print(f"PASS: _IndexTracker sequential — {tracker.index_to_real_id}")
