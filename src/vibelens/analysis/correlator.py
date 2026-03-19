"""Cross-agent session correlator.

Detects when multiple agents worked on the same project in overlapping
time windows.  Neither dataclaw nor VibeLens previously had this
capability — it enables cross-agent workflow analysis.
"""

from datetime import timedelta

from pydantic import BaseModel, Field

from vibelens.models.trajectories import Trajectory


class CorrelatedSession(BaseModel):
    """A single session participating in a correlated group."""

    agent_name: str = Field(description="Agent name (e.g. 'claude-code', 'codex').")
    session_id: str = Field(description="Unique session identifier.")
    is_main: bool = Field(
        default=True,
        description="Whether this is a main session or a sub-agent session.",
    )


class CorrelatedGroup(BaseModel):
    """A group of trajectories from different agents on the same project.

    Includes hierarchy details: which sessions are main-agent sessions
    and which are sub-agent sessions, supporting cascade relationships
    where sub-agents can themselves have subordinate sub-agents.
    """

    project_path: str = Field(description="Project path shared by all trajectories in the group.")
    sessions: list[CorrelatedSession] = Field(
        default_factory=list,
        description="Sessions in this correlated group with main/sub-agent roles.",
    )
    time_overlap_seconds: int = Field(
        default=0,
        description="Maximum time overlap between any two sessions in seconds.",
    )


def correlate_sessions(trajectories: list[Trajectory]) -> list[CorrelatedGroup]:
    """Group trajectories by project and overlapping time windows.

    Two trajectories overlap when their ``[timestamp, timestamp+duration]``
    intervals intersect.  Trajectories are grouped by ``project_path``.

    Args:
        trajectories: Trajectory objects from any combination of parsers.

    Returns:
        List of CorrelatedGroup for projects with overlapping sessions.
    """
    by_project: dict[str, list[Trajectory]] = {}
    for traj in trajectories:
        if not traj.project_path or not traj.timestamp:
            continue
        by_project.setdefault(traj.project_path, []).append(traj)

    groups: list[CorrelatedGroup] = []
    for _project_path, project_trajectories in by_project.items():
        if len(project_trajectories) < 2:
            continue
        overlapping = _find_overlapping(project_trajectories)
        if overlapping:
            groups.append(overlapping)
    return groups


def _find_overlapping(trajectories: list[Trajectory]) -> CorrelatedGroup | None:
    """Find trajectories with overlapping time intervals within one project.

    Args:
        trajectories: Trajectories for a single project, all with timestamps.

    Returns:
        CorrelatedGroup if overlaps found, else None.
    """
    intervals = []
    for traj in trajectories:
        if not traj.timestamp:
            continue
        start = traj.timestamp
        duration = traj.final_metrics.duration if traj.final_metrics else 1
        end = start + timedelta(seconds=max(duration, 1))
        agent_name = traj.agent.name if traj.agent else "unknown"
        intervals.append((start, end, agent_name, traj.session_id))

    intervals.sort(key=lambda x: x[0])

    overlapping_entries: list[CorrelatedSession] = []
    # A session can overlap with multiple others; seen_ids prevents
    # adding it to the result list more than once.
    seen_ids: set[str] = set()
    max_overlap = 0

    # O(n²) pairwise scan is acceptable: project-level session counts
    # are small (typically < 100 even for active projects).
    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            start_i, end_i, agent_i, sid_i = intervals[i]
            start_j, end_j, agent_j, sid_j = intervals[j]
            if end_i <= start_j:
                continue
            overlap_start = max(start_i, start_j)
            overlap_end = min(end_i, end_j)
            overlap_seconds = int((overlap_end - overlap_start).total_seconds())
            if overlap_seconds > 0:
                if sid_i not in seen_ids:
                    seen_ids.add(sid_i)
                    overlapping_entries.append(
                        CorrelatedSession(agent_name=agent_i, session_id=sid_i)
                    )
                if sid_j not in seen_ids:
                    seen_ids.add(sid_j)
                    overlapping_entries.append(
                        CorrelatedSession(agent_name=agent_j, session_id=sid_j)
                    )
                max_overlap = max(max_overlap, overlap_seconds)

    if not overlapping_entries:
        return None

    project_path = trajectories[0].project_path or ""
    return CorrelatedGroup(
        project_path=project_path,
        sessions=overlapping_entries,
        time_overlap_seconds=max_overlap,
    )
