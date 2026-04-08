"""Shared text helpers for digest and analysis modules.

Pure functions for extracting, truncating, and summarizing text content
from trajectory message and observation fields.
"""

DEFAULT_MAX_TOTAL_CHARS = 200
DEFAULT_MAX_VALUE_CHARS = 60
ERROR_SIGNALS = ("error:", "traceback", "exception", "failed", "fatal")


def extract_text(content) -> str:
    """Extract plain text from a message or observation content field.

    Handles str, list[ContentPart], None, and other types.

    Args:
        content: Raw content field (str, list, or None).

    Returns:
        Plain text representation.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if hasattr(part, "text") and part.text:
                text_parts.append(part.text)
            elif hasattr(part, "type"):
                text_parts.append(f"[{part.type}]")
        return " ".join(text_parts)
    return str(content)


def truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, collapsing whitespace and adding ellipsis.

    Args:
        text: Input text to truncate.
        max_chars: Maximum character length.

    Returns:
        Truncated text with ellipsis if it exceeded max_chars.
    """
    text = text.strip().replace("\n", " ")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def summarize_args(
    arguments,
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
    max_value_chars: int = DEFAULT_MAX_VALUE_CHARS,
) -> str:
    """Create a compact summary of tool call arguments.

    Args:
        arguments: Tool call arguments (dict, str, or None).
        max_total_chars: Max length for the entire summary string.
        max_value_chars: Max length for each individual value.

    Returns:
        Compact argument summary string.
    """
    if arguments is None:
        return ""
    if isinstance(arguments, str):
        return truncate(arguments, max_total_chars)
    if isinstance(arguments, dict):
        parts = []
        for key, value in arguments.items():
            val_str = str(value)
            parts.append(f"{key}={truncate(val_str, max_value_chars)}")
        return ", ".join(parts)
    return truncate(str(arguments), max_total_chars)


def is_error_content(content: str) -> bool:
    """Heuristic check for error content in tool output.

    Args:
        content: Text content to check.

    Returns:
        True if content contains error signals.
    """
    if not content:
        return False
    lower = content.lower()
    return any(signal in lower for signal in ERROR_SIGNALS)
