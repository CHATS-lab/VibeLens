"""Determinism tests for OpenClawParser fallback paths.

OpenClaw events normally carry an ``id`` and a ``session`` event provides
the session_id, so the fallback branches in the parser are rarely hit
on real data. These tests exercise the fallbacks directly so re-parsing
the same file always yields identical step_ids and session_id, which is
required for downstream caches and the trajectory ref graph.

Scoped narrowly to the deterministic_id refactor; broader coverage of
the parser lives in ``test_openclaw.py`` (PR #4).
"""

import json
from pathlib import Path

import pytest

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.openclaw import OpenClawParser


def _write_jsonl(path: Path, events: list[dict]) -> None:
    """Write a JSONL session file at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")


@pytest.fixture
def parser() -> OpenClawParser:
    """Fresh OpenClawParser per test."""
    return OpenClawParser()


def test_step_id_stable_when_event_id_missing(tmp_path: Path, parser: OpenClawParser) -> None:
    """Re-parsing produces the same step_ids when source events lack an ``id`` field."""
    session_file = tmp_path / "session.jsonl"
    _write_jsonl(
        session_file,
        [
            {"type": "session", "id": "sess-fallback", "cwd": "/proj"},
            # No "id" on either message — exercise the deterministic fallback.
            {
                "type": "message",
                "timestamp": "2025-01-15T10:00:00Z",
                "message": {"role": "user", "content": "hello"},
            },
            {
                "type": "message",
                "timestamp": "2025-01-15T10:00:05Z",
                "message": {
                    "role": "assistant",
                    "model": "claude-sonnet-4-5",
                    "content": [{"type": "text", "text": "hi"}],
                },
            },
        ],
    )

    ids_first = [step.step_id for step in parser.parse(session_file)[0].steps]
    ids_second = [step.step_id for step in parser.parse(session_file)[0].steps]

    assert ids_first == ids_second
    # Each fallback id is a fresh string, but must follow the deterministic_id shape.
    assert all(step_id.startswith("openclaw_msg-") for step_id in ids_first)
    print(f"stable fallback step_ids across re-parses: {ids_first}")


def test_step_id_uses_event_id_when_present(tmp_path: Path, parser: OpenClawParser) -> None:
    """When the event has an ``id``, it is used verbatim; the fallback never fires."""
    session_file = tmp_path / "session.jsonl"
    _write_jsonl(
        session_file,
        [
            {"type": "session", "id": "sess-with-ids", "cwd": "/proj"},
            {
                "type": "message",
                "id": "evt-user-1",
                "timestamp": "2025-01-15T10:00:00Z",
                "message": {"role": "user", "content": "hi"},
            },
            {
                "type": "message",
                "id": "evt-assistant-1",
                "timestamp": "2025-01-15T10:00:05Z",
                "message": {
                    "role": "assistant",
                    "model": "claude-sonnet-4-5",
                    "content": [{"type": "text", "text": "ok"}],
                },
            },
        ],
    )

    step_ids = [step.step_id for step in parser.parse(session_file)[0].steps]

    assert step_ids == ["evt-user-1", "evt-assistant-1"]
    print(f"event ids preserved: {step_ids}")


def test_session_id_stable_when_meta_and_stem_missing(parser: OpenClawParser) -> None:
    """The session_id last-resort fallback (no meta id, empty stem) is deterministic.

    pathlib never yields an empty stem for a real-world session file, so we
    exercise the branch by calling ``_extract_metadata`` directly with
    ``Path("/")`` (whose stem is empty). The point is to lock in that the
    parser doesn't generate a fresh random session_id when this branch fires.
    """
    raw = [{"type": "session", "cwd": "/proj"}]  # no "id" — meta lookup returns None.
    diagnostics = DiagnosticsCollector()

    sid_first = parser._extract_metadata(raw, Path("/"), diagnostics).session_id
    sid_second = parser._extract_metadata(raw, Path("/"), diagnostics).session_id

    assert sid_first == sid_second
    assert sid_first.startswith("openclaw_session-")
    print(f"stable fallback session_id: {sid_first}")
