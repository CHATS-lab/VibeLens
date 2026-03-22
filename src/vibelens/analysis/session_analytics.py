"""Per-session detailed analytics computation.

Computes token breakdowns, tool frequency, step counts, phase segments,
and cost estimation for a single session (main trajectory + sub-agents).
"""

from collections import defaultdict

from vibelens.analysis.phase_detector import detect_phases
from vibelens.analysis.pricing import compute_trajectory_cost
from vibelens.models.analysis.dashboard import SessionAnalytics
from vibelens.models.trajectories import Trajectory


def compute_session_analytics(trajectories: list[Trajectory]) -> SessionAnalytics:
    """Compute detailed analytics for a single session.

    Args:
        trajectories: Trajectory group for one session (main + sub-agents).

    Returns:
        SessionAnalytics with token breakdown, tool frequency, and phase segments.
    """
    if not trajectories:
        raise ValueError("No trajectories provided for session analytics")

    main = trajectories[0]
    all_steps = []
    for traj in trajectories:
        all_steps.extend(traj.steps)

    total_cost = 0.0
    has_cost = False
    for traj in trajectories:
        traj_cost = compute_trajectory_cost(traj)
        if traj_cost is not None:
            total_cost += traj_cost
            has_cost = True

    return SessionAnalytics(
        session_id=main.session_id,
        token_breakdown=_compute_token_breakdown(trajectories),
        tool_frequency=_compute_tool_frequency(trajectories),
        step_count_by_source=_compute_step_counts(trajectories),
        phase_segments=detect_phases(all_steps),
        cost_usd=round(total_cost, 6) if has_cost else None,
    )


def _compute_token_breakdown(trajectories: list[Trajectory]) -> dict[str, int]:
    """Aggregate token counts by category across all trajectories."""
    prompt = 0
    completion = 0
    cache_read = 0
    cache_write = 0

    for traj in trajectories:
        for step in traj.steps:
            if step.metrics:
                prompt += step.metrics.prompt_tokens
                completion += step.metrics.completion_tokens
                cache_read += step.metrics.cached_tokens
                cache_write += step.metrics.cache_creation_tokens

    return {
        "prompt": prompt,
        "completion": completion,
        "cache_read": cache_read,
        "cache_write": cache_write,
    }


def _compute_tool_frequency(trajectories: list[Trajectory]) -> dict[str, int]:
    """Count tool calls by function name across all trajectories."""
    counts: dict[str, int] = defaultdict(int)
    for traj in trajectories:
        for step in traj.steps:
            for tc in step.tool_calls:
                counts[tc.function_name] += 1
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))


def _compute_step_counts(trajectories: list[Trajectory]) -> dict[str, int]:
    """Count steps by source (user/agent/system) across all trajectories."""
    counts: dict[str, int] = defaultdict(int)
    for traj in trajectories:
        for step in traj.steps:
            counts[step.source.value] += 1
    return dict(counts)
