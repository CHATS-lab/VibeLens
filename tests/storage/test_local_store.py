"""Tests for LocalStore (read-only conversation storage backend)."""

import json
import tempfile
from pathlib import Path

import pytest

from vibelens.ingest.parsers.claude import ClaudeParser
from vibelens.models.enums import AgentType
from vibelens.storage.trajectory.local import LocalTrajectoryStore as LocalSource


@pytest.fixture
def test_settings(tmp_path):
    """Create test data dirs with temporary Claude directory."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()

    projects_dir = claude_dir / "projects"
    projects_dir.mkdir()

    test_project = projects_dir / "-Users-TestProject-Agent-Test"
    test_project.mkdir()

    data_dirs = {AgentType.CLAUDE: claude_dir}
    return data_dirs, claude_dir, test_project


@pytest.fixture
def sample_history(test_settings):
    """Create sample history.jsonl with test data."""
    _, claude_dir, test_project = test_settings

    history_file = claude_dir / "history.jsonl"
    sessions_data = [
        {
            "display": "How does caching work?",
            "pastedContents": {},
            "timestamp": 1707734674932,
            "project": "/Users/TestProject/Agent-Test",
            "sessionId": "session-001",
        },
        {
            "display": "Explain JWT authentication",
            "pastedContents": {},
            "timestamp": 1707734680000,
            "project": "/Users/TestProject/Agent-Test",
            "sessionId": "session-002",
        },
    ]

    with open(history_file, "w") as f:
        for data in sessions_data:
            f.write(json.dumps(data) + "\n")

    return sessions_data


@pytest.fixture
def sample_sessions(test_settings, sample_history):
    """Create sample session .jsonl files."""
    _, _, test_project = test_settings

    session_1_file = test_project / "session-001.jsonl"
    session_1_data = [
        {
            "type": "user",
            "uuid": "msg-001",
            "sessionId": "session-001",
            "timestamp": 1707734674932,
            "message": {"role": "user", "content": "How does caching work?"},
        },
        {
            "type": "assistant",
            "uuid": "msg-002",
            "sessionId": "session-001",
            "timestamp": 1707734680000,
            "message": {
                "role": "assistant",
                "model": "claude-opus-4-6",
                "content": [{"type": "text", "text": "Caching stores frequently accessed data..."}],
                "usage": {
                    "input_tokens": 50,
                    "output_tokens": 100,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
        },
    ]

    with open(session_1_file, "w") as f:
        for data in session_1_data:
            f.write(json.dumps(data) + "\n")

    session_2_file = test_project / "session-002.jsonl"
    session_2_data = [
        {
            "type": "user",
            "uuid": "msg-003",
            "sessionId": "session-002",
            "timestamp": 1707734685000,
            "message": {"role": "user", "content": "Explain JWT authentication"},
        },
        {
            "type": "assistant",
            "uuid": "msg-004",
            "sessionId": "session-002",
            "timestamp": 1707734690000,
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-4-6",
                "content": [
                    {"type": "text", "text": "Let me search for JWT documentation..."},
                    {
                        "type": "tool_use",
                        "id": "tool-001",
                        "name": "Read",
                        "input": {"file_path": "/tmp/jwt-guide.md"},
                        "caller": {"type": "direct"},
                    },
                ],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 200,
                    "cache_creation_input_tokens": 50,
                    "cache_read_input_tokens": 0,
                },
            },
        },
        {
            "type": "user",
            "uuid": "msg-005",
            "sessionId": "session-002",
            "timestamp": 1707734695000,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-001",
                        "content": "JWT is a stateless authentication mechanism...",
                        "is_error": False,
                    }
                ],
            },
        },
    ]

    with open(session_2_file, "w") as f:
        for data in session_2_data:
            f.write(json.dumps(data) + "\n")

    return {"session-001": session_1_data, "session-002": session_2_data}


class TestDataParsing:
    """Test session data parsing."""

    def test_local_source_loads_index(self, test_settings, sample_history):
        """Test LocalSource can load history index."""
        data_dirs, claude_dir, _ = test_settings
        source = LocalSource(data_dirs=data_dirs)

        summaries = source.list_metadata()
        assert len(summaries) == 0  # No sessions with files yet

    def test_local_source_with_session_files(self, test_settings, sample_history, sample_sessions):
        """Test LocalSource with actual session files."""
        data_dirs, claude_dir, _ = test_settings
        source = LocalSource(data_dirs=data_dirs)

        summaries = source.list_metadata()
        assert len(summaries) == 2
        assert all(s["session_id"] in ["session-001", "session-002"] for s in summaries)

    def test_get_trajectory_with_correct_metadata(
        self, test_settings, sample_history, sample_sessions
    ):
        """Test trajectory metadata is correctly computed."""
        data_dirs, claude_dir, _ = test_settings
        source = LocalSource(data_dirs=data_dirs)

        group = source.load("session-002")
        assert group is not None
        main_traj = group[0]
        assert main_traj.session_id == "session-002"
        # session-002 has 2 parsed steps (user + agent; relay message filtered)
        assert len(main_traj.steps) == 2
        assert main_traj.agent.model_name == "claude-sonnet-4-6"


class TestLocalStoreABC:
    """Test ABC methods on LocalStore."""

    def test_exists_known_session(self, test_settings, sample_history, sample_sessions):
        """exists() returns True for known sessions, False for unknown."""
        data_dirs, _, _ = test_settings
        source = LocalSource(data_dirs=data_dirs)

        assert source.exists("session-001") is True
        assert source.exists("session-002") is True
        assert source.exists("nonexistent") is False
        print("exists() correctly identifies known/unknown sessions")

    def test_session_count(self, test_settings, sample_history, sample_sessions):
        """session_count() matches len(list_metadata())."""
        data_dirs, _, _ = test_settings
        source = LocalSource(data_dirs=data_dirs)

        count = source.session_count()
        metadata_count = len(source.list_metadata())
        assert count == metadata_count == 2
        print(f"session_count() = {count}, matches list_metadata() length")

    def test_save_raises(self, test_settings):
        """save() raises NotImplementedError."""
        data_dirs, _, _ = test_settings
        source = LocalSource(data_dirs=data_dirs)

        with pytest.raises(NotImplementedError, match="read-only"):
            source.save([])
        print("save() correctly raises NotImplementedError")

    def test_get_metadata(self, test_settings, sample_history, sample_sessions):
        """get_metadata() returns summary dict for known session, None for unknown."""
        data_dirs, _, _ = test_settings
        source = LocalSource(data_dirs=data_dirs)

        meta = source.get_metadata("session-001")
        assert meta is not None
        assert meta["session_id"] == "session-001"

        assert source.get_metadata("nonexistent") is None
        print("get_metadata() correctly returns metadata or None")


class TestLocalStoreErrorHandling:
    """Test error handling for LocalStore."""

    def test_malformed_jsonl_line(self, test_settings):
        """Test handling of malformed JSONL data."""
        data_dirs, claude_dir, test_project = test_settings

        history_file = claude_dir / "history.jsonl"
        with open(history_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "display": "Test",
                        "timestamp": 1707734674932,
                        "project": "/Users/TestProject/Agent-Test",
                        "sessionId": "session-bad",
                    }
                )
                + "\n"
            )

        session_file = test_project / "session-bad.jsonl"
        with open(session_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "type": "user",
                        "uuid": "msg-1",
                        "sessionId": "session-bad",
                        "message": {"role": "user", "content": "test"},
                    }
                )
                + "\n"
            )
            f.write("INVALID JSON LINE\n")
            f.write(
                json.dumps(
                    {
                        "type": "assistant",
                        "uuid": "msg-2",
                        "sessionId": "session-bad",
                        "message": {"role": "assistant", "content": "response"},
                    }
                )
                + "\n"
            )

        source = LocalSource(data_dirs=data_dirs)

        # Should still parse valid lines
        group = source.load("session-bad")
        assert group is not None

    def test_empty_claude_directory(self):
        """Test behavior with empty Claude directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            empty_dirs = {AgentType.CLAUDE: base / ".claude"}
            source = LocalSource(data_dirs=empty_dirs)

            summaries = source.list_metadata()
            assert len(summaries) == 0


