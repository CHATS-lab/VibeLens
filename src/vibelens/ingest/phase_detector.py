"""Session conversation phase detection.

Classifies segments of a coding agent session into phases (exploration,
implementation, debugging, verification, planning) using a sliding
window over tool call categories.  Enables "what fraction of time is
spent exploring vs coding?" analytics.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from vibelens.models.message import Message

PHASE_WINDOW_SIZE = 5

# Minimum fraction of window tools that must match for a dominant phase.
_DOMINANCE_THRESHOLD = 0.4


class SessionPhase(StrEnum):
    """Semantic phase of a coding agent session."""

    EXPLORATION = "exploration"
    IMPLEMENTATION = "implementation"
    DEBUGGING = "debugging"
    VERIFICATION = "verification"
    PLANNING = "planning"
    MIXED = "mixed"


class PhaseSegment(BaseModel):
    """A contiguous range of messages sharing the same phase."""

    phase: SessionPhase = Field(description="Detected phase for this segment.")
    start_index: int = Field(description="First message index (inclusive).")
    end_index: int = Field(description="Last message index (inclusive).")
    start_time: datetime | None = Field(
        default=None, description="Timestamp of first message."
    )
    end_time: datetime | None = Field(
        default=None, description="Timestamp of last message."
    )
    dominant_tool_category: str = Field(
        default="", description="Most frequent tool category in this segment."
    )
    tool_call_count: int = Field(
        default=0, description="Total tool calls in this segment."
    )


def detect_phases(messages: list[Message]) -> list[PhaseSegment]:
    """Detect conversation phases using a sliding window.

    Args:
        messages: Ordered messages from a single session.

    Returns:
        List of PhaseSegment objects covering the full session.
    """
    if not messages:
        return []

    window_phases = _classify_windows(messages)
    if not window_phases:
        return [_make_segment(messages, 0, len(messages) - 1, SessionPhase.PLANNING)]

    raw_segments = _merge_adjacent(window_phases, messages)
    return _absorb_small_segments(raw_segments)


def _classify_windows(messages: list[Message]) -> list[tuple[int, SessionPhase]]:
    """Classify each window position by its dominant tool category.

    Returns:
        List of (start_index, phase) tuples.
    """
    results: list[tuple[int, SessionPhase]] = []
    for start in range(len(messages)):
        end = min(start + PHASE_WINDOW_SIZE, len(messages))
        window = messages[start:end]
        phase = _classify_window(window)
        results.append((start, phase))
    return results


def _classify_window(window: list[Message]) -> SessionPhase:
    """Classify a single window of messages into a phase."""
    category_counts: dict[str, int] = {}
    total_tools = 0
    has_error = False

    for msg in window:
        for tc in msg.tool_calls:
            cat = tc.category or "other"
            category_counts[cat] = category_counts.get(cat, 0) + 1
            total_tools += 1
            if tc.is_error:
                has_error = True

    if total_tools == 0:
        return SessionPhase.PLANNING

    read_count = category_counts.get("file_read", 0) + category_counts.get("search", 0)
    write_count = category_counts.get("file_write", 0)
    shell_count = category_counts.get("shell", 0)

    read_ratio = read_count / total_tools
    write_ratio = write_count / total_tools
    shell_ratio = shell_count / total_tools

    if has_error and (read_ratio + write_ratio) >= _DOMINANCE_THRESHOLD:
        return SessionPhase.DEBUGGING
    if shell_ratio >= 0.5 and write_count == 0 and not has_error:
        return SessionPhase.VERIFICATION
    if write_ratio >= _DOMINANCE_THRESHOLD:
        return SessionPhase.IMPLEMENTATION
    if read_ratio >= 0.6:
        return SessionPhase.EXPLORATION

    return SessionPhase.MIXED


def _merge_adjacent(
    window_phases: list[tuple[int, SessionPhase]], messages: list[Message]
) -> list[PhaseSegment]:
    """Merge adjacent windows with the same phase into segments."""
    if not window_phases:
        return []

    segments: list[PhaseSegment] = []
    current_phase = window_phases[0][1]
    current_start = 0

    for idx in range(1, len(window_phases)):
        _, phase = window_phases[idx]
        if phase != current_phase:
            segments.append(
                _make_segment(messages, current_start, idx - 1, current_phase)
            )
            current_start = idx
            current_phase = phase

    segments.append(
        _make_segment(messages, current_start, len(messages) - 1, current_phase)
    )
    return segments


def _absorb_small_segments(segments: list[PhaseSegment]) -> list[PhaseSegment]:
    """Absorb sub-threshold segments (1 message) into their neighbors."""
    if len(segments) <= 1:
        return segments

    result: list[PhaseSegment] = []
    for seg in segments:
        span = seg.end_index - seg.start_index + 1
        if span <= 1 and result:
            prev = result[-1]
            result[-1] = PhaseSegment(
                phase=prev.phase,
                start_index=prev.start_index,
                end_index=seg.end_index,
                start_time=prev.start_time,
                end_time=seg.end_time,
                dominant_tool_category=prev.dominant_tool_category,
                tool_call_count=prev.tool_call_count + seg.tool_call_count,
            )
        else:
            result.append(seg)
    return result


def _make_segment(
    messages: list[Message], start: int, end: int, phase: SessionPhase
) -> PhaseSegment:
    """Build a PhaseSegment from a message range."""
    segment_messages = messages[start : end + 1]
    category_counts: dict[str, int] = {}
    tool_count = 0
    for msg in segment_messages:
        for tc in msg.tool_calls:
            cat = tc.category or "other"
            category_counts[cat] = category_counts.get(cat, 0) + 1
            tool_count += 1

    dominant = max(category_counts, key=category_counts.get) if category_counts else ""
    start_time = messages[start].timestamp if start < len(messages) else None
    end_time = messages[end].timestamp if end < len(messages) else None

    return PhaseSegment(
        phase=phase,
        start_index=start,
        end_index=end,
        start_time=start_time,
        end_time=end_time,
        dominant_tool_category=dominant,
        tool_call_count=tool_count,
    )
