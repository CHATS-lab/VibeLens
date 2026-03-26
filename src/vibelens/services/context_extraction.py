"""Context extraction — compress trajectory groups into LLM-ready text.

Extracts compressed context from a session's trajectory group (main + sub-agents).
Compaction-aware: detects compaction sub-agents (flagged via ``extra["is_compaction_agent"]``)
and uses their summaries alongside the full step chronology.

Reusable by friction analysis, skill analysis, and other LLM-powered modules.
"""

from dataclasses import dataclass, field
from datetime import datetime

from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Trajectory
from vibelens.models.trajectories.step import Step
from vibelens.utils.log import get_logger
from vibelens.utils.text import extract_text, is_error_content, truncate

logger = get_logger(__name__)

BASH_COMMAND_MAX_CHARS = 80
ERROR_TRUNCATE_CHARS = 300

# Tool-specific argument keys to extract for summarization
TOOL_ARG_KEYS: dict[str, list[str]] = {
    "Write": ["file_path"],
    "Edit": ["file_path"],
    "Read": ["file_path"],
    "Bash": ["command"],
    "Glob": ["pattern", "path"],
    "Grep": ["pattern", "path"],
    "WebFetch": ["url"],
    "WebSearch": ["query"],
}


@dataclass
class SessionContext:
    """Compressed context for one session, ready for LLM consumption."""

    session_id: str
    project_path: str | None
    context_text: str
    char_count: int
    trajectory_group: list[Trajectory] = field(repr=False)
    last_trajectory_ref_id: str | None = None
    continued_trajectory_ref_id: str | None = None
    timestamp: datetime | None = None


def extract_session_context(trajectory_group: list[Trajectory]) -> SessionContext:
    """Extract compressed context from a session's trajectory group.

    Detects compaction sub-agents and adapts extraction strategy:
    - With compactions: compaction summaries + ALL steps chronologically
    - Without compactions: all steps with user messages, tool calls, and errors

    The compaction branch includes every step (not just post-compaction) so the
    LLM sees the full session timeline. Compaction summaries provide compressed
    context for the pre-compaction portion that may lack detailed tool info.

    Args:
        trajectory_group: All trajectories for one session (main + sub-agents).

    Returns:
        SessionContext with compressed text representation.
    """
    main = _find_main_trajectory(trajectory_group)
    compaction_agents = _find_compaction_agents(trajectory_group)

    if compaction_agents:
        context_text = _extract_with_compactions(main, compaction_agents)
    else:
        context_text = _extract_without_compactions(main)

    header = _build_header(main)
    full_text = f"{header}\n\n{context_text}"

    return SessionContext(
        session_id=main.session_id,
        project_path=main.project_path,
        context_text=full_text,
        char_count=len(full_text),
        trajectory_group=trajectory_group,
        last_trajectory_ref_id=(
            main.last_trajectory_ref.session_id if main.last_trajectory_ref else None
        ),
        continued_trajectory_ref_id=(
            main.continued_trajectory_ref.session_id if main.continued_trajectory_ref else None
        ),
        timestamp=main.timestamp,
    )


def _find_main_trajectory(trajectory_group: list[Trajectory]) -> Trajectory:
    """Find the main (non-sub-agent) trajectory in the group.

    The main trajectory is the one without a parent_trajectory_ref, meaning
    it was not spawned as a sub-agent. For single-trajectory groups (e.g.
    Dataclaw, Codex single-session), the first trajectory is returned as
    a safe fallback since it has no parent_ref by definition.
    """
    for t in trajectory_group:
        if t.parent_trajectory_ref is None:
            return t
    return trajectory_group[0]


def _find_compaction_agents(trajectory_group: list[Trajectory]) -> list[Trajectory]:
    """Find compaction sub-agents sorted by timestamp.

    Compaction agents are detected via the ``extra["is_compaction_agent"]`` flag
    set by parsers during ingestion. This decouples detection from any
    agent-specific session_id naming convention.

    Parser contract: parsers that encounter compaction sub-agents must set
    ``extra={"is_compaction_agent": True}`` on the Trajectory. Currently only
    the Claude Code parser produces compaction agents (``acompact-*`` files).
    """
    compaction = [t for t in trajectory_group if (t.extra or {}).get("is_compaction_agent")]
    compaction.sort(key=lambda t: t.timestamp or datetime.min)
    return compaction


def _build_header(main: Trajectory) -> str:
    """Build the session header block."""
    lines = [f"=== SESSION: {main.session_id} ==="]
    if main.project_path:
        lines.append(f"PROJECT: {main.project_path}")
    return "\n".join(lines)


