"""JSON parsing and serialization helpers."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


def safe_json_loads(text: str) -> dict | list | None:
    """Parse a JSON string, returning None on failure.

    Args:
        text: Raw JSON string.

    Returns:
        Parsed object, or None if the string is malformed.
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def load_json_file(path: Path) -> dict | list | None:
    """Read and parse a JSON file, returning None on failure.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed object, or None if reading or parsing fails.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load JSON from %s: %s", path, exc)
        return None


def serialize_model(model: BaseModel | None) -> str | None:
    """Serialize a Pydantic model to a JSON string.

    Args:
        model: Pydantic model instance, or None.

    Returns:
        JSON string, or None if model is None.
    """
    if model is None:
        return None
    return json.dumps(model.model_dump())


def serialize_model_list(models: list[Any]) -> str:
    """Serialize a list of Pydantic models to a JSON string.

    Args:
        models: List of Pydantic BaseModel instances.

    Returns:
        JSON string of the serialized list.
    """
    return json.dumps([m.model_dump() for m in models])


def coerce_to_string(value: str | list | dict | int | float | bool | None) -> str:
    """Coerce any content value to a plain string.

    Handles the polymorphic content fields found across agent formats:
    string pass-through, list of ``{text: ...}`` blocks concatenated,
    dict JSON-serialised, and primitives stringified.

    Args:
        value: Content in any observed shape.

    Returns:
        Plain string representation.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return extract_text_from_blocks(value)
    if isinstance(value, dict):
        return json.dumps(value)
    return str(value)


def coerce_to_list(value: str | list | dict | None) -> list:
    """Coerce a value to a list of content blocks.

    Args:
        value: String (wrapped as single text block), list (returned as-is),
               dict (wrapped as single-element list), or None (empty list).

    Returns:
        List of content blocks.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str):
        return [{"type": "text", "text": value}] if value else []
    return []


def extract_text_from_blocks(blocks: list) -> str:
    """Concatenate text from a list of content blocks.

    Handles dicts with ``text`` keys, bare strings, and silently skips
    non-text items.

    Args:
        blocks: List of content block dicts or strings.

    Returns:
        Concatenated text separated by newlines.
    """
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, str):
            if block:
                parts.append(block)
        elif isinstance(block, dict):
            text = block.get("text", "")
            if text and isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def coerce_json_field(value: str | dict | list | None) -> dict | list | None:
    """Unwrap one level of string-encoded JSON.

    Real-world exports sometimes double-encode dicts as JSON strings.
    This function detects string values that are valid JSON objects or
    arrays and decodes them.

    Args:
        value: A value that may be a JSON-encoded string, or already decoded.

    Returns:
        Decoded dict/list, or the original value if not string-encoded.
    """
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in ("{", "["):
        return None
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return None


def deterministic_id(namespace: str, *components: str) -> str:
    """Generate a repeatable identifier from a namespace and components.

    Uses SHA-256 of the concatenated parts, truncated to 24 hex chars
    with a namespace prefix for readability (e.g. ``msg-a1b2c3...``).
    Parsing the same file twice always yields the same IDs, enabling
    caching and deduplication.

    Args:
        namespace: Short prefix (e.g. "msg", "tc").
        *components: Strings hashed together to form the unique part.

    Returns:
        Deterministic identifier string.
    """
    raw = "|".join(components)
    hex_digest = hashlib.sha256(raw.encode()).hexdigest()[:24]
    return f"{namespace}-{hex_digest}"
