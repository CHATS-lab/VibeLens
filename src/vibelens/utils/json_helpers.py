"""JSON parsing and serialization helpers."""

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
