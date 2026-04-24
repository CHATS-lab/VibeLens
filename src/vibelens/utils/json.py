"""JSON parsing, serialization, and LLM output extraction helpers."""

import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any

from vibelens.utils.log import get_logger

logger = get_logger(__name__)


@contextmanager
def _exclusive_lock(fh: IO) -> Iterator[None]:
    """Hold an exclusive file lock for the ``with`` block.

    POSIX uses ``fcntl.flock``; Windows uses ``msvcrt.locking``. Both
    serialize concurrent appenders on the same host. On any other
    platform (none supported today) the lock is a best-effort no-op.
    """
    if os.name == "posix":
        import fcntl

        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    elif os.name == "nt":
        import msvcrt

        # Lock the first byte; msvcrt locks by byte range. Using 1 byte
        # is enough for cross-process serialization.
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        yield


# Greedy match: finds opening ```json fence and extends to the LAST closing ```.
# Greedy (.*) is required because the JSON value itself may contain embedded
# triple backticks (e.g. markdown code blocks inside a skill_md_content string).
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*)\n```", re.DOTALL)

# Valid JSON escape characters per RFC 8259 (the character after a backslash).
_VALID_JSON_ESCAPES = set('"\\/bfnrtu')
# Captures every backslash-escape in the JSON text so we can inspect the next char.
_INVALID_ESCAPE_RE = re.compile(r"\\(.)")


def atomic_write_json(path: Path, data: Any, *, indent: int | None = None) -> None:
    """Write JSON to ``path`` atomically via a sibling ``.tmp`` file.

    Creates parent directories. On success, ``path`` either contains the
    new payload or is unchanged (no partial write). Raises OSError on
    failure so callers can log or propagate as they prefer.

    Args:
        path: Destination file path.
        data: JSON-serializable object.
        indent: Passed through to ``json.dumps``. None for compact output.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=indent), encoding="utf-8")
    tmp_path.replace(path)


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

    Serializes concurrent appenders within the same process or across
    processes on the same host (``fcntl.flock`` on POSIX,
    ``msvcrt.locking`` on Windows).

    Args:
        path: Path to the JSONL file (created if missing).
        data: Dictionary to serialize and append.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(data, default=str, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as fh, _exclusive_lock(fh):
        fh.write(line)
        fh.flush()


def locked_jsonl_remove(path: Path, match_key: str, match_value: str) -> int:
    """Remove lines from a JSONL file where a key matches a value, under exclusive lock.

    Holds an exclusive file lock (``fcntl.flock`` on POSIX,
    ``msvcrt.locking`` on Windows) for the entire read-filter-write
    cycle so concurrent appenders block until the rewrite completes.
    This prevents the classic lost-update race where an append between
    the read and the write is silently overwritten.

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
    with open(path, "r+b") as fh, _exclusive_lock(fh):
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
    return removed


def repair_json_escapes(json_str: str) -> str:
    """Escape stray backslashes that LLMs sometimes emit inside JSON strings.

    LLMs occasionally emit ``\\n`` inside strings where they mean a literal
    newline-backslash-n, which is not a valid JSON escape. This replaces
    every invalid ``\\X`` with ``\\\\X`` so the string parses.

    Args:
        json_str: JSON text that failed strict parsing.

    Returns:
        JSON text with invalid escapes repaired to literal backslashes.
    """

    def _fix(match: re.Match) -> str:
        char = match.group(1)
        if char in _VALID_JSON_ESCAPES:
            return match.group(0)
        return "\\\\" + char

    return _INVALID_ESCAPE_RE.sub(_fix, json_str)


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
