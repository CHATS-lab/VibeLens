"""Tests for lightweight compaction-based extraction."""
from pathlib import Path
from unittest.mock import MagicMock, patch

from vibelens.services.recommendation.extraction import (
    extract_lightweight_digest,
    _sample_sessions,
)


def test_extract_lightweight_digest_with_compaction(tmp_path):
    """Sessions with compaction agents produce summary-based signals."""
    # Create a fake compaction JSONL file
    session_dir = tmp_path / "projects" / "test" / "abc123" / "subagents"
    session_dir.mkdir(parents=True)
    compaction_file = session_dir / "agent-acompact-001.jsonl"
    # Write a minimal JSONL with an assistant message (the summary)
    import json

    lines = [
        json.dumps({
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Implemented auth system with JWT tokens and bcrypt hashing."}],
            },
        }),
    ]
    compaction_file.write_text("\n".join(lines))

    metadata = [
        {
            "session_id": "abc123",
            "project_path": "/home/user/myproject",
            "filepath": str(tmp_path / "projects" / "test" / "abc123.jsonl"),
            "agent_type": "claude_code",
            "model": "claude-sonnet-4-20250514",
            "total_tool_calls": 25,
            "duration_seconds": 600,
        },
    ]

    digest, session_count, signal_count = extract_lightweight_digest(metadata)

    assert session_count == 1
    assert signal_count == 1
    assert "abc123" in digest
    assert "auth system" in digest.lower() or "JWT" in digest


def test_extract_lightweight_digest_metadata_fallback(tmp_path):
    """Sessions without compaction use metadata-only signal."""
    metadata = [
        {
            "session_id": "def456",
            "project_path": "/home/user/other",
            "filepath": str(tmp_path / "nonexistent" / "def456.jsonl"),
            "agent_type": "codex",
            "model": "gpt-4o",
            "total_tool_calls": 10,
            "duration_seconds": 300,
        },
    ]

    digest, session_count, signal_count = extract_lightweight_digest(metadata)

    assert session_count == 1
    assert signal_count == 1
    assert "other" in digest
    assert "Tools: 10" in digest


def test_extract_lightweight_digest_empty():
    """Empty metadata list produces empty digest."""
    digest, session_count, signal_count = extract_lightweight_digest([])

    assert session_count == 0
    assert signal_count == 0
    assert digest == ""


def test_sample_sessions_under_budget():
    """Sessions under budget are returned unchanged."""
    sessions = [
        ("s1", "Short signal", "/project-a", "2026-01-01"),
        ("s2", "Another signal", "/project-b", "2026-01-02"),
    ]
    result = _sample_sessions(sessions, token_budget=80_000)
    assert len(result) == 2


def test_sample_sessions_over_budget():
    """Sampling reduces sessions when over budget."""
    # Create many sessions with large signals
    sessions = [
        (f"s{i}", "x" * 2000, f"/project-{i % 3}", f"2026-01-{i:02d}")
        for i in range(1, 101)
    ]
    result = _sample_sessions(sessions, token_budget=5_000)
    assert len(result) < 100
    # All three projects should still be represented
    project_ids = {sid.split("-")[-1] for sid, _ in result}
    print(f"Sampled {len(result)}/100 sessions")


def test_sample_sessions_diverse_projects():
    """Sampling prefers recent sessions and covers all projects."""
    sessions = []
    for proj in range(5):
        for i in range(20):
            sessions.append(
                (f"p{proj}-s{i}", f"Signal for project {proj}", f"/project-{proj}", f"2026-01-{i+1:02d}")
            )
    result = _sample_sessions(sessions, token_budget=3_000)
    # Should have sessions from multiple projects
    projects_seen = set()
    for sid, _ in result:
        proj_id = sid.split("-")[0]
        projects_seen.add(proj_id)
    assert len(projects_seen) >= 3, f"Only {len(projects_seen)} projects represented"
    print(f"Sampled {len(result)}/100 sessions across {len(projects_seen)} projects")
