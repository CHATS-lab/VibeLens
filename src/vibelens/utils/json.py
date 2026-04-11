"""JSON parsing, serialization, and LLM output extraction helpers."""

import fcntl
import json
import re
from pathlib import Path

from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Greedy match: finds opening ```json fence and extends to the LAST closing ```.
# Greedy (.*) is required because the JSON value itself may contain embedded
# triple backticks (e.g. markdown code blocks inside a skill_md_content string).
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*)\n```", re.DOTALL)


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


def read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file and return parsed dicts, skipping invalid lines.

    Args:
        path: Path to the JSONL file.

    Returns:
        List of parsed JSON dicts.
    """
    results: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    results.append(json.loads(stripped))
                except json.JSONDecodeError:
                    logger.warning("Skipping invalid JSON line in %s", path.name)
    except OSError as exc:
        logger.warning("Cannot read JSONL file %s: %s", path, exc)
    return results


def locked_jsonl_append(path: Path, data: dict) -> None:
    """Append one JSON object as a line to a JSONL file under an exclusive lock.

    Uses ``fcntl.flock(LOCK_EX)`` so concurrent appenders within the same
    process (or across processes on the same host) serialize safely.

    Args:
        path: Path to the JSONL file (created if missing).
        data: Dictionary to serialize and append.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(data, default=str, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.write(line)
            fh.flush()
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def locked_jsonl_remove(path: Path, match_key: str, match_value: str) -> int:
    """Remove lines from a JSONL file where a key matches a value, under exclusive lock.

    Holds ``fcntl.flock(LOCK_EX)`` for the entire read-filter-write cycle
    so concurrent appenders block until the rewrite completes.  This
    prevents the classic lost-update race where an append between the
    read and the write is silently overwritten.

    Corrupt or unparseable lines are kept as-is.

    Args:
        path: Path to the JSONL file.
        match_key: JSON key to check (e.g. ``"analysis_id"``).
        match_value: Value to match for removal.

    Returns:
        Number of lines removed.
    """
    if not path.exists():
        return 0

    # Open r+b so we can read, seek, truncate, and write under one lock.
    # Binary mode avoids platform-specific newline translation issues
    # when truncating.
    with open(path, "r+b") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            raw = fh.read().decode("utf-8")
            lines = raw.splitlines()
            kept: list[str] = []
            removed = 0
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    if data.get(match_key) == match_value:
                        removed += 1
                        continue
                except json.JSONDecodeError:
                    pass
                kept.append(stripped)
            new_content = ("\n".join(kept) + "\n") if kept else ""
            fh.seek(0)
            fh.truncate()
            fh.write(new_content.encode("utf-8"))
            fh.flush()
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    return removed


def extract_json_from_llm_output(text: str) -> str:
    """Extract JSON from LLM output, stripping markdown code fences.

    Handles three cases:
    1. Plain JSON (no fences) — returned as-is after stripping.
    2. JSON wrapped in ``` fences at the start of output.
    3. Text preamble before a fenced JSON block
       (e.g. "Here is the output:\\n```json\\n{...}\\n```").

    Args:
        text: Raw LLM output text.

    Returns:
        Extracted JSON string.
    """
    stripped = text.strip()
    if not stripped:
        return stripped

    match = _CODE_FENCE_RE.search(stripped)
    if match:
        return match.group(1).strip()

    return stripped