class TestLoadSnapshotPattern:
    """Test that load() snapshots index state to avoid races."""

    def test_load_uses_ensure_index_return_value(
        self, test_settings, sample_history, sample_sessions
    ):
        """load() passes metadata_cache to _enrich_refs, not self._metadata_cache."""
        data_dirs, _, _ = test_settings
        source = LocalSource(data_dirs=data_dirs)

        # Load a session to warm the index
        group = source.load("session-001")
        assert group is not None

        # Invalidate after _ensure_index_snapshot but before _enrich_refs — simulates race
        # If load() snapshots correctly, this should not crash
        original_ensure = source._ensure_index_snapshot

        def ensure_then_invalidate():
            result = original_ensure()
            source._metadata_cache = None
            source._index = {}
            return result

        source._ensure_index_snapshot = ensure_then_invalidate
        source._metadata_cache = None

        group = source.load("session-001")
        assert group is not None
        print("load() survived concurrent invalidation via snapshot pattern")


class TestCacheHitOrRebuild:
    """Test that _try_load_from_cache is binary: perfect hit or full rebuild."""

    def test_stale_file_triggers_partial_rebuild(
        self, test_settings, sample_history, sample_sessions
    ):
        """When one file changed, _try_load_from_cache uses the partial-rebuild path.

        The partial path returns True (cache was usable) while still re-parsing
        the single stale file. The full-rebuild fallback is reserved for missing
        or corrupt cache files, not stale entries.
        """
        data_dirs, _, test_project = test_settings
        source = LocalSource(data_dirs=data_dirs)

        # Build initial index and warm cache
        source.list_metadata()

        # Invalidate in-memory state
        source._metadata_cache = None
        source._index = {}
        source._discover_files()

        # Modify one file to make it stale
        session_file = test_project / "session-001.jsonl"
        session_file.write_text(session_file.read_text() + "\n")

        result = source._try_load_from_cache()
        assert result is True, "Stale files should trigger partial rebuild and return True"
        # Both sessions should still be in the index after partial rebuild.
        assert source._metadata_cache is not None
        assert "session-001" in source._metadata_cache
        assert "session-002" in source._metadata_cache
        print("Stale file correctly triggers partial rebuild (returns True)")


class TestParserResilience:
    """Test that parsers handle corrupt files gracefully."""

    def test_parse_file_handles_unicode_error(self, test_settings):
        """parse_file returns [] for files with non-UTF-8 bytes."""
        settings, _, test_project = test_settings
        corrupt_file = test_project / "corrupt.jsonl"
        corrupt_file.write_bytes(b"\x80\x81\x82 invalid utf-8 bytes")

        parser = ClaudeParser()
        result = parser.parse_file(corrupt_file)
        assert result == []
        print("parse_file returns [] for non-UTF-8 file")

    def test_parse_handles_all_unparseable_lines(self):
        """parse returns [] (not raises ValueError) when all lines are corrupt JSON."""
        corrupt_content = "not json at all\nalso not json\nstill not json\n"
        parser = ClaudeParser()
        result = parser.parse(corrupt_content, source_path="/fake/session.jsonl")
        assert result == []
        print("parse returns [] for fully corrupt content")
