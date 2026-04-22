"""Unit tests for vibelens.ingest.fast_metrics scanner."""

import json
from pathlib import Path

from vibelens.ingest.fast_metrics import scan_session_metrics


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    """Write a list of dicts as a JSONL file."""
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")


def _user_entry(timestamp: str = "2025-01-15T10:00:00Z") -> dict:
    return {"type": "user", "timestamp": timestamp, "message": {"role": "user"}}


def _assistant_entry(
    msg_id: str,
    model: str = "claude-sonnet-4-5",
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read: int = 0,
    cache_creation: int = 0,
    tool_use_count: int = 0,
    timestamp: str = "2025-01-15T10:00:05Z",
) -> dict:
    content = [{"type": "tool_use", "id": f"tc-{i}"} for i in range(tool_use_count)]
    return {
        "type": "assistant",
        "timestamp": timestamp,
        "message": {
            "id": msg_id,
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_creation,
            },
            "content": content,
        },
    }


class TestBasicAccumulation:
    """Tests for correct token and count accumulation."""

    def test_single_exchange(self, tmp_path: Path):
        path = tmp_path / "session.jsonl"
        _write_jsonl(path, [
            _user_entry("2025-01-15T10:00:00Z"),
            _assistant_entry("msg-1", input_tokens=100, output_tokens=50,
                             timestamp="2025-01-15T10:00:05Z"),
        ])
        result = scan_session_metrics(path)
        assert result is not None
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert result["cache_read_tokens"] == 0
        assert result["cache_creation_tokens"] == 0
        assert result["tool_call_count"] == 0
        assert result["model"] == "claude-sonnet-4-5"
        assert result["message_count"] == 2

    def test_multiple_exchanges_accumulated(self, tmp_path: Path):
        path = tmp_path / "session.jsonl"
        _write_jsonl(path, [
            _user_entry("2025-01-15T10:00:00Z"),
            _assistant_entry("msg-1", input_tokens=100, output_tokens=50,
                             timestamp="2025-01-15T10:00:05Z"),
            _user_entry("2025-01-15T10:00:10Z"),
            _assistant_entry("msg-2", input_tokens=200, output_tokens=80,
                             timestamp="2025-01-15T10:00:15Z"),
        ])
        result = scan_session_metrics(path)
        assert result is not None
        assert result["input_tokens"] == 300
        assert result["output_tokens"] == 130

    def test_cache_tokens_accumulated(self, tmp_path: Path):
        path = tmp_path / "cache.jsonl"
        _write_jsonl(path, [
            _user_entry(),
            _assistant_entry("msg-1", input_tokens=100, cache_read=20, cache_creation=5,
                             timestamp="2025-01-15T10:00:05Z"),
        ])
        result = scan_session_metrics(path)
        assert result is not None
        # input_tokens includes cache_read (VibeLens convention)
        assert result["input_tokens"] == 120  # 100 + 20
        assert result["cache_read_tokens"] == 20
        assert result["cache_creation_tokens"] == 5

    def test_tool_call_count(self, tmp_path: Path):
        path = tmp_path / "tools.jsonl"
        _write_jsonl(path, [
            _user_entry(),
            _assistant_entry("msg-1", tool_use_count=3,
                             timestamp="2025-01-15T10:00:05Z"),
            _user_entry("2025-01-15T10:00:10Z"),
            _assistant_entry("msg-2", tool_use_count=2,
                             timestamp="2025-01-15T10:00:15Z"),
        ])
        result = scan_session_metrics(path)
        assert result is not None
        assert result["tool_call_count"] == 5


class TestDeduplication:
    """Tests for message-ID deduplication (streaming sends same ID multiple times)."""

    def test_duplicate_message_id_counted_once(self, tmp_path: Path):
        """Claude Code streams multiple JSONL lines per response with same msg ID.
        Each should be counted only once.
        """
        path = tmp_path / "dup.jsonl"
        # Same msg ID, same usage — represents streaming lines for one response
        entry = _assistant_entry("msg-same", input_tokens=100, output_tokens=50)
        _write_jsonl(path, [entry, entry, entry])
        result = scan_session_metrics(path)
        assert result is not None
        assert result["input_tokens"] == 100  # not 300
        assert result["output_tokens"] == 50   # not 150

    def test_different_ids_all_counted(self, tmp_path: Path):
        path = tmp_path / "unique.jsonl"
        _write_jsonl(path, [
            _assistant_entry("msg-A", input_tokens=10, output_tokens=5,
                             timestamp="2025-01-15T10:00:01Z"),
            _assistant_entry("msg-B", input_tokens=20, output_tokens=10,
                             timestamp="2025-01-15T10:00:02Z"),
        ])
        result = scan_session_metrics(path)
        assert result is not None
        assert result["input_tokens"] == 30
        assert result["output_tokens"] == 15


