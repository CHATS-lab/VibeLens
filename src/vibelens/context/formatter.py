"""Shared formatting helpers for context extraction.

Provides path shortening, argument summarization, and message truncation
used by all context extractor subclasses. Also provides build_metadata_block
for generating a shared session metadata header, and digest-shaping helpers
(batch concatenation and token-budget truncation) applied downstream.
"""

import os
from collections import Counter
from pathlib import PurePosixPath

from vibelens.context.params import ContextParams
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.context import SessionContextBatch
from vibelens.models.enums import StepSource
from vibelens.models.trajectories.trajectory import Trajectory
from vibelens.utils.content import truncate
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Max tokens of session context to include in a single LLM prompt.
# Consumed by truncate_digest_to_fit as the default total budget.
CONTEXT_TOKEN_BUDGET = 100_000

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


def build_metadata_block(
    main: Trajectory, session_index: int | None = None, include_details: bool = False
) -> str:
    """Build shared metadata header: session ID, project, creation time, last-activity time,
    and optional details.

    Args:
        main: The main (non-sub-agent) trajectory.
        session_index: Optional 0-based index within the analysis batch.
        include_details: If True, include STEPS and TOOLS lines.

    Returns:
        Multi-line metadata header string.
    """
    index_suffix = f" (index={session_index})" if session_index is not None else ""
    lines = [f"=== SESSION: {main.session_id}{index_suffix} ==="]

    if main.project_path:
        lines.append(f"PROJECT: {main.project_path}")

    if main.created_at:
        lines.append(f"STARTED: {main.created_at.strftime('%Y-%m-%d %H:%M')}")
    if main.updated_at and main.updated_at != main.created_at:
        lines.append(f"LAST_ACTIVE: {main.updated_at.strftime('%Y-%m-%d %H:%M')}")

    if include_details:
        user_count = sum(1 for s in main.steps if s.source == StepSource.USER)
        agent_count = sum(1 for s in main.steps if s.source == StepSource.AGENT)
        lines.append(f"STEPS: {len(main.steps)} (user={user_count}, agent={agent_count})")

        tool_counts: Counter[str] = Counter()
        for step in main.steps:
            for tc in step.tool_calls:
                tool_counts[tc.function_name] += 1
        if tool_counts:
            tool_parts = [f"{name}({count})" for name, count in tool_counts.most_common()]
            lines.append(f"TOOLS: {', '.join(tool_parts)}")

    return "\n".join(lines)


def format_user_prompt(message: str, params: ContextParams) -> str:
    """Truncate long user prompts to save tokens.

    Keeps the first head_chars and last tail_chars with a truncation marker.

    Args:
        message: User message text.
        params: Context extraction parameters.

    Returns:
        Truncated or original message string.
    """
    if len(message) <= params.user_prompt_max_chars:
        return message
    head = message[: params.user_prompt_head_chars]
    tail = message[-params.user_prompt_tail_chars :]
    return f"{head}\n[...truncated...]\n{tail}"


def format_agent_message(message: str, params: ContextParams) -> str:
    """Truncate long agent text messages to save tokens.

    Keeps the first head_chars and last tail_chars with a truncation marker.

    Args:
        message: Agent message text.
        params: Context extraction parameters.

    Returns:
        Truncated or original message string.
    """
    if len(message) <= params.agent_message_max_chars:
        return message
    head = message[: params.agent_message_head_chars]
    tail = message[-params.agent_message_tail_chars :]
    return f"{head}\n[...truncated...]\n{tail}"


def summarize_tool_args(function_name: str, arguments: object, params: ContextParams) -> str:
    """Summarize tool call arguments based on tool-specific rules.

    For known tools (Edit, Read, Bash, etc.), extracts only the key arguments
    defined in TOOL_ARG_KEYS. For unknown tools, falls back to checking common
    argument names (file_path, path, pattern, query, url, command) and shows
    the first match found.

    File paths are shortened based on params (shorten_home_prefix, path_max_segments).

    Args:
        function_name: Name of the tool being called.
        arguments: Tool arguments (dict, str, or None).
        params: Context extraction parameters.

    Returns:
        Compact argument summary string.
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
    """Format a single argument value with appropriate truncation and path shortening.

    Args:
        key: Argument key name.
        value: Raw argument value string.
        function_name: Tool name (used for Bash-specific truncation limit).
        params: Context extraction parameters.

    Returns:
        Formatted value string.
    """
    if key in _PATH_ARG_KEYS:
        value = shorten_path(value, params)
        return truncate(value, params.tool_arg_max_chars)
    if function_name == "Bash" and key == "command":
        return truncate(value, params.bash_command_max_chars)
    return truncate(value, params.tool_arg_max_chars)


def shorten_path(path_str: str, params: ContextParams) -> str:
    """Shorten a file path for display.

    Applies two transformations in order:
    1. Replace $HOME prefix with ~ (if shorten_home_prefix is True)
    2. Keep only the last N path segments (if path_max_segments > 0)

    Args:
        path_str: File path to shorten.
        params: Context extraction parameters.

    Returns:
        Shortened path string.
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


def format_context_batch(batch: SessionContextBatch) -> str:
    """Concatenate session context texts from a batch into a single digest string.

    Args:
        batch: SessionContextBatch containing extracted session contexts.

    Returns:
        Combined context text, or placeholder if empty.
    """
    if not batch.contexts:
        return "[no sessions]"
    return "\n\n".join(ctx.context_text for ctx in batch.contexts)


def truncate_digest_to_fit(
    digest: str,
    system_prompt: str,
    other_user_content: str,
    budget_tokens: int = CONTEXT_TOKEN_BUDGET,
) -> str:
    """Truncate digest so the total prompt stays within budget.

    Preserves the first and last portions of the digest, cutting from the middle.

    Args:
        digest: Session digest text.
        system_prompt: Rendered system prompt.
        other_user_content: Non-digest portion of the user prompt.
        budget_tokens: Maximum token budget for the full prompt.

    Returns:
        Possibly truncated digest string.
    """
    overhead_tokens = count_tokens(system_prompt) + count_tokens(other_user_content)
    digest_tokens = count_tokens(digest)
    available = budget_tokens - overhead_tokens
    logger.info(
        "Token budget: overhead=%d, digest=%d, available=%d, budget=%d",
        overhead_tokens,
        digest_tokens,
        available,
        budget_tokens,
    )
    if available <= 0:
        return "[digest truncated -- no token budget remaining]"
    if digest_tokens <= available:
        return digest

    total_chars = len(digest)
    target_chars = int(total_chars * (available / digest_tokens))
    head_chars = int(target_chars * 0.7)
    tail_chars = target_chars - head_chars

    head = digest[:head_chars]
    tail = digest[-tail_chars:] if tail_chars > 0 else ""
    truncated_count = digest_tokens - available
    logger.info(
        "Digest truncated: %d → %d tokens (%d removed)",
        digest_tokens,
        available,
        truncated_count,
    )
    return f"{head}\n\n[... {truncated_count} tokens truncated ...]\n\n{tail}"
