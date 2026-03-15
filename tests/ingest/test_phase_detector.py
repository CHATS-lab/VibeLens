"""Tests for vibelens.ingest.phase_detector — session phase classification."""

from datetime import UTC, datetime

from vibelens.ingest.phase_detector import (
    PHASE_WINDOW_SIZE,
    PhaseSegment,
    SessionPhase,
    detect_phases,
)
from vibelens.models.message import Message, ToolCall


def _msg(tool_calls: list[ToolCall] | None = None, ts: datetime | None = None) -> Message:
    """Build a minimal message with optional tool calls."""
    return Message(
        uuid="m1",
        session_id="s1",
        role="assistant",
        type="assistant",
        tool_calls=tool_calls or [],
        timestamp=ts,
    )


def _tc(category: str, is_error: bool = False) -> ToolCall:
    """Build a tool call with a given category."""
    return ToolCall(id="tc1", name="Tool", category=category, is_error=is_error)


# ─── detect_phases
class TestDetectPhases:
    def test_empty_messages(self):
        assert detect_phases([]) == []

    def test_no_tool_calls_is_planning(self):
        messages = [_msg() for _ in range(3)]
        phases = detect_phases(messages)
        assert len(phases) >= 1
        assert phases[0].phase == SessionPhase.PLANNING
        print(f"  planning phase: {phases[0]}")

    def test_all_reads_is_exploration(self):
        messages = [_msg([_tc("file_read")]) for _ in range(PHASE_WINDOW_SIZE + 2)]
        phases = detect_phases(messages)
        exploration = [p for p in phases if p.phase == SessionPhase.EXPLORATION]
        assert len(exploration) >= 1
        print(f"  exploration phases: {len(exploration)}")

    def test_all_writes_is_implementation(self):
        messages = [_msg([_tc("file_write")]) for _ in range(PHASE_WINDOW_SIZE + 2)]
        phases = detect_phases(messages)
        impl = [p for p in phases if p.phase == SessionPhase.IMPLEMENTATION]
        assert len(impl) >= 1

    def test_shell_no_errors_is_verification(self):
        messages = [_msg([_tc("shell")]) for _ in range(PHASE_WINDOW_SIZE + 2)]
        phases = detect_phases(messages)
        verif = [p for p in phases if p.phase == SessionPhase.VERIFICATION]
        assert len(verif) >= 1
        print(f"  verification phases: {len(verif)}")

    def test_errors_with_reads_is_debugging(self):
        messages = [
            _msg([_tc("file_read", is_error=True), _tc("file_write")])
            for _ in range(PHASE_WINDOW_SIZE + 2)
        ]
        phases = detect_phases(messages)
        debug = [p for p in phases if p.phase == SessionPhase.DEBUGGING]
        assert len(debug) >= 1

    def test_segments_cover_full_range(self):
        messages = [_msg([_tc("file_read")]) for _ in range(10)]
        phases = detect_phases(messages)
        assert phases[0].start_index == 0
        assert phases[-1].end_index == len(messages) - 1


# ─── PhaseSegment
class TestPhaseSegment:
    def test_start_end_indices(self):
        seg = PhaseSegment(
            phase=SessionPhase.EXPLORATION,
            start_index=0,
            end_index=4,
            tool_call_count=5,
        )
        assert seg.start_index == 0
        assert seg.end_index == 4

    def test_optional_timestamps(self):
        seg = PhaseSegment(
            phase=SessionPhase.IMPLEMENTATION,
            start_index=0,
            end_index=2,
        )
        assert seg.start_time is None
        assert seg.end_time is None

    def test_with_timestamps(self):
        t1 = datetime(2024, 6, 1, tzinfo=UTC)
        t2 = datetime(2024, 6, 1, 0, 5, tzinfo=UTC)
        seg = PhaseSegment(
            phase=SessionPhase.DEBUGGING,
            start_index=0,
            end_index=5,
            start_time=t1,
            end_time=t2,
        )
        assert seg.start_time == t1
        assert seg.end_time == t2


# ─── SessionPhase enum
class TestSessionPhase:
    def test_all_values(self):
        expected = {
            "exploration", "implementation", "debugging",
            "verification", "planning", "mixed",
        }
        actual = {p.value for p in SessionPhase}
        assert actual == expected
        print(f"  phases: {sorted(actual)}")

    def test_str_comparison(self):
        assert SessionPhase.EXPLORATION == "exploration"
        assert SessionPhase.DEBUGGING == "debugging"
