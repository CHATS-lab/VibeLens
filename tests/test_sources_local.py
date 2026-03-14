"""Unit tests for vibelens.sources.local.LocalSource."""

import json
from pathlib import Path

import pytest

from vibelens.sources.local import LocalSource


@pytest.fixture
def claude_dir(tmp_path: Path) -> Path:
    """Create a minimal ~/.claude directory structure."""
    d = tmp_path / ".claude"
    d.mkdir()
    (d / "projects").mkdir()
    return d


@pytest.fixture
def project_dir(claude_dir: Path) -> Path:
    """Create a project subdirectory."""
    p = claude_dir / "projects" / "-Users-Test-MyProject"
    p.mkdir(parents=True)
    return p


def _write_history(claude_dir: Path, entries: list[dict]) -> None:
    with open(claude_dir / "history.jsonl", "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _write_session(path: Path, entries: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


HISTORY_ENTRY_A = {
    "sessionId": "sess-a",
    "display": "Fix the bug",
    "timestamp": 1707734674932,
    "project": "/Users/Test/MyProject",
}
HISTORY_ENTRY_B = {
    "sessionId": "sess-b",
    "display": "Add feature",
    "timestamp": 1707734680000,
    "project": "/Users/Test/MyProject",
}
HISTORY_ENTRY_GHOST = {
    "sessionId": "sess-ghost",
    "display": "Ghost session",
    "timestamp": 1707734690000,
    "project": "/Users/Test/OtherProject",
}

SESSION_A_MESSAGES = [
    {
        "type": "user",
        "uuid": "m1",
        "sessionId": "sess-a",
        "timestamp": 1707734674932,
        "message": {"role": "user", "content": "Fix the bug in login"},
    },
    {
        "type": "assistant",
        "uuid": "m2",
        "sessionId": "sess-a",
        "timestamp": 1707734680000,
        "message": {
            "role": "assistant",
            "content": "I'll fix that for you.",
            "model": "claude-sonnet-4-6",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
    },
]

SESSION_B_MESSAGES = [
    {
        "type": "user",
        "uuid": "m3",
        "sessionId": "sess-b",
        "timestamp": 1707734680000,
        "message": {"role": "user", "content": "Add dark mode"},
    },
]


class TestLocalSourceInit:
    """Test LocalSource initialization."""

    def test_source_type(self, claude_dir: Path):
        source = LocalSource(claude_dir)
        assert source.source_type == "local"

    def test_display_name(self, claude_dir: Path):
        source = LocalSource(claude_dir)
        assert str(claude_dir) in source.display_name


class TestListSessions:
    """Test LocalSource.list_sessions()."""

    def test_empty_directory(self, claude_dir: Path):
        source = LocalSource(claude_dir)
        assert source.list_sessions() == []

    def test_no_projects_directory(self, tmp_path: Path):
        bare_dir = tmp_path / "bare"
        bare_dir.mkdir()
        source = LocalSource(bare_dir)
        assert source.list_sessions() == []

    def test_returns_sessions_with_files(self, claude_dir: Path, project_dir: Path):
        _write_history(claude_dir, [HISTORY_ENTRY_A, HISTORY_ENTRY_B])
        _write_session(project_dir / "sess-a.jsonl", SESSION_A_MESSAGES)
        _write_session(project_dir / "sess-b.jsonl", SESSION_B_MESSAGES)

        source = LocalSource(claude_dir)
        sessions = source.list_sessions()
        assert len(sessions) == 2
        ids = {s.session_id for s in sessions}
        assert ids == {"sess-a", "sess-b"}

    def test_filters_ghost_records(self, claude_dir: Path, project_dir: Path):
        _write_history(claude_dir, [HISTORY_ENTRY_A, HISTORY_ENTRY_GHOST])
        _write_session(project_dir / "sess-a.jsonl", SESSION_A_MESSAGES)

        source = LocalSource(claude_dir)
        sessions = source.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].session_id == "sess-a"

    def test_pagination_limit(self, claude_dir: Path, project_dir: Path):
        _write_history(claude_dir, [HISTORY_ENTRY_A, HISTORY_ENTRY_B])
        _write_session(project_dir / "sess-a.jsonl", SESSION_A_MESSAGES)
        _write_session(project_dir / "sess-b.jsonl", SESSION_B_MESSAGES)

        source = LocalSource(claude_dir)
        sessions = source.list_sessions(limit=1)
        assert len(sessions) == 1

    def test_pagination_offset(self, claude_dir: Path, project_dir: Path):
        _write_history(claude_dir, [HISTORY_ENTRY_A, HISTORY_ENTRY_B])
        _write_session(project_dir / "sess-a.jsonl", SESSION_A_MESSAGES)
        _write_session(project_dir / "sess-b.jsonl", SESSION_B_MESSAGES)

        source = LocalSource(claude_dir)
        all_sessions = source.list_sessions(limit=100)
        offset_sessions = source.list_sessions(limit=100, offset=1)
        assert len(offset_sessions) == len(all_sessions) - 1

    def test_offset_beyond_range(self, claude_dir: Path, project_dir: Path):
        _write_history(claude_dir, [HISTORY_ENTRY_A])
        _write_session(project_dir / "sess-a.jsonl", SESSION_A_MESSAGES)

        source = LocalSource(claude_dir)
        sessions = source.list_sessions(offset=999)
        assert sessions == []

    def test_filter_by_project_name(self, claude_dir: Path, project_dir: Path):
        other_project = claude_dir / "projects" / "-Users-Test-OtherProject"
        other_project.mkdir()
        other_entry = {
            "sessionId": "sess-other",
            "display": "Other",
            "timestamp": 1707734680000,
            "project": "/Users/Test/OtherProject",
        }
        _write_history(claude_dir, [HISTORY_ENTRY_A, other_entry])
        _write_session(project_dir / "sess-a.jsonl", SESSION_A_MESSAGES)
        _write_session(other_project / "sess-other.jsonl", SESSION_B_MESSAGES)

        source = LocalSource(claude_dir)
        sessions = source.list_sessions(project_name="MyProject")
        assert len(sessions) == 1
        assert sessions[0].project_name == "MyProject"

    def test_filter_by_nonexistent_project(self, claude_dir: Path, project_dir: Path):
        _write_history(claude_dir, [HISTORY_ENTRY_A])
        _write_session(project_dir / "sess-a.jsonl", SESSION_A_MESSAGES)

        source = LocalSource(claude_dir)
        sessions = source.list_sessions(project_name="NoSuchProject")
        assert sessions == []

    def test_caching(self, claude_dir: Path, project_dir: Path):
        _write_history(claude_dir, [HISTORY_ENTRY_A])
        _write_session(project_dir / "sess-a.jsonl", SESSION_A_MESSAGES)

        source = LocalSource(claude_dir)
        source.list_sessions()
        assert source._sessions_cache is not None
        cached_ref = source._sessions_cache
        source.list_sessions()
        assert source._sessions_cache is cached_ref


class TestGetSession:
    """Test LocalSource.get_session()."""

    def test_returns_detail(self, claude_dir: Path, project_dir: Path):
        _write_history(claude_dir, [HISTORY_ENTRY_A])
        _write_session(project_dir / "sess-a.jsonl", SESSION_A_MESSAGES)

        source = LocalSource(claude_dir)
        detail = source.get_session("sess-a")
        assert detail is not None
        assert detail.summary.session_id == "sess-a"
        assert len(detail.messages) == 2

    def test_returns_none_for_missing(self, claude_dir: Path, project_dir: Path):
        _write_history(claude_dir, [HISTORY_ENTRY_A])
        _write_session(project_dir / "sess-a.jsonl", SESSION_A_MESSAGES)

        source = LocalSource(claude_dir)
        assert source.get_session("nonexistent") is None

    def test_returns_none_for_ghost(self, claude_dir: Path, project_dir: Path):
        _write_history(claude_dir, [HISTORY_ENTRY_GHOST])

        source = LocalSource(claude_dir)
        assert source.get_session("sess-ghost") is None

    def test_metadata_populated(self, claude_dir: Path, project_dir: Path):
        _write_history(claude_dir, [HISTORY_ENTRY_A])
        _write_session(project_dir / "sess-a.jsonl", SESSION_A_MESSAGES)

        source = LocalSource(claude_dir)
        detail = source.get_session("sess-a")
        assert detail.summary.message_count == 2
        assert "claude-sonnet-4-6" in detail.summary.models
        assert detail.summary.duration > 0

    def test_session_not_in_history_but_has_file(self, claude_dir: Path, project_dir: Path):
        """File exists on disk but has no history entry — still loadable via file index."""
        _write_history(claude_dir, [])
        _write_session(project_dir / "orphan.jsonl", SESSION_A_MESSAGES)

        source = LocalSource(claude_dir)
        detail = source.get_session("orphan")
        assert detail is not None
        assert detail.summary.session_id == "orphan"
        assert detail.summary.message_count == 2


class TestListProjects:
    """Test LocalSource.list_projects()."""

    def test_empty(self, claude_dir: Path):
        source = LocalSource(claude_dir)
        assert source.list_projects() == []

    def test_returns_unique_sorted(self, claude_dir: Path, project_dir: Path):
        other_project = claude_dir / "projects" / "-Users-Test-Alpha"
        other_project.mkdir()
        entry_alpha = {
            "sessionId": "sess-alpha",
            "display": "Alpha",
            "timestamp": 1707734680000,
            "project": "/Users/Test/Alpha",
        }
        _write_history(claude_dir, [HISTORY_ENTRY_A, HISTORY_ENTRY_B, entry_alpha])
        _write_session(project_dir / "sess-a.jsonl", SESSION_A_MESSAGES)
        _write_session(project_dir / "sess-b.jsonl", SESSION_B_MESSAGES)
        _write_session(other_project / "sess-alpha.jsonl", SESSION_B_MESSAGES)

        source = LocalSource(claude_dir)
        projects = source.list_projects()
        assert projects == ["Alpha", "MyProject"]

    def test_ghost_projects_excluded(self, claude_dir: Path, project_dir: Path):
        _write_history(claude_dir, [HISTORY_ENTRY_A, HISTORY_ENTRY_GHOST])
        _write_session(project_dir / "sess-a.jsonl", SESSION_A_MESSAGES)

        source = LocalSource(claude_dir)
        projects = source.list_projects()
        assert "OtherProject" not in projects


class TestBuildFileIndex:
    """Test LocalSource._build_file_index()."""

    def test_no_projects_dir(self, tmp_path: Path):
        source = LocalSource(tmp_path)
        source._build_file_index()
        assert source._file_index == {}

    def test_indexes_jsonl_files(self, claude_dir: Path, project_dir: Path):
        (project_dir / "sess-1.jsonl").write_text("")
        (project_dir / "sess-2.jsonl").write_text("")

        source = LocalSource(claude_dir)
        source._build_file_index()
        assert "sess-1" in source._file_index
        assert "sess-2" in source._file_index

    def test_ignores_non_jsonl_files(self, claude_dir: Path, project_dir: Path):
        (project_dir / "sess-1.jsonl").write_text("")
        (project_dir / "readme.txt").write_text("")
        (project_dir / "data.json").write_text("")

        source = LocalSource(claude_dir)
        source._build_file_index()
        assert len(source._file_index) == 1

    def test_multiple_project_dirs(self, claude_dir: Path, project_dir: Path):
        other = claude_dir / "projects" / "-Other"
        other.mkdir()
        (project_dir / "s1.jsonl").write_text("")
        (other / "s2.jsonl").write_text("")

        source = LocalSource(claude_dir)
        source._build_file_index()
        assert "s1" in source._file_index
        assert "s2" in source._file_index

    def test_ignores_non_directory_entries(self, claude_dir: Path, project_dir: Path):
        (claude_dir / "projects" / "some_file.txt").write_text("")
        (project_dir / "s1.jsonl").write_text("")

        source = LocalSource(claude_dir)
        source._build_file_index()
        assert len(source._file_index) == 1
