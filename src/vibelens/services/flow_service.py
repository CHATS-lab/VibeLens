"""Flow analysis service — tool dependency graph and phase detection."""

from vibelens.analysis.phase_detector import detect_phases
from vibelens.analysis.tool_graph import build_tool_graph
from vibelens.deps import get_store
from vibelens.models.trajectories import Trajectory


def compute_flow_from_trajectories(
    trajectories: list[Trajectory], identifier: str
) -> dict[str, str | list[dict] | dict]:
    """Compute tool dependency graph and phase segments from trajectories.

    Shared logic used by both session and share flow endpoints.

    Args:
        trajectories: Trajectory objects to analyze.
        identifier: Session ID or share token for the graph.

    Returns:
        Dict with session_id, tool_graph, and phase_segments.
    """
    all_steps = []
    for traj in trajectories:
        all_steps.extend(traj.steps)

    tool_graph = build_tool_graph(all_steps, identifier)
    phase_segments = detect_phases(all_steps)

    return {
        "session_id": identifier,
        "tool_graph": tool_graph.model_dump(mode="json"),
        "phase_segments": [seg.model_dump(mode="json") for seg in phase_segments],
    }


def get_session_flow(
    session_id: str, session_token: str | None
) -> dict[str, str | list[dict] | dict] | None:
    """Compute tool dependency graph and phase segments for a single session.

    Args:
        session_id: Main session identifier.
        session_token: Browser tab token for upload scoping.

    Returns:
        Dict with session_id, tool_graph, and phase_segments, or None if not found.
    """
    group = get_store().load(session_id, session_token=session_token)
    if not group:
        return None
    return compute_flow_from_trajectories(group, session_id)
