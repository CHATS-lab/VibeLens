"""Tests for vibelens.ingest.parallel — parallel multi-file parsing."""

import json
from pathlib import Path

from vibelens.ingest.parallel import BATCH_SIZE, parse_files_parallel


def _write_claude_session(path: Path, session_id: str) -> None:
    """Write a minimal Claude Code session JSONL file."""
    entries = [
        {
            "type": "user",
            "sessionId": session_id,
            "uuid": f"{session_id}-u1",
            "timestamp": 1700000000000,
            "message": {"role": "user", "content": "Hello"},
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "uuid": f"{session_id}-a1",
            "timestamp": 1700000001000,
            "message": {"role": "assistant", "content": "Hi there"},
        },
    ]
    path.write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n"
    )


# ─── parse_files_parallel
class TestParseFilesParallel:
    def test_single_file(self, tmp_path: Path):
        session_file = tmp_path / "s1.jsonl"
        _write_claude_session(session_file, "s1")
        results = parse_files_parallel("ClaudeCodeParser", [session_file])
        assert len(results) == 1
        summary, messages = results[0]
        assert len(messages) == 2
        print(f"  single file: {len(messages)} messages")

    def test_multiple_files(self, tmp_path: Path):
        files = []
        for i in range(5):
            path = tmp_path / f"s{i}.jsonl"
            _write_claude_session(path, f"s{i}")
            files.append(path)
        results = parse_files_parallel("ClaudeCodeParser", files)
        assert len(results) == 5
        total_msgs = sum(len(msgs) for _, msgs in results)
        assert total_msgs == 10
        print(f"  {len(results)} files, {total_msgs} messages")

    def test_empty_file_list(self):
        results = parse_files_parallel("ClaudeCodeParser", [])
        assert results == []

    def test_below_batch_size_uses_sequential(self, tmp_path: Path):
        """Files below BATCH_SIZE are parsed sequentially."""
        files = []
        count = min(3, BATCH_SIZE - 1)
        for i in range(count):
            path = tmp_path / f"s{i}.jsonl"
            _write_claude_session(path, f"s{i}")
            files.append(path)
        results = parse_files_parallel("ClaudeCodeParser", files)
        assert len(results) == count

    def test_invalid_file_skipped(self, tmp_path: Path):
        good = tmp_path / "good.jsonl"
        _write_claude_session(good, "s1")
        bad = tmp_path / "bad.jsonl"
        bad.write_text("NOT VALID JSON\n")
        results = parse_files_parallel(
            "ClaudeCodeParser", [good, bad]
        )
        assert len(results) >= 1
        print(f"  results with bad file: {len(results)}")

    def test_codex_parser_class(self, tmp_path: Path):
        """Verify CodexParser can be instantiated by name."""
        path = tmp_path / "rollout.jsonl"
        entry = {
            "type": "session_meta",
            "payload": {"session_id": "s1"},
            "timestamp": "2024-06-01T00:00:00Z",
        }
        path.write_text(json.dumps(entry) + "\n")
        results = parse_files_parallel("CodexParser", [path])
        assert isinstance(results, list)
