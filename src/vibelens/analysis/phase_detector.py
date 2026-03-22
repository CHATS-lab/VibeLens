"""Session conversation phase detection.

Classifies segments of a coding agent session into phases (exploration,
implementation, debugging, verification, planning) using a sliding
window over tool call categories.  Enables "what fraction of time is
spent exploring vs coding?" analytics.
"""

from vibelens.analysis.tool_categories import TOOL_CATEGORY_MAP
from vibelens.ingest.parsers.base import is_error_content
from vibelens.models.analysis.phase import PhaseSegment
from vibelens.models.enums import SessionPhase
from vibelens.models.trajectories import Step

PHASE_WINDOW_SIZE = 5

# 40% threshold balances sensitivity vs noise: lower values fragment
# sessions into too many micro-phases, higher values miss genuine
# phase transitions in mixed-activity windows.
_DOMINANCE_THRESHOLD = 0.4


def detect_phases(messages: list[Step]) -> list[PhaseSegment]:
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


def _classify_windows(messages: list[Step]) -> list[tuple[int, SessionPhase]]:
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


def _classify_window(window: list[Step]) -> SessionPhase:
    """Classify a single window of messages into a phase."""
    category_counts: dict[str, int] = {}
    total_tools = 0
    has_error = False

    for step in window:
        for tc in step.tool_calls:
            cat = TOOL_CATEGORY_MAP.get(tc.function_name, "other")
            category_counts[cat] = category_counts.get(cat, 0) + 1
            total_tools += 1
        # Check observation results for errors via content prefix convention
        if step.observation:
            for result in step.observation.results:
                if is_error_content(result.content):
                    has_error = True

    if total_tools == 0:
        return SessionPhase.PLANNING

    read_count = category_counts.get("file_read", 0) + category_counts.get("search", 0)
    write_count = category_counts.get("file_write", 0)
    shell_count = category_counts.get("shell", 0)

    read_ratio = read_count / total_tools
    write_ratio = write_count / total_tools
    shell_ratio = shell_count / total_tools

    # Priority order reflects how agents typically work: errors with file
    # activity signal debugging; shell-only (no writes, no errors) means
    # running tests or checks; writes mean implementation; reads-only
    # means exploring/understanding code before acting.
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
    window_phases: list[tuple[int, SessionPhase]], messages: list[Step]
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
            segments.append(_make_segment(messages, current_start, idx - 1, current_phase))
            current_start = idx
            current_phase = phase

    segments.append(_make_segment(messages, current_start, len(messages) - 1, current_phase))
    return segments


def _absorb_small_segments(segments: list[PhaseSegment]) -> list[PhaseSegment]:
    """Absorb sub-threshold segments (1 message) into their neighbors.

    Merges backwards (into predecessor) rather than forwards so that a
    single-message blip doesn't prematurely start a new phase trend.
    """
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


def _make_segment(steps: list[Step], start: int, end: int, phase: SessionPhase) -> PhaseSegment:
    """Build a PhaseSegment from a step range."""
    segment_steps = steps[start : end + 1]
    category_counts: dict[str, int] = {}
    tool_count = 0
    for step in segment_steps:
        for tc in step.tool_calls:
            cat = TOOL_CATEGORY_MAP.get(tc.function_name, "other")
            category_counts[cat] = category_counts.get(cat, 0) + 1
            tool_count += 1

    dominant = max(category_counts, key=category_counts.get) if category_counts else ""
    start_time = steps[start].timestamp if start < len(steps) else None
    end_time = steps[end].timestamp if end < len(steps) else None

    return PhaseSegment(
        phase=phase,
        start_index=start,
        end_index=end,
        start_time=start_time,
        end_time=end_time,
        dominant_tool_category=dominant,
        tool_call_count=tool_count,
    )
