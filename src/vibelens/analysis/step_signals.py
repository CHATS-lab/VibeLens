"""Step signal builder — trajectory to StepSignal conversion.

Flattens trajectories into StepSignal objects for LLM friction analysis.
Pure function with no I/O, no filtering, no classification.
"""

from vibelens.models.analysis.friction import StepSignal
from vibelens.models.trajectories import Trajectory


def build_step_signals(trajectories: list[Trajectory]) -> list[StepSignal]:
    """Convert trajectories into a flat StepSignal list for LLM consumption.

    Wraps every step in a StepSignal with session-level metadata.
    No filtering or classification — the LLM makes all analytical decisions.

    Args:
        trajectories: Loaded ATIF trajectory objects.

    Returns:
        Ordered list of StepSignal (trajectory order, then step order).
    """
    signals: list[StepSignal] = []
    for trajectory in trajectories:
        for index, step in enumerate(trajectory.steps):
            signals.append(
                StepSignal(
                    session_id=trajectory.session_id,
                    project_path=trajectory.project_path,
                    step_index=index,
                    step=step,
                )
            )
    return signals
