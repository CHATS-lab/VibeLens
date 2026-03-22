"""Per-tool usage statistics computation.

Aggregates tool call counts, per-session averages, and error rates
across trajectories for the dashboard tool usage breakdown.
"""

from collections import defaultdict

from vibelens.ingest.parsers.base import is_error_content
from vibelens.models.analysis.behavior import ToolUsageStat
from vibelens.models.trajectories import Step, Trajectory


def compute_tool_usage(trajectories: list[Trajectory]) -> list[ToolUsageStat]:
    """Compute per-tool usage statistics from full trajectories.

    Args:
        trajectories: Fully loaded Trajectory objects.

    Returns:
        ToolUsageStat list sorted by call_count descending.
    """
    tool_counts: dict[str, int] = defaultdict(int)
    tool_errors: dict[str, int] = defaultdict(int)
    session_count = len(trajectories)

    for traj in trajectories:
        for step in traj.steps:
            for tc in step.tool_calls:
                tool_counts[tc.function_name] += 1
            if step.observation:
                _count_observation_errors(step, tool_errors)

    if session_count == 0:
        return []

    stats = []
    for tool_name, count in tool_counts.items():
        errors = tool_errors.get(tool_name, 0)
        error_rate = round(errors / count, 3) if count > 0 else 0.0
        stats.append(
            ToolUsageStat(
                tool_name=tool_name,
                call_count=count,
                avg_per_session=round(count / session_count, 2),
                error_rate=error_rate,
            )
        )

    stats.sort(key=lambda s: s.call_count, reverse=True)
    return stats


def _count_observation_errors(step: Step, tool_errors: dict[str, int]) -> None:
    """Count error results and attribute them to tool calls."""
    if not step.observation:
        return

    call_map = {tc.tool_call_id: tc.function_name for tc in step.tool_calls}

    for result in step.observation.results:
        if is_error_content(result.content):
            func_name = call_map.get(result.source_call_id or "", "")
            if func_name:
                tool_errors[func_name] += 1
