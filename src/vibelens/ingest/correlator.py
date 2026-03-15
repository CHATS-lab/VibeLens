"""Cross-agent session correlator.

Detects when multiple agents worked on the same project in overlapping
time windows.  Neither dataclaw nor VibeLens previously had this
capability — it enables cross-agent workflow analysis.
"""

from datetime import timedelta

from pydantic import BaseModel, Field

from vibelens.models.session import SessionSummary


class CorrelatedSession(BaseModel):
    """A single session participating in a correlated group."""

    source_type: str = Field(
        description="Data source type (e.g. 'local', 'huggingface')."
    )
    session_id: str = Field(description="Unique session identifier.")
    is_main: bool = Field(
        default=True,
        description="Whether this is a main session or a sub-agent session.",
    )


class CorrelatedGroup(BaseModel):
    """A group of sessions from different agents on the same project.

    Includes hierarchy details: which sessions are main-agent sessions
    and which are sub-agent sessions, supporting cascade relationships
    where sub-agents can themselves have subordinate sub-agents.
    """

    project_path: str = Field(
        description="Project path or name shared by all sessions in the group."
    )
    sessions: list[CorrelatedSession] = Field(
        default_factory=list,
        description="Sessions in this correlated group with main/sub-agent roles.",
    )
    time_overlap_seconds: int = Field(
        default=0,
        description="Maximum time overlap between any two sessions in seconds.",
    )


def correlate_sessions(summaries: list[SessionSummary]) -> list[CorrelatedGroup]:
    """Group sessions by project and overlapping time windows.

    Two sessions overlap when their ``[timestamp, timestamp+duration]``
    intervals intersect.  Sessions are grouped by ``project_name``.

    Args:
        summaries: Session summaries from any combination of parsers.

    Returns:
        List of CorrelatedGroup for projects with overlapping sessions.
    """
    by_project: dict[str, list[SessionSummary]] = {}
    for summary in summaries:
        if not summary.project_name or not summary.timestamp:
            continue
        by_project.setdefault(summary.project_name, []).append(summary)

    groups: list[CorrelatedGroup] = []
    for _project_name, project_sessions in by_project.items():
        if len(project_sessions) < 2:
            continue
        overlapping = _find_overlapping(project_sessions)
        if overlapping:
            groups.append(overlapping)
    return groups


def _find_overlapping(sessions: list[SessionSummary]) -> CorrelatedGroup | None:
    """Find sessions with overlapping time intervals within one project.

    Args:
        sessions: Sessions for a single project, all with timestamps.

    Returns:
        CorrelatedGroup if overlaps found, else None.
    """
    intervals = []
    for session in sessions:
        if not session.timestamp:
            continue
        start = session.timestamp
        end = start + timedelta(seconds=max(session.duration, 1))
        source = session.source_type.value if session.source_type else "unknown"
        intervals.append((start, end, source, session.session_id))

    intervals.sort(key=lambda x: x[0])

    overlapping_entries: list[CorrelatedSession] = []
    seen_ids: set[str] = set()
    max_overlap = 0

    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            start_i, end_i, source_i, sid_i = intervals[i]
            start_j, end_j, source_j, sid_j = intervals[j]
            if end_i <= start_j:
                continue
            overlap_start = max(start_i, start_j)
            overlap_end = min(end_i, end_j)
            overlap_seconds = int((overlap_end - overlap_start).total_seconds())
            if overlap_seconds > 0:
                if sid_i not in seen_ids:
                    seen_ids.add(sid_i)
                    overlapping_entries.append(
                        CorrelatedSession(source_type=source_i, session_id=sid_i)
                    )
                if sid_j not in seen_ids:
                    seen_ids.add(sid_j)
                    overlapping_entries.append(
                        CorrelatedSession(source_type=source_j, session_id=sid_j)
                    )
                max_overlap = max(max_overlap, overlap_seconds)

    if not overlapping_entries:
        return None

    project_name = sessions[0].project_name
    return CorrelatedGroup(
        project_path=project_name,
        sessions=overlapping_entries,
        time_overlap_seconds=max_overlap,
    )
