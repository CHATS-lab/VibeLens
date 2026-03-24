"""Session conversation phase detection.

Classifies segments of a coding agent session into phases (exploration,
implementation, debugging, verification, planning) using a sliding
window over tool call categories.  Enables "what fraction of time is
spent exploring vs coding?" analytics.

User steps are excluded from phase classification — they serve as
natural anchors between phases rather than contributing to phase
identity.  Phase segment indices still refer to the original (full)
step list so the frontend can map segments to steps directly.
"""

from vibelens.analysis.tool_categories import TOOL_CATEGORY_MAP
from vibelens.ingest.parsers.base import is_error_content
from vibelens.models.analysis.phase import PhaseSegment
from vibelens.models.enums import SessionPhase
from vibelens.models.trajectories import Step

PHASE_WINDOW_SIZE = 5

# 35% threshold — slightly lower than before (was 40%) to catch
# phases earlier.  Combined with user-step filtering this produces
# cleaner phase boundaries.
_DOMINANCE_THRESHOLD = 0.35


def detect_phases(steps: list[Step]) -> list[PhaseSegment]:
    """Detect conversation phases using a sliding window over agent steps.

    User steps are excluded from windowing — only agent steps with tool
    calls or text contribute to phase classification.  Segment indices
    map back to the original step list for frontend consumption.

    Args:
        steps: Ordered steps from a single session (all sources).

    Returns:
        List of PhaseSegment objects covering agent activity regions.
    """
    if not steps:
        return []

    # Build (original_index, step) pairs for agent steps only
    agent_entries = [
        (i, step) for i, step in enumerate(steps) if step.source == "agent"
    ]
    if not agent_entries:
        return []

    agent_steps = [s for _, s in agent_entries]
    original_indices = [i for i, _ in agent_entries]

    window_phases = _classify_windows(agent_steps)
    if not window_phases:
        start_idx = original_indices[0]
        end_idx = original_indices[-1]
        return [_make_segment(steps, start_idx, end_idx, SessionPhase.PLANNING)]

    raw_segments = _merge_adjacent(window_phases, agent_steps, original_indices)
    return _absorb_small_segments(raw_segments, steps)


def _classify_windows(agent_steps: list[Step]) -> list[tuple[int, SessionPhase]]:
    """Classify each window position by its dominant tool category.

    Args:
        agent_steps: Agent-only steps (no user/system steps).

    Returns:
        List of (agent_index, phase) tuples.
    """
    results: list[tuple[int, SessionPhase]] = []
    for start in range(len(agent_steps)):
        end = min(start + PHASE_WINDOW_SIZE, len(agent_steps))
        window = agent_steps[start:end]
        phase = _classify_window(window)
        results.append((start, phase))
    return results


def _classify_window(window: list[Step]) -> SessionPhase:
    """Classify a single window of agent steps into a phase.

    Priority order reflects typical agent workflow:
    1. Errors with file activity → debugging (fixing broken code)
    2. Shell-heavy without writes/errors → verification (running tests)
    3. Write-heavy → implementation (creating/editing code)
    4. Read/search-heavy → exploration (understanding codebase)
    5. No tools → planning (pure thinking/reasoning)
    6. Fallback → mixed

    Args:
        window: Consecutive agent steps to classify.

    Returns:
        Detected SessionPhase.
    """
    category_counts: dict[str, int] = {}
    total_tools = 0
    has_error = False

    for step in window:
        for tc in step.tool_calls:
            cat = TOOL_CATEGORY_MAP.get(tc.function_name, "other")
            category_counts[cat] = category_counts.get(cat, 0) + 1
            total_tools += 1
        if step.observation:
            for result in step.observation.results:
                if is_error_content(result.content):
                    has_error = True

    if total_tools == 0:
        return SessionPhase.PLANNING

    read_count = category_counts.get("file_read", 0)
    search_count = category_counts.get("search", 0)
    write_count = category_counts.get("file_write", 0)
    shell_count = category_counts.get("shell", 0)

    read_ratio = (read_count + search_count) / total_tools
    write_ratio = write_count / total_tools
    shell_ratio = shell_count / total_tools

    if has_error and (read_ratio + write_ratio) >= 0.3:
        return SessionPhase.DEBUGGING
    if shell_ratio >= 0.4 and write_count == 0 and not has_error:
        return SessionPhase.VERIFICATION
    if write_ratio >= _DOMINANCE_THRESHOLD:
        return SessionPhase.IMPLEMENTATION
    if read_ratio >= 0.5:
        return SessionPhase.EXPLORATION

    return SessionPhase.MIXED


def _merge_adjacent(
    window_phases: list[tuple[int, SessionPhase]],
    agent_steps: list[Step],
    original_indices: list[int],
) -> list[PhaseSegment]:
    """Merge adjacent windows with the same phase into segments.

    Maps agent-step indices back to original step indices so segment
    boundaries align with the full step list.

    Args:
        window_phases: (agent_index, phase) pairs from classification.
        agent_steps: Agent-only step list.
        original_indices: Mapping from agent index → original step index.

    Returns:
        Merged PhaseSegment list.
    """
    if not window_phases:
        return []

    segments: list[PhaseSegment] = []
    current_phase = window_phases[0][1]
    current_start = 0

    for agent_idx in range(1, len(window_phases)):
        _, phase = window_phases[agent_idx]
        if phase != current_phase:
            orig_start = original_indices[current_start]
            orig_end = original_indices[agent_idx - 1]
            segments.append(
                _make_segment(agent_steps, orig_start, orig_end, current_phase,
                              agent_range=(current_start, agent_idx - 1))
            )
            current_start = agent_idx
            current_phase = phase

    orig_start = original_indices[current_start]
    orig_end = original_indices[-1]
    segments.append(
        _make_segment(agent_steps, orig_start, orig_end, current_phase,
                      agent_range=(current_start, len(agent_steps) - 1))
    )
    return segments


def _absorb_small_segments(
    segments: list[PhaseSegment], all_steps: list[Step]
) -> list[PhaseSegment]:
    """Absorb sub-threshold segments (1 message) into their neighbors.

    Merges backwards (into predecessor) rather than forwards so that a
    single-message blip doesn't prematurely start a new phase trend.

    Args:
        segments: Raw segments from merge step.
        all_steps: Full step list for rebuilding segment metadata.

    Returns:
        Cleaned segment list.
    """
    if len(segments) <= 1:
        return segments

    result: list[PhaseSegment] = []
    for seg in segments:
        span = seg.end_index - seg.start_index + 1
        if span <= 1 and result:
            prev = result[-1]
            result[-1] = _make_segment(
                all_steps, prev.start_index, seg.end_index, prev.phase
            )
        else:
            result.append(seg)
    return result


def _make_segment(
    steps: list[Step],
    start: int,
    end: int,
    phase: SessionPhase,
    agent_range: tuple[int, int] | None = None,
) -> PhaseSegment:
    """Build a PhaseSegment from a step range.

    Args:
        steps: Step list (either agent-only or full, depending on caller).
        start: Start index in the original step list.
        end: End index in the original step list.
        phase: Detected phase for this segment.
        agent_range: Optional (start, end) into agent_steps for counting.
            When None, iterates steps[start:end+1] directly.

    Returns:
        Populated PhaseSegment.
    """
    if agent_range:
        segment_steps = steps[agent_range[0] : agent_range[1] + 1]
    else:
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