class TestTimestamps:
    """Tests for first/last timestamp tracking."""

    def test_timestamps_captured(self, tmp_path: Path):
        path = tmp_path / "ts.jsonl"
        _write_jsonl(path, [
            _user_entry("2025-01-15T10:00:00Z"),
            _assistant_entry("msg-1", timestamp="2025-01-15T10:00:05Z"),
            _user_entry("2025-01-15T10:01:00Z"),
            _assistant_entry("msg-2", timestamp="2025-01-15T10:01:30Z"),
        ])
        result = scan_session_metrics(path)
        assert result is not None
        assert result["first_timestamp"] == "2025-01-15T10:00:00Z"
        assert result["last_timestamp"] == "2025-01-15T10:01:30Z"

    def test_single_entry_timestamps(self, tmp_path: Path):
        path = tmp_path / "single.jsonl"
        _write_jsonl(path, [_user_entry("2025-03-10T09:00:00Z")])
        result = scan_session_metrics(path)
        assert result is not None
        assert result["first_timestamp"] == "2025-03-10T09:00:00Z"
        assert result["last_timestamp"] == "2025-03-10T09:00:00Z"


class TestModelExtraction:
    """Tests for model name extraction."""

    def test_first_model_wins(self, tmp_path: Path):
        """First non-placeholder model name is used; later different models ignored."""
        path = tmp_path / "models.jsonl"
        _write_jsonl(path, [
            _user_entry(),
            _assistant_entry("msg-1", model="claude-sonnet-4-5",
                             timestamp="2025-01-15T10:00:05Z"),
            _assistant_entry("msg-2", model="claude-opus-4-7",
                             timestamp="2025-01-15T10:00:10Z"),
        ])
        result = scan_session_metrics(path)
        assert result is not None
        assert result["model"] == "claude-sonnet-4-5"

    def test_placeholder_model_skipped(self, tmp_path: Path):
        """Model names starting with '<' are placeholders and ignored."""
        path = tmp_path / "placeholder.jsonl"
        entries = [
            _user_entry(),
        ]
        # Manually craft an assistant entry with a placeholder model
        placeholder_entry = {
            "type": "assistant",
            "timestamp": "2025-01-15T10:00:05Z",
            "message": {
                "id": "msg-p1",
                "model": "<placeholder>",
                "usage": {"input_tokens": 10, "output_tokens": 5},
                "content": [],
            },
        }
        real_entry = _assistant_entry("msg-real", model="claude-haiku-4-5",
                                      timestamp="2025-01-15T10:00:10Z")
        _write_jsonl(path, [entries[0], placeholder_entry, real_entry])
        result = scan_session_metrics(path)
        assert result is not None
        assert result["model"] == "claude-haiku-4-5"

    def test_no_model_in_session(self, tmp_path: Path):
        path = tmp_path / "no-model.jsonl"
        _write_jsonl(path, [_user_entry()])
        result = scan_session_metrics(path)
        assert result is not None
        assert result["model"] is None


class TestEdgeCases:
    """Tests for empty, missing, and malformed files."""

    def test_empty_file(self, tmp_path: Path):
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        result = scan_session_metrics(path)
        assert result is not None
        assert result["input_tokens"] == 0
        assert result["output_tokens"] == 0
        assert result["tool_call_count"] == 0
        assert result["model"] is None

    def test_missing_file_returns_none(self, tmp_path: Path):
        result = scan_session_metrics(tmp_path / "does-not-exist.jsonl")
        assert result is None

    def test_invalid_json_lines_skipped(self, tmp_path: Path):
        path = tmp_path / "mixed.jsonl"
        path.write_text(
            "\n".join([
                "{not valid",
                json.dumps(_user_entry("2025-01-15T10:00:00Z")),
                "also bad",
                json.dumps(_assistant_entry("msg-1", input_tokens=10,
                                            timestamp="2025-01-15T10:00:05Z")),
            ]),
            encoding="utf-8",
        )
        result = scan_session_metrics(path)
        assert result is not None
        assert result["input_tokens"] == 10

    def test_non_dict_entries_skipped(self, tmp_path: Path):
        path = tmp_path / "non-dict.jsonl"
        path.write_text(
            "\n".join([
                json.dumps([1, 2, 3]),
                json.dumps("just a string"),
                json.dumps(_user_entry()),
            ]),
            encoding="utf-8",
        )
        result = scan_session_metrics(path)
        assert result is not None
        assert result["message_count"] == 1

    def test_non_user_assistant_entries_ignored(self, tmp_path: Path):
        """Entries with type other than 'user'/'assistant' are ignored for counting."""
        path = tmp_path / "other-types.jsonl"
        _write_jsonl(path, [
            {"type": "system", "timestamp": "2025-01-15T10:00:00Z", "message": {}},
            {"type": "tool_result", "timestamp": "2025-01-15T10:00:01Z", "message": {}},
            _user_entry("2025-01-15T10:00:02Z"),
        ])
        result = scan_session_metrics(path)
        assert result is not None
        assert result["message_count"] == 1

    def test_none_usage_values_treated_as_zero(self, tmp_path: Path):
        """None token values in usage dict should not crash accumulation."""
        path = tmp_path / "null-usage.jsonl"
        entry = {
            "type": "assistant",
            "timestamp": "2025-01-15T10:00:05Z",
            "message": {
                "id": "msg-null",
                "model": "claude-sonnet-4-5",
                "usage": {
                    "input_tokens": None,
                    "output_tokens": None,
                    "cache_read_input_tokens": None,
                    "cache_creation_input_tokens": None,
                },
                "content": [],
            },
        }
        _write_jsonl(path, [_user_entry(), entry])
        result = scan_session_metrics(path)
        assert result is not None
        assert result["input_tokens"] == 0
        assert result["output_tokens"] == 0