def _extract_with_compactions(main: Trajectory, compaction_agents: list[Trajectory]) -> str:
    """Extract context for sessions WITH compaction sub-agents.

    Strategy:
    1. Compaction summaries — compressed context from each compaction agent
    2. ALL steps chronologically — the full session timeline via _format_steps_basic()

    Previous implementation had a separate "USER MESSAGES" section plus only
    post-compaction steps, which caused user messages after compaction to appear
    twice. This version includes all steps exactly once and lets compaction
    summaries provide compressed context for the pre-compaction portion.
    """
    parts: list[str] = []

    # Compaction summaries provide compressed context for pre-compaction history
    summaries = _extract_compaction_summaries(compaction_agents)
    for i, summary in enumerate(summaries, 1):
        parts.append(f"--- COMPACTION SUMMARY {i} ---")
        parts.append(summary)

    # All steps from the entire session — user messages, agent tool calls,
    # errors appear exactly once in chronological order
    activity = _format_steps_basic(main.steps)
    if activity:
        parts.append("--- ALL ACTIVITY ---")
        parts.append(activity)

    return "\n\n".join(parts)


def _extract_without_compactions(main: Trajectory) -> str:
    """Extract context for sessions WITHOUT compaction.

    Includes all user messages verbatim, agent steps with tool calls
    (function name + key args only), and error observations in full.
    """
    parts: list[str] = []
    for step in main.steps:
        formatted = _format_step_full(step)
        if formatted:
            parts.append(formatted)
    return "\n\n".join(parts)


def _extract_compaction_summaries(compaction_agents: list[Trajectory]) -> list[str]:
    """Extract summary text from compaction agent response steps.

    The compaction agent typically has step[0] as system/user prompt and
    step[1] as the agent's summary response.
    """
    summaries: list[str] = []
    for agent in compaction_agents:
        # Find the agent response step (usually step[1])
        for step in agent.steps:
            if step.source == StepSource.AGENT:
                summary = extract_text(step.message)
                if summary.strip():
                    summaries.append(summary.strip())
                break
    return summaries


def _format_step_full(step: Step) -> str:
    """Format a step with user messages verbatim, agent steps with tool info.

    Filtering logic:
    - USER steps: include full message text
    - AGENT steps: include only if they have tool calls or error observations.
      Agent-only text responses (no tools, no errors) are skipped to reduce noise.
    - SYSTEM steps: skipped entirely (internal prompts, not useful for analysis)

    Observations are scanned for error content (stderr, exception traces) which
    is included truncated. Non-error tool output is omitted to keep context compact.
    """
    lines: list[str] = []

    if step.source == StepSource.USER:
        message = extract_text(step.message)
        if message.strip():
            lines.append(f"[step_id={step.step_id}] USER: {message.strip()}")

    elif step.source == StepSource.AGENT:
        agent_lines = [f"[step_id={step.step_id}] AGENT:"]
        for tc in step.tool_calls:
            tool_summary = _summarize_tool_args(tc.function_name, tc.arguments)
            agent_lines.append(f"  TOOL: fn={tc.function_name} {tool_summary}")

        # Include error observations — Dataclaw trajectories may have no
        # observation at all, so the None check is required for compatibility
        if step.observation:
            for result in step.observation.results:
                content = extract_text(result.content)
                if is_error_content(content):
                    error_text = truncate(content, ERROR_TRUNCATE_CHARS)
                    agent_lines.append(f"  ERROR: {error_text}")

        # Only include agent step if it has tool calls or errors (len > 1
        # means something beyond the header line was added)
        if len(agent_lines) > 1:
            lines.extend(agent_lines)

    return "\n".join(lines)


def _format_steps_basic(steps: list[Step]) -> str:
    """Format a list of steps with basic info."""
    parts: list[str] = []
    for step in steps:
        formatted = _format_step_full(step)
        if formatted:
            parts.append(formatted)
    return "\n".join(parts)


def _summarize_tool_args(function_name: str, arguments) -> str:
    """Summarize tool call arguments based on tool-specific rules.

    For known tools (Edit, Read, Bash, etc.), extracts only the key arguments
    defined in TOOL_ARG_KEYS. For unknown tools, falls back to checking common
    argument names (file_path, path, pattern, query, url, command) and shows
    the first match found.

    Args:
        function_name: Name of the tool function.
        arguments: Tool call arguments (dict, str, or None).

    Returns:
        Compact argument summary string.
    """
    if arguments is None:
        return ""
    if not isinstance(arguments, dict):
        return truncate(str(arguments), BASH_COMMAND_MAX_CHARS)

    keys_to_show = TOOL_ARG_KEYS.get(function_name)
    if keys_to_show:
        parts = []
        for key in keys_to_show:
            value = arguments.get(key)
            if value is not None:
                val_str = str(value)
                if function_name == "Bash" and key == "command":
                    val_str = truncate(val_str, BASH_COMMAND_MAX_CHARS)
                parts.append(f"{key}={val_str}")
        return " ".join(parts) if parts else ""

    # Unknown tool: show first recognized key if any
    for key in ("file_path", "path", "pattern", "query", "url", "command"):
        if key in arguments:
            return f"{key}={truncate(str(arguments[key]), BASH_COMMAND_MAX_CHARS)}"
    return ""
