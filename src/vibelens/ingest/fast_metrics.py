"""Fast JSONL metrics scanner for dashboard stats.

Extracts aggregate token counts, tool call counts, model name, and
duration from raw JSONL files without full Pydantic parsing. Reads
each line as raw JSON and accumulates only the fields needed for
dashboard statistics.

Deduplicates assistant entries by message ID to avoid double-counting
when Claude Code logs multiple JSONL lines for the same API response.
"""

import json
from pathlib import Path

from vibelens.utils.log import get_logger

logger = get_logger(__name__)


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
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_creation = 0
    tool_call_count = 0
    model_name = None
    message_count = 0
    first_ts = None
    last_ts = None
    seen_message_ids: set[str] = set()

    try:
        with open(file_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(entry, dict):
                    continue

                entry_type = entry.get("type")
                timestamp = entry.get("timestamp")

                # Track timestamps for duration calculation
                if timestamp and isinstance(timestamp, str):
                    if first_ts is None:
                        first_ts = timestamp
                    last_ts = timestamp

                if entry_type not in ("user", "assistant"):
                    continue

                if entry_type == "user":
                    message_count += 1
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
                if not model_name:
                    m = msg.get("model")
                    if m and isinstance(m, str) and not m.startswith("<"):
                        model_name = m

                # Accumulate usage/token data (values may be None).
                # VibeLens prompt_tokens = input_tokens + cache_read_input_tokens
                # (aligned with Harbor convention, see claude_code.py _parse_usage).
                usage = msg.get("usage")
                if isinstance(usage, dict):
                    message_count += 1
                    input_tok = usage.get("input_tokens") or 0
                    cache_read = usage.get("cache_read_input_tokens") or 0
                    total_input += input_tok + cache_read
                    total_output += usage.get("output_tokens") or 0
                    total_cache_read += cache_read
                    total_cache_creation += usage.get("cache_creation_input_tokens") or 0

                # Count tool_use blocks in content
                content = msg.get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_call_count += 1

    except OSError:
        return None

    return {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cache_read_tokens": total_cache_read,
        "cache_creation_tokens": total_cache_creation,
        "tool_call_count": tool_call_count,
        "model": model_name,
        "message_count": message_count,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
    }
