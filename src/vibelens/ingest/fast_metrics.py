"""Fast JSONL metrics scanner for dashboard stats.

Extracts aggregate token counts, tool call counts, model name, and
duration from raw JSONL files without full Pydantic parsing.
Deduplicates assistant entries by message ID since Claude Code logs
streaming chunks of the same response on multiple lines.

:func:`scan_session_metrics_incremental` resumes from a saved byte
offset and merges into a previous metrics dict, used by the
partial-rebuild path for append-only updates.
"""

import json
from pathlib import Path

import orjson

from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# The cheap substring filter below skips ~40% of lines (progress,
# queue-operation, file-history-snapshot, etc.) without paying the
# cost of an orjson parse. orjson is fast but not free, and the
# JSONL files in question are 30-80 MB with thousands of lines each.
_USER_MARKER = b'"type":"user"'
_ASSISTANT_MARKER = b'"type":"assistant"'


def _empty_state() -> dict:
    """Initial accumulator state for a metrics scan."""
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "tool_call_count": 0,
        "model": None,
        "message_count": 0,
        "first_timestamp": None,
        "last_timestamp": None,
    }


def _scan_into(file_path: Path, state: dict, start_offset: int = 0) -> dict | None:
    """Mutate ``state`` with metrics from ``file_path`` starting at byte ``start_offset``.

    Returns ``state`` on success, ``None`` on read failure.
    """
    seen_message_ids: set[str] = set()
    try:
        with open(file_path, "rb") as fh:
            if start_offset:
                fh.seek(start_offset)
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                is_user = _USER_MARKER in line
                is_assistant = (not is_user) and _ASSISTANT_MARKER in line
                if not is_user and not is_assistant:
                    continue
                try:
                    entry = orjson.loads(line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(entry, dict):
                    continue

                timestamp = entry.get("timestamp")
                if timestamp and isinstance(timestamp, str):
                    if state["first_timestamp"] is None:
                        state["first_timestamp"] = timestamp
                    state["last_timestamp"] = timestamp

                if is_user:
                    state["message_count"] += 1
                    continue

                msg = entry.get("message")
                if not isinstance(msg, dict):
                    continue

                # Deduplicate by message ID — Claude Code logs multiple JSONL
                # lines per API response (streaming), each with the same usage.
                msg_id = msg.get("id")
                if msg_id:
                    if msg_id in seen_message_ids:
                        continue
                    seen_message_ids.add(msg_id)

                # Extract model name (first real one wins)
                if not state["model"]:
                    m = msg.get("model")
                    if m and isinstance(m, str) and not m.startswith("<"):
                        state["model"] = m

                # Accumulate usage/token data (values may be None).
                # VibeLens prompt_tokens = input_tokens + cache_read_input_tokens
                # (aligned with Harbor convention, see claude_code.py _parse_usage).
                usage = msg.get("usage")
                if isinstance(usage, dict):
                    state["message_count"] += 1
                    input_tok = usage.get("input_tokens") or 0
                    cache_read = usage.get("cache_read_input_tokens") or 0
                    state["input_tokens"] += input_tok + cache_read
                    state["output_tokens"] += usage.get("output_tokens") or 0
                    state["cache_read_tokens"] += cache_read
                    state["cache_creation_tokens"] += usage.get("cache_creation_input_tokens") or 0

                # Count tool_use blocks in content
                content = msg.get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            state["tool_call_count"] += 1
    except OSError:
        return None
    return state


def scan_session_metrics(file_path: Path) -> dict | None:
    """Extract aggregate metrics from a Claude Code JSONL session file.

    Scans line-by-line, extracting usage data from assistant messages
    and counting tool_use blocks. Deduplicates by message ID so each
    API response is counted only once.

    Args:
        file_path: Path to the session JSONL file.

    Returns:
        Dict with keys: input_tokens, output_tokens, cache_read_tokens,
        cache_creation_tokens, tool_call_count, model, message_count,
        duration, first_timestamp, last_timestamp. None on read failure.
    """
    return _scan_into(file_path, _empty_state())


def scan_session_metrics_incremental(file_path: Path, start_offset: int, prev: dict) -> dict | None:
    """Resume a metrics scan from ``start_offset`` and merge into ``prev``.

    Used by the partial-rebuild path: when a session file grew on disk,
    seek past the last-cached byte and accumulate only the new lines'
    metrics into the previous totals. ~300× cheaper than re-scanning
    the whole file for an active session.

    The de-duplication ``seen_message_ids`` set starts empty rather than
    being persisted, on the assumption that Claude Code's streaming
    chunks for one assistant message ID are emitted contiguously and
    therefore won't straddle the resume boundary. If they ever do, the
    only consequence is over-counting tokens for that one message.

    Args:
        file_path: Path to the session JSONL file.
        start_offset: Byte offset into the file where new content begins.
            Should be the file size at the time of the previous scan.
        prev: Dict returned by a previous :func:`scan_session_metrics`
            call (or another :func:`scan_session_metrics_incremental`).

    Returns:
        Updated metrics dict, or None on read failure.
    """
    state = dict(prev)
    return _scan_into(file_path, state, start_offset=start_offset)
