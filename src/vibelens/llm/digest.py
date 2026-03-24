"""Trajectory digest — compress session data for LLM context windows.

Pure functions with no I/O. Produces token-efficient text representations
of trajectory data at three depth levels for different context budgets.
"""

from enum import StrEnum

from vibelens.models.trajectories import Trajectory

MAX_MESSAGE_CHARS_BRIEF = 80
MAX_MESSAGE_CHARS_STANDARD = 300
MAX_MESSAGE_CHARS_DETAILED = 2000
MAX_TOOL_OUTPUT_CHARS = 500
STEP_THRESHOLD_DETAILED = 10
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
    message = _extract_text(step.message)
    truncated = _truncate(message, MAX_MESSAGE_CHARS_BRIEF)
    tool_names = [tc.function_name for tc in step.tool_calls]
    tool_part = f" tools=[{','.join(tool_names)}]" if tool_names else ""
    has_error = _has_error_observation(step)
    error_part = " [ERROR]" if has_error else ""
    return f"[{index}] {step.source.value}: {truncated}{tool_part}{error_part}"


def _format_step_standard(index: int, step) -> str:
    """Step with truncated message and tool call summaries."""
    lines: list[str] = []
    message = _extract_text(step.message)
    truncated = _truncate(message, MAX_MESSAGE_CHARS_STANDARD)
    lines.append(f"[{index}] {step.source.value}: {truncated}")

    for tc in step.tool_calls:
        args_summary = _summarize_args(tc.arguments)
        lines.append(f"  -> {tc.function_name}({args_summary})")

    if step.observation:
        for result in step.observation.results:
            content = _extract_text(result.content)
            is_error = _is_error_content(content)
            if is_error:
                # Always include error output in full for friction detection
                lines.append(f"  <- ERROR: {_truncate(content, MAX_TOOL_OUTPUT_CHARS)}")
            else:
                lines.append(f"  <- {_truncate(content, MAX_MESSAGE_CHARS_BRIEF)}")

    return "\n".join(lines)


def _format_step_detailed(index: int, step) -> str:
    """Full step content with truncated tool outputs."""
    lines: list[str] = []
    message = _extract_text(step.message)
    truncated = _truncate(message, MAX_MESSAGE_CHARS_DETAILED)
    lines.append(f"[{index}] {step.source.value}:")
    if truncated:
        lines.append(truncated)

    for tc in step.tool_calls:
        args_str = str(tc.arguments) if tc.arguments else ""
        lines.append(f"  TOOL: {tc.function_name}")
        if args_str:
            lines.append(f"  ARGS: {_truncate(args_str, MAX_TOOL_OUTPUT_CHARS)}")

    if step.observation:
        for result in step.observation.results:
            content = _extract_text(result.content)
            lines.append(f"  OUTPUT: {_truncate(content, MAX_TOOL_OUTPUT_CHARS)}")

    return "\n".join(lines)


def _extract_text(content) -> str:
    """Extract plain text from a message or observation content field."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # ContentPart list — extract text parts
        text_parts = []
        for part in content:
            if hasattr(part, "text") and part.text:
                text_parts.append(part.text)
            elif hasattr(part, "type"):
                text_parts.append(f"[{part.type}]")
        return " ".join(text_parts)
    return str(content)


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, adding ellipsis if truncated."""
    text = text.strip().replace("\n", " ")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _summarize_args(arguments) -> str:
    """Create a compact summary of tool call arguments."""
    if arguments is None:
        return ""
    if isinstance(arguments, str):
        return _truncate(arguments, MAX_MESSAGE_CHARS_BRIEF)
    if isinstance(arguments, dict):
        parts = []
        for key, value in arguments.items():
            val_str = str(value)
            parts.append(f"{key}={_truncate(val_str, 40)}")
        return ", ".join(parts)
    return _truncate(str(arguments), MAX_MESSAGE_CHARS_BRIEF)


def _has_error_observation(step) -> bool:
    """Check whether a step has any error observations."""
    if not step.observation:
        return False
    return any(_is_error_content(_extract_text(r.content)) for r in step.observation.results)


def _is_error_content(content: str) -> bool:
    """Heuristic check for error content in tool output."""
    if not content:
        return False
    lower = content.lower()
    error_signals = ["error:", "traceback", "exception", "failed", "fatal", "errno"]
    return any(signal in lower for signal in error_signals)
