"""Tests for vibelens.ingest.fingerprint — format auto-detection."""

import json
from pathlib import Path

import pytest

from vibelens.ingest.fingerprint import (
    FormatMatch,
    fingerprint_file,
    parse_auto,
)


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    """Write a list of dicts as JSONL."""
    path.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n"
    )


# ─── Fixtures
@pytest.fixture
def claude_code_jsonl(tmp_path: Path) -> Path:
    """Create a minimal Claude Code JSONL file."""
    path = tmp_path / "session.jsonl"
    lines = [
        {
            "type": "user", "sessionId": "s1", "uuid": "u1",
            "message": {"role": "user", "content": "hi"},
        },
        {
            "type": "assistant", "sessionId": "s1", "uuid": "u2",
            "message": {"role": "assistant", "content": "hello"},
        },
    ]
    _write_jsonl(path, lines)
    return path


@pytest.fixture
def codex_jsonl(tmp_path: Path) -> Path:
    """Create a minimal Codex JSONL file."""
    path = tmp_path / "rollout.jsonl"
    lines = [
        {
            "type": "session_meta",
            "payload": {"session_id": "s1"},
            "timestamp": "2024-06-01T00:00:00Z",
        },
        {
            "type": "response_item",
            "payload": {"role": "assistant"},
            "timestamp": "2024-06-01T00:01:00Z",
        },
    ]
    _write_jsonl(path, lines)
    return path


@pytest.fixture
def dataclaw_jsonl(tmp_path: Path) -> Path:
    """Create a minimal Dataclaw JSONL file."""
    path = tmp_path / "conversations.jsonl"
    lines = [
        {
            "session_id": "s1",
            "messages": [{"role": "user", "content": "hi"}],
            "stats": {"turns": 1},
            "project": "/proj",
        },
    ]
    _write_jsonl(path, lines)
    return path


@pytest.fixture
def gemini_json(tmp_path: Path) -> Path:
    """Create a minimal Gemini JSON file."""
    path = tmp_path / "session.json"
    data = {
        "sessionId": "s1",
        "startTime": "2024-06-01T00:00:00Z",
        "messages": [{"type": "user", "text": "hi"}],
    }
    path.write_text(json.dumps(data))
    return path


# ─── fingerprint_file
class TestFingerprintFile:
    def test_claude_code_detection(self, claude_code_jsonl: Path):
        matches = fingerprint_file(claude_code_jsonl)
        assert len(matches) >= 1
        best = matches[0]
        assert best.format_name == "claude_code"
        assert best.confidence >= 0.5
        assert best.parser_class == "ClaudeCodeParser"
        print(f"  claude_code confidence: {best.confidence}")

    def test_codex_detection(self, codex_jsonl: Path):
        matches = fingerprint_file(codex_jsonl)
        assert len(matches) >= 1
        codex = [m for m in matches if m.format_name == "codex"]
        assert len(codex) >= 1
        assert codex[0].confidence >= 0.5
        print(f"  codex confidence: {codex[0].confidence}")

    def test_dataclaw_detection(self, dataclaw_jsonl: Path):
        matches = fingerprint_file(dataclaw_jsonl)
        assert len(matches) >= 1
        dc = [m for m in matches if m.format_name == "dataclaw"]
        assert len(dc) >= 1
        assert dc[0].confidence >= 0.5
        print(f"  dataclaw confidence: {dc[0].confidence}")

    def test_gemini_detection(self, gemini_json: Path):
        matches = fingerprint_file(gemini_json)
        assert len(matches) >= 1
        assert matches[0].format_name == "gemini"
        assert matches[0].confidence >= 0.5
        print(f"  gemini confidence: {matches[0].confidence}")

    def test_nonexistent_file(self, tmp_path: Path):
        matches = fingerprint_file(tmp_path / "missing.jsonl")
        assert matches == []

    def test_unsupported_extension(self, tmp_path: Path):
        path = tmp_path / "data.csv"
        path.write_text("a,b,c\n1,2,3\n")
        assert fingerprint_file(path) == []

    def test_empty_jsonl(self, tmp_path: Path):
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        assert fingerprint_file(path) == []

    def test_matches_sorted_by_confidence(self, claude_code_jsonl: Path):
        matches = fingerprint_file(claude_code_jsonl)
        if len(matches) > 1:
            for i in range(len(matches) - 1):
                assert matches[i].confidence >= matches[i + 1].confidence


# ─── parse_auto
class TestParseAuto:
    def test_auto_parses_claude_code(self, claude_code_jsonl: Path):
        results = parse_auto(claude_code_jsonl)
        assert len(results) >= 1
        summary, messages = results[0]
        assert len(messages) >= 1
        print(f"  auto-parsed {len(messages)} messages")

    def test_auto_raises_for_unknown(self, tmp_path: Path):
        path = tmp_path / "unknown.jsonl"
        path.write_text('{"random": "data"}\n')
        with pytest.raises(ValueError, match="Cannot auto-detect"):
            parse_auto(path)


# ─── FormatMatch model
class TestFormatMatch:
    def test_fields(self):
        fm = FormatMatch(
            format_name="claude_code",
            confidence=0.8,
            parser_class="ClaudeCodeParser",
        )
        assert fm.format_name == "claude_code"
        assert fm.confidence == 0.8
        assert fm.parser_class == "ClaudeCodeParser"
