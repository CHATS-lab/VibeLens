"""Tests for fast_metrics — full and incremental scan parity."""

import json
from pathlib import Path

from vibelens.ingest.fast_metrics import (
    scan_session_metrics,
    scan_session_metrics_incremental,
)


def _write_session(path: Path, lines: list[dict]) -> None:
    """Append the given JSON dicts as a JSONL file."""
    with open(path, "a", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


def _user_line(text: str = "hi", ts: str = "2025-01-01T00:00:00Z") -> dict:
    return {
        "type": "user",
        "uuid": f"u-{text}",
        "timestamp": ts,
        "message": {"role": "user", "content": text},
    }


def _assistant_line(
    msg_id: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_create: int = 0,
    tool_uses: int = 0,
    model: str = "claude-test",
    ts: str = "2025-01-01T00:01:00Z",
) -> dict:
    content = [{"type": "text", "text": "ok"}]
    for i in range(tool_uses):
        content.append({"type": "tool_use", "id": f"tu-{msg_id}-{i}", "name": "Bash"})
    return {
        "type": "assistant",
        "uuid": f"a-{msg_id}",
        "timestamp": ts,
        "message": {
            "id": msg_id,
            "model": model,
            "content": content,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_create,
            },
        },
    }


def test_incremental_matches_full(tmp_path: Path):
    """An incremental scan resumed from the midpoint must match a fresh full scan."""
    f = tmp_path / "session.jsonl"
    _write_session(
        f,
        [
            _user_line("first"),
            _assistant_line("m1", input_tokens=100, output_tokens=10, tool_uses=1),
            _user_line("second"),
            _assistant_line("m2", input_tokens=50, output_tokens=5, cache_read=10),
        ],
    )
    midpoint = f.stat().st_size

    # Append more turns
    _write_session(
        f,
        [
            _user_line("third", ts="2025-01-01T00:02:00Z"),
            _assistant_line(
                "m3",
                input_tokens=200,
                output_tokens=20,
                cache_create=15,
                tool_uses=2,
                ts="2025-01-01T00:02:30Z",
            ),
        ],
    )

    full = scan_session_metrics(f)

    # Snapshot the file as it looked at the midpoint and run a full scan on it
    # — that's our "previous metrics" baseline for the incremental call.
    snapshot = tmp_path / "snapshot.jsonl"
    snapshot.write_bytes(f.read_bytes()[:midpoint])
    prev = scan_session_metrics(snapshot)
    assert prev is not None

    incremental = scan_session_metrics_incremental(f, midpoint, prev)
    assert incremental is not None

    # Token totals, tool counts, message counts should match full scan
    assert incremental["input_tokens"] == full["input_tokens"]
    assert incremental["output_tokens"] == full["output_tokens"]
    assert incremental["cache_read_tokens"] == full["cache_read_tokens"]
    assert incremental["cache_creation_tokens"] == full["cache_creation_tokens"]
    assert incremental["tool_call_count"] == full["tool_call_count"]
    assert incremental["message_count"] == full["message_count"]
    assert incremental["model"] == full["model"]
    # last_timestamp should advance to the appended portion
    assert incremental["last_timestamp"] == full["last_timestamp"]


def test_incremental_with_empty_append_is_noop(tmp_path: Path):
    """If nothing new follows the offset, prev metrics pass through unchanged."""
    f = tmp_path / "session.jsonl"
    _write_session(
        f,
        [
            _user_line("only"),
            _assistant_line("m1", input_tokens=100, output_tokens=10),
        ],
    )
    prev = scan_session_metrics(f)
    assert prev is not None
    end_offset = f.stat().st_size

    # Resume from end — no new bytes.
    incremental = scan_session_metrics_incremental(f, end_offset, prev)
    assert incremental == prev
