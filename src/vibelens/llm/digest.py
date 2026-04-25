"""Trajectory digest — compress session data for LLM context windows.

Pure functions with no I/O. Produces token-efficient text representations
of trajectory data at three depth levels for different context budgets.
"""

from vibelens.models.trajectories import Trajectory
from vibelens.utils.compat import StrEnum
from vibelens.utils.content import content_to_text, summarize_args, truncate

# Character limits per message at each digest depth
MAX_MESSAGE_CHARS_BRIEF = 80
MAX_MESSAGE_CHARS_STANDARD = 300
MAX_MESSAGE_CHARS_DETAILED = 2000
# Character limit for tool output included in digests
MAX_TOOL_OUTPUT_CHARS = 500
# Sessions with fewer steps than this use detailed depth
STEP_THRESHOLD_DETAILED = 10
# Sessions with fewer steps than this use standard depth (above = brief)
STEP_THRESHOLD_STANDARD = 200


class DigestDepth(StrEnum):
    """Controls how much trajectory detail is included in the digest."""

    BRIEF = "brief"
    STANDARD = "standard"
    DETAILED = "detailed"


def digest_trajectory(trajectories: list[Trajectory], depth: DigestDepth) -> str:
    """Compress a trajectory group into LLM-readable text.

    Args:
        trajectories: List of trajectories (main + sub-agents) for one session.
        depth: Level of detail to include.

    Returns:
        Formatted text digest suitable for LLM context.
    """
    if not trajectories:
        return "[empty session]"

    parts: list[str] = []
    for trajectory in trajectories:
        parts.append(_format_trajectory(trajectory, depth))
    return "\n\n---\n\n".join(parts)


def select_depth(total_steps: int) -> DigestDepth:
    """Auto-select digest depth based on session size.

    Args:
        total_steps: Total number of steps across all trajectories.

    Returns:
        Appropriate DigestDepth for the step count.
    """
    if total_steps < STEP_THRESHOLD_DETAILED:
        return DigestDepth.DETAILED
    if total_steps < STEP_THRESHOLD_STANDARD:
        return DigestDepth.STANDARD
    return DigestDepth.BRIEF


def _format_trajectory(trajectory: Trajectory, depth: DigestDepth) -> str:
    """Format a single trajectory at the given depth."""
    header = _format_header(trajectory)
    steps = [_format_step(i, step, depth) for i, step in enumerate(trajectory.steps)]
    return f"{header}\n\n" + "\n".join(steps)


def _format_header(trajectory: Trajectory) -> str:
    """Format trajectory metadata header."""
    lines = [
        f"SESSION: {trajectory.session_id}",
        f"AGENT: {trajectory.agent.name}",
    ]
    if trajectory.agent.model_name:
        lines.append(f"MODEL: {trajectory.agent.model_name}")
    if trajectory.project_path:
        lines.append(f"PROJECT: {trajectory.project_path}")
    if trajectory.timestamp:
        lines.append(f"TIME: {trajectory.timestamp.isoformat()}")
    lines.append(f"STEPS: {len(trajectory.steps)}")

    if trajectory.parent_trajectory_ref:
        lines.append(f"PARENT: {trajectory.parent_trajectory_ref.trajectory_id}")

    return "\n".join(lines)


def _format_step(index: int, step, depth: DigestDepth) -> str:
    """Format a single step at the given depth.

    Args:
        index: Zero-based step index.
        step: Step model instance.
        depth: Level of detail.

    Returns:
        Formatted step string.
    """
    if depth == DigestDepth.BRIEF:
        return _format_step_brief(index, step)
    if depth == DigestDepth.STANDARD:
        return _format_step_standard(index, step)
    return _format_step_detailed(index, step)


def _format_step_brief(index: int, step) -> str:
    """One-line summary per step."""
    message = content_to_text(step.message)
    truncated = truncate(message, MAX_MESSAGE_CHARS_BRIEF)
    tool_names = [tc.function_name for tc in step.tool_calls]
    tool_part = f" tools=[{','.join(tool_names)}]" if tool_names else ""
    has_error = _has_error_observation(step)
    error_part = " [ERROR]" if has_error else ""
    return f"[{index}] {step.source.value}: {truncated}{tool_part}{error_part}"


def _format_step_standard(index: int, step) -> str:
    """Step with truncated message and tool call summaries."""
    lines: list[str] = []
    message = content_to_text(step.message)
    truncated = truncate(message, MAX_MESSAGE_CHARS_STANDARD)
    lines.append(f"[{index}] {step.source.value}: {truncated}")

    for tc in step.tool_calls:
        args_summary = summarize_args(
            tc.arguments,
            max_total_chars=MAX_MESSAGE_CHARS_BRIEF,
            max_value_chars=40,
        )
        lines.append(f"  -> {tc.function_name}({args_summary})")

    if step.observation:
        for result in step.observation.results:
            content = content_to_text(result.content)
            if result.is_error:
                # Always include error output in full for friction detection
                lines.append(f"  <- ERROR: {truncate(content, MAX_TOOL_OUTPUT_CHARS)}")
            else:
                lines.append(f"  <- {truncate(content, MAX_MESSAGE_CHARS_BRIEF)}")

    return "\n".join(lines)


def _format_step_detailed(index: int, step) -> str:
    """Full step content with truncated tool outputs."""
    lines: list[str] = []
    message = content_to_text(step.message)
    truncated = truncate(message, MAX_MESSAGE_CHARS_DETAILED)
    lines.append(f"[{index}] {step.source.value}:")
    if truncated:
        lines.append(truncated)

    for tc in step.tool_calls:
        args_str = str(tc.arguments) if tc.arguments else ""
        lines.append(f"  TOOL: {tc.function_name}")
        if args_str:
            lines.append(f"  ARGS: {truncate(args_str, MAX_TOOL_OUTPUT_CHARS)}")

    if step.observation:
        for result in step.observation.results:
            content = content_to_text(result.content)
            lines.append(f"  OUTPUT: {truncate(content, MAX_TOOL_OUTPUT_CHARS)}")

    return "\n".join(lines)


def _has_error_observation(step) -> bool:
    """Check whether a step has any error observations."""
    if not step.observation:
        return False
    return any(r.is_error for r in step.observation.results)
