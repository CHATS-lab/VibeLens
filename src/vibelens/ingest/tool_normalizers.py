"""Tool call categorisation and summary extraction.

Maps tool names from all supported agent formats into a small set of
semantic categories, and extracts a one-line human-readable summary
from the tool's raw input arguments.
"""

TOOL_CATEGORY_MAP: dict[str, str] = {
    # File reading
    "Read": "file_read",
    "read_file": "file_read",
    "cat": "file_read",
    "Glob": "search",
    "glob": "search",
    "Grep": "search",
    "grep": "search",
    "find": "search",
    # File writing / editing
    "Edit": "file_write",
    "Write": "file_write",
    "write_file": "file_write",
    "NotebookEdit": "file_write",
    "MultiEdit": "file_write",
    "apply_patch": "file_write",
    "apply-patch": "file_write",
    # Shell / command execution
    "Bash": "shell",
    "bash": "shell",
    "shell": "shell",
    "execute_command": "shell",
    # Search
    "WebSearch": "web",
    "WebFetch": "web",
    "web_search": "web",
    # Agent delegation
    "Agent": "agent",
    "Skill": "agent",
    "TodoWrite": "agent",
    "TaskCreate": "agent",
    "TaskUpdate": "agent",
    # User interaction
    "AskUserQuestion": "other",
}

# Keys in tool input dicts that typically hold the most informative value,
# ordered by priority within each tool name.
_SUMMARY_KEYS: dict[str, list[str]] = {
    "Read": ["file_path"],
    "read_file": ["path", "file_path"],
    "Edit": ["file_path"],
    "Write": ["file_path"],
    "write_file": ["path", "file_path"],
    "NotebookEdit": ["notebook_path"],
    "Bash": ["command"],
    "bash": ["command"],
    "shell": ["command"],
    "execute_command": ["command"],
    "Glob": ["pattern"],
    "glob": ["pattern"],
    "Grep": ["pattern"],
    "grep": ["pattern"],
    "WebSearch": ["query"],
    "web_search": ["query"],
    "WebFetch": ["url"],
    "Agent": ["description", "prompt"],
}

# Limit summary length to avoid overly long strings in analytics displays.
_MAX_SUMMARY_LENGTH = 120


def categorize_tool(name: str) -> str:
    """Map a tool name to its semantic category.

    Args:
        name: Tool name as recorded in the agent output.

    Returns:
        Category string: file_read, file_write, shell, search, web, agent, or other.
    """
    return TOOL_CATEGORY_MAP.get(name, "other")


def summarize_tool_input(name: str, raw_input: dict | str | None) -> str:
    """Extract a short human-readable summary from tool input arguments.

    Args:
        name: Tool name.
        raw_input: Arguments dict, raw string, or None.

    Returns:
        Summary string (e.g. "src/main.py" for Read, "ls -la" for Bash).
    """
    if raw_input is None:
        return ""
    if isinstance(raw_input, str):
        return raw_input[:_MAX_SUMMARY_LENGTH]
    if not isinstance(raw_input, dict):
        return ""
    keys = _SUMMARY_KEYS.get(name, [])
    for key in keys:
        value = raw_input.get(key)
        if value and isinstance(value, str):
            return value[:_MAX_SUMMARY_LENGTH]
    # Fall back to first string value in the dict
    for value in raw_input.values():
        if isinstance(value, str) and value.strip():
            return value[:_MAX_SUMMARY_LENGTH]
    return ""


MAX_OUTPUT_DIGEST_LENGTH = 150


def summarize_tool_output(name: str, output: str | None, is_error: bool) -> str:
    """Generate a one-line digest of the tool output signal.

    Args:
        name: Tool name.
        output: Raw output string, or None.
        is_error: Whether the tool execution resulted in an error.

    Returns:
        Short digest string (e.g. "ERROR: file not found", "42 lines").
    """
    if output is None:
        return ""
    category = categorize_tool(name)
    if is_error:
        first_line = output.split("\n", 1)[0].strip()
        return f"ERROR: {first_line}"[:MAX_OUTPUT_DIGEST_LENGTH]
    return _digest_by_category(category, output)


def _digest_by_category(category: str, output: str) -> str:
    """Produce a category-appropriate digest of successful output.

    Args:
        category: Tool semantic category.
        output: Raw output string.

    Returns:
        Short digest string.
    """
    line_count = output.count("\n") + (1 if output and not output.endswith("\n") else 0)
    if category == "file_read":
        return f"{line_count} lines"
    if category == "search":
        match_count = max(line_count, 1)
        return f"{match_count} matches"
    if category == "file_write":
        return "applied"
    if category == "web":
        return f"fetched {len(output)} chars"
    if category == "shell":
        return f"{line_count} lines"
    return f"{line_count} lines"
