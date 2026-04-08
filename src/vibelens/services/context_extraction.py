"""Context extraction — compress trajectory groups into LLM-ready text.

Extracts compressed context from a session's trajectory group (main + sub-agents).
Compaction-aware: detects compaction sub-agents (flagged via ``extra["is_compaction_agent"]``)
and uses their summaries alongside the full step chronology.

All truncation limits are controlled by ``ContextParams``. Three presets
(PRESET_CONCISE, PRESET_MEDIUM, PRESET_DETAIL) are available in ``context_params.py``.

Reusable by friction analysis, skill analysis, and other LLM-powered modules.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath

from vibelens.models.context import SessionContext
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Trajectory
from vibelens.models.trajectories.step import Step
from vibelens.services.context_params import PRESET_DETAIL, ContextParams
from vibelens.utils.log import get_logger
from vibelens.utils.text import extract_text, is_error_content, truncate

logger = get_logger(__name__)

# Maps tool names to the argument keys worth showing in context.
# Structural mapping — does not vary by ContextParams preset.
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

# Argument keys whose values are file system paths (eligible for shortening)
_PATH_ARG_KEYS = {"file_path", "path"}


@dataclass
class _IndexTracker:
    """Assigns sequential 0-based indices to steps during formatting."""

    _counter: int = 0
    index_to_real_id: dict[int, str] = field(default_factory=dict)

    def assign(self, real_id: str) -> int:
        """Assign the next sequential index to a real step ID."""
        idx = self._counter
        self.index_to_real_id[idx] = real_id
        self._counter += 1
        return idx


def extract_session_context(
    trajectory_group: list[Trajectory],
    params: ContextParams = PRESET_DETAIL,
    session_index: int | None = None,
) -> SessionContext:
    """Extract compressed context from a session's trajectory group.

    Detects compaction sub-agents and adapts extraction strategy:
    - With compactions: compaction summaries interleaved with steps chronologically
    - Without compactions: all steps with user messages, tool calls, and errors

    Steps use 0-indexed IDs via _IndexTracker for compact LLM prompts.
    The mapping from index → real UUID is stored in step_index2id.

    Args:
        trajectory_group: All trajectories for one session (main + sub-agents).
        params: Context extraction parameters controlling detail level.
        session_index: Optional 0-based index within the analysis batch.

    Returns:
        SessionContext with compressed text representation.
    """
    main = _find_main_trajectory(trajectory_group)
    compaction_agents = _find_compaction_agents(trajectory_group)
    tracker = _IndexTracker()

    if compaction_agents:
        context_text = _extract_with_compactions(main, compaction_agents, tracker, params)
    else:
        context_text = _extract_without_compactions(main, tracker, params)

    header = _build_header(main, params, session_index)
    full_text = f"{header}\n\n{context_text}"

    return SessionContext(
        session_id=main.session_id,
        project_path=main.project_path,
        context_text=full_text,
        trajectory_group=trajectory_group,
        prev_trajectory_ref_id=(
            main.prev_trajectory_ref.session_id if main.prev_trajectory_ref else None
        ),
        next_trajectory_ref_id=(
            main.next_trajectory_ref.session_id if main.next_trajectory_ref else None
        ),
        timestamp=main.timestamp,
        step_index2id=tracker.index_to_real_id,
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


def _build_header(main: Trajectory, params: ContextParams, session_index: int | None = None) -> str:
    """Build the session header block with optional path shortening."""
    index_suffix = f" (index={session_index})" if session_index is not None else ""
    lines = [f"=== SESSION: {main.session_id}{index_suffix} ==="]
    if main.project_path:
        display_path = _shorten_path(main.project_path, params)
        lines.append(f"PROJECT: {display_path}")
    return "\n".join(lines)


def _extract_with_compactions(
    main: Trajectory,
    compaction_agents: list[Trajectory],
    tracker: _IndexTracker,
    params: ContextParams,
) -> str:
    """Extract context for sessions WITH compaction sub-agents.

    Interleaves compaction summaries at their chronological position among steps.
    Each summary is inserted just before the first step whose timestamp exceeds
    the compaction boundary. Falls back to summaries-first if timestamps are unavailable.
    """
    boundaries = _build_compaction_boundaries(compaction_agents)
    parts: list[str] = []

    boundary_idx = 0
    summary_counter = 0

    for step in main.steps:
        while boundary_idx < len(boundaries):
            boundary_ts, summary_text = boundaries[boundary_idx]
            step_ts = step.timestamp

            if boundary_ts is None or step_ts is None:
                break

            if boundary_ts < step_ts:
                summary_counter += 1
                parts.append(f"--- COMPACTION SUMMARY {summary_counter} ---")
                parts.append(summary_text)
                boundary_idx += 1
            else:
                break

        formatted = _format_step(step, tracker, params)
        if formatted:
            parts.append(formatted)

    while boundary_idx < len(boundaries):
        _, summary_text = boundaries[boundary_idx]
        summary_counter += 1
        parts.append(f"--- COMPACTION SUMMARY {summary_counter} ---")
        parts.append(summary_text)
        boundary_idx += 1

    return "\n\n".join(parts)


def _extract_without_compactions(
    main: Trajectory, tracker: _IndexTracker, params: ContextParams
) -> str:
    """Extract context for sessions WITHOUT compaction.

    Includes user messages (truncated if long), agent steps with tool calls
    (function name + key args only), and error observations in full.
    """
    parts: list[str] = []
    for step in main.steps:
        formatted = _format_step(step, tracker, params)
        if formatted:
            parts.append(formatted)
    return "\n\n".join(parts)


def _build_compaction_boundaries(
    compaction_agents: list[Trajectory],
) -> list[tuple[datetime | None, str]]:
    """Build timestamped compaction summaries sorted by timestamp.

    Each compaction agent typically has step[0] as system/user prompt and
    step[1] as the agent's summary response. The agent's trajectory timestamp
    marks when the compaction occurred.

    Returns:
        Sorted list of (timestamp, summary_text) pairs.
    """
    boundaries: list[tuple[datetime | None, str]] = []
    for agent in compaction_agents:
        for step in agent.steps:
            if step.source == StepSource.AGENT:
                summary = extract_text(step.message)
                if summary.strip():
                    boundaries.append((agent.timestamp, summary.strip()))
                break
    boundaries.sort(key=lambda b: b[0] or datetime.min)
    return boundaries


def _format_step(step: Step, tracker: _IndexTracker, params: ContextParams) -> str:
    """Format a step with 0-indexed IDs, truncated user prompts, and tool info.

    Filtering logic:
    - USER steps: truncate long messages, assign 0-indexed step ID
    - AGENT steps: include text message (truncated), tool calls, and observations.
      Included if they have any content (message, tool calls, or observations).
    - SYSTEM steps: skipped entirely (internal prompts, not useful for analysis)

    Observations: errors are always included (truncated by error_truncate_chars).
    Non-error tool output is optionally included based on params.include_non_error_obs.
    """
    lines: list[str] = []

    if step.source == StepSource.USER:
        message = extract_text(step.message)
        if message.strip():
            idx = tracker.assign(step.step_id)
            truncated = _truncate_user_prompt(message.strip(), params)
            lines.append(f"[step_id={idx}] USER: {truncated}")

    elif step.source == StepSource.AGENT:
        # Agent's text message (reasoning, explanations, decisions)
        idx = tracker.assign(step.step_id)
        message = extract_text(step.message)
        truncated = _truncate_agent_message(message.strip(), params)
        agent_lines = [f"[step_id={idx}] AGENT: {truncated}"]

        for tc in step.tool_calls:
            tool_summary = _summarize_tool_args(tc.function_name, tc.arguments, params)
            agent_lines.append(f"  TOOL: fn={tc.function_name} {tool_summary}")

        # Scan observations for errors and optionally non-error output
        if step.observation:
            for result in step.observation.results:
                content = extract_text(result.content)
                if is_error_content(content):
                    error_text = truncate(content, params.error_truncate_chars)
                    agent_lines.append(f"  ERROR: {error_text}")
                elif params.include_non_error_obs and params.observation_max_chars > 0:
                    obs_text = truncate(content, params.observation_max_chars)
                    if obs_text.strip():
                        agent_lines.append(f"  RESULT: {obs_text}")

        # Include agent step if it has any content beyond the header
        if len(agent_lines) > 1:
            lines.extend(agent_lines)

    return "\n".join(lines)


def _truncate_user_prompt(message: str, params: ContextParams) -> str:
    """Truncate long user prompts to save tokens.

    Keeps the first head_chars and last tail_chars with a truncation marker.
    """
    if len(message) <= params.user_prompt_max_chars:
        return message
    head = message[: params.user_prompt_head_chars]
    tail = message[-params.user_prompt_tail_chars :]
    return f"{head}\n[...truncated...]\n{tail}"


def _truncate_agent_message(message: str, params: ContextParams) -> str:
    """Truncate long agent text messages to save tokens.

    Keeps the first head_chars and last tail_chars with a truncation marker.
    """
    if len(message) <= params.agent_message_max_chars:
        return message
    head = message[: params.agent_message_head_chars]
    tail = message[-params.agent_message_tail_chars :]
    return f"{head}\n[...truncated...]\n{tail}"


def _summarize_tool_args(function_name: str, arguments: object, params: ContextParams) -> str:
    """Summarize tool call arguments based on tool-specific rules.

    For known tools (Edit, Read, Bash, etc.), extracts only the key arguments
    defined in TOOL_ARG_KEYS. For unknown tools, falls back to checking common
    argument names (file_path, path, pattern, query, url, command) and shows
    the first match found.

    File paths are shortened based on params (shorten_home_prefix, path_max_segments).
    """
    if arguments is None:
        return ""
    if not isinstance(arguments, dict):
        return truncate(str(arguments), params.bash_command_max_chars)

    keys_to_show = TOOL_ARG_KEYS.get(function_name)
    if keys_to_show:
        parts = []
        for key in keys_to_show:
            value = arguments.get(key)
            if value is not None:
                val_str = _format_arg_value(key, str(value), function_name, params)
                parts.append(f"{key}={val_str}")
        return " ".join(parts) if parts else ""

    # Unknown tool: show first recognized key if any
    for key in ("file_path", "path", "pattern", "query", "url", "command"):
        if key in arguments:
            val_str = _format_arg_value(key, str(arguments[key]), function_name, params)
            return f"{key}={val_str}"
    return ""


def _format_arg_value(key: str, value: str, function_name: str, params: ContextParams) -> str:
    """Format a single argument value with appropriate truncation and path shortening."""
    if key in _PATH_ARG_KEYS:
        value = _shorten_path(value, params)
        return truncate(value, params.tool_arg_max_chars)
    if function_name == "Bash" and key == "command":
        return truncate(value, params.bash_command_max_chars)
    return truncate(value, params.tool_arg_max_chars)


def _shorten_path(path_str: str, params: ContextParams) -> str:
    """Shorten a file path for display.

    Applies two transformations in order:
    1. Replace $HOME prefix with ~ (if shorten_home_prefix is True)
    2. Keep only the last N path segments (if path_max_segments > 0)
    """
    if params.shorten_home_prefix:
        home = os.path.expanduser("~")
        if path_str.startswith(home):
            path_str = "~" + path_str[len(home) :]

    if params.path_max_segments > 0:
        parts = PurePosixPath(path_str).parts
        if len(parts) > params.path_max_segments:
            path_str = str(PurePosixPath(*parts[-params.path_max_segments :]))

    return path_str
