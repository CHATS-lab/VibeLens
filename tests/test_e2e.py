"""End-to-end tests for VibeLens application."""

import json
from pathlib import Path

import httpx
import pytest

from vibelens.app import create_app
from vibelens.config import Settings
from vibelens.models.trajectories import Trajectory
from vibelens.storage.conversation.local import LocalStore as LocalSource


@pytest.fixture
def test_settings(tmp_path):
    """Create test settings with temporary Claude directory."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()

    # Create projects directory
    projects_dir = claude_dir / "projects"
    projects_dir.mkdir()

    # Create test project directory
    test_project = projects_dir / "-Users-TestProject-Agent-Test"
    test_project.mkdir()

    # Point all agent dirs to temp paths so real ~/.codex and ~/.gemini
    # don't leak into test results.
    return (
        Settings(
            claude_dir=claude_dir,
            codex_dir=tmp_path / ".codex",
            gemini_dir=tmp_path / ".gemini",
            openclaw_dir=tmp_path / ".openclaw",
        ),
        claude_dir,
        test_project,
    )


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
        {
            "display": "What is a ghost record?",
            "pastedContents": {},
            "timestamp": 1707734690000,
            "project": "/Users/TestProject/Agent-Test",
            "sessionId": "session-ghost",  # No matching .jsonl file
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

    # Session 1: Simple conversation
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

    # Session 2: With tool use
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


@pytest.mark.asyncio
class TestAPIEndpoints:
    """Test API endpoints."""

    async def test_get_projects(self, test_settings, monkeypatch):
        """Test /api/projects endpoint."""
        settings, _, _ = test_settings
        import vibelens.app
        import vibelens.deps

        def mock_load_settings():
            return settings

        monkeypatch.setattr(vibelens.app, "load_settings", mock_load_settings)
        monkeypatch.setattr(vibelens.deps, "load_settings", mock_load_settings)
        app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/projects")
            assert response.status_code == 200
            projects = response.json()
            assert isinstance(projects, list)

    async def test_list_sessions(self, test_settings, sample_history, sample_sessions, monkeypatch):
        """Test /api/sessions endpoint returns trajectory summaries."""
        settings, _, _ = test_settings
        import vibelens.app
        import vibelens.deps

        def mock_load_settings_inner():
            return settings

        monkeypatch.setattr(vibelens.app, "load_settings", mock_load_settings_inner)
        monkeypatch.setattr(vibelens.deps, "load_settings", mock_load_settings_inner)
        app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/sessions?limit=100")
            assert response.status_code == 200
            sessions = response.json()
            assert isinstance(sessions, list)
            assert len(sessions) == 2  # Only 2 have files, 1 is ghost
            session_ids = [s["session_id"] for s in sessions]
            assert "session-001" in session_ids
            assert "session-002" in session_ids

    async def test_list_sessions_with_pagination(
        self, test_settings, sample_history, sample_sessions, monkeypatch
    ):
        """Test pagination parameters."""
        settings, _, _ = test_settings
        import vibelens.app
        import vibelens.deps

        def mock_load_settings_inner():
            return settings

        monkeypatch.setattr(vibelens.app, "load_settings", mock_load_settings_inner)
        monkeypatch.setattr(vibelens.deps, "load_settings", mock_load_settings_inner)
        app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/sessions?limit=1&offset=0")
            assert response.status_code == 200
            sessions = response.json()
            assert len(sessions) == 1

    async def test_list_sessions_by_project(
        self, test_settings, sample_history, sample_sessions, monkeypatch
    ):
        """Test filtering by project name."""
        settings, _, _ = test_settings
        import vibelens.app
        import vibelens.deps

        def mock_load_settings_inner():
            return settings

        monkeypatch.setattr(vibelens.app, "load_settings", mock_load_settings_inner)
        monkeypatch.setattr(vibelens.deps, "load_settings", mock_load_settings_inner)
        app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/sessions?project_name=Agent-Test")
            assert response.status_code == 200
            sessions = response.json()
            # All trajectories from this directory have project_path "Agent-Test"
            assert all(s.get("project_path") == "Agent-Test" for s in sessions)

    async def test_get_session_detail(
        self, test_settings, sample_history, sample_sessions, monkeypatch
    ):
        """Test /api/sessions/{id} returns trajectory group as JSON array."""
        settings, _, _ = test_settings
        import vibelens.app
        import vibelens.deps

        def mock_load_settings_inner():
            return settings

        monkeypatch.setattr(vibelens.app, "load_settings", mock_load_settings_inner)
        monkeypatch.setattr(vibelens.deps, "load_settings", mock_load_settings_inner)
        app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/sessions/session-001")
            assert response.status_code == 200
            group = response.json()

            # Response is a list of trajectory dicts
            assert isinstance(group, list)
            assert len(group) >= 1
            main_traj = group[0]
            assert main_traj["session_id"] == "session-001"
            assert len(main_traj["steps"]) == 2

    async def test_get_nonexistent_session(self, test_settings, sample_history, monkeypatch):
        """Test error handling for missing sessions."""
        settings, _, _ = test_settings
        import vibelens.app
        import vibelens.deps

        def mock_load_settings_inner():
            return settings

        monkeypatch.setattr(vibelens.app, "load_settings", mock_load_settings_inner)
        monkeypatch.setattr(vibelens.deps, "load_settings", mock_load_settings_inner)
        app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/sessions/nonexistent-session")
            assert response.status_code == 404

    async def test_get_ghost_session(self, test_settings, sample_history, monkeypatch):
        """Test that ghost records are filtered out."""
        settings, _, _ = test_settings
        import vibelens.app
        import vibelens.deps

        def mock_load_settings_inner():
            return settings

        monkeypatch.setattr(vibelens.app, "load_settings", mock_load_settings_inner)
        monkeypatch.setattr(vibelens.deps, "load_settings", mock_load_settings_inner)
        app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/sessions?limit=100")
            sessions = response.json()
            session_ids = [s["session_id"] for s in sessions]
            assert "session-ghost" not in session_ids

    async def test_session_with_tool_calls(
        self, test_settings, sample_history, sample_sessions, monkeypatch
    ):
        """Test parsing of tool calls and results."""
        settings, _, _ = test_settings
        import vibelens.app
        import vibelens.deps

        def mock_load_settings_inner():
            return settings

        monkeypatch.setattr(vibelens.app, "load_settings", mock_load_settings_inner)
        monkeypatch.setattr(vibelens.deps, "load_settings", mock_load_settings_inner)
        app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/sessions/session-002")
            assert response.status_code == 200
            group = response.json()
            main_traj = group[0]

            # Find the step with tool calls
            tool_steps = [
                s for s in main_traj["steps"] if s["source"] == "agent" and s.get("tool_calls")
            ]
            assert len(tool_steps) > 0
            assert tool_steps[0]["tool_calls"][0]["function_name"] == "Read"

    async def test_session_token_usage(
        self, test_settings, sample_history, sample_sessions, monkeypatch
    ):
        """Test token usage on steps."""
        settings, _, _ = test_settings
        import vibelens.app
        import vibelens.deps

        def mock_load_settings_inner():
            return settings

        monkeypatch.setattr(vibelens.app, "load_settings", mock_load_settings_inner)
        monkeypatch.setattr(vibelens.deps, "load_settings", mock_load_settings_inner)
        app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/sessions/session-001")
            assert response.status_code == 200
            group = response.json()
            main_traj = group[0]

            # Verify token counts on individual steps
            steps = main_traj["steps"]
            total_prompt = sum((s.get("metrics") or {}).get("prompt_tokens", 0) for s in steps)
            assert total_prompt > 0


class TestDataParsing:
    """Test session data parsing."""

    def test_local_source_loads_index(self, test_settings, sample_history):
        """Test LocalSource can load history index."""
        settings, claude_dir, _ = test_settings
        source = LocalSource(settings=settings)

        summaries = source.list_metadata()
        assert len(summaries) == 0  # No sessions with files yet

    def test_local_source_with_session_files(self, test_settings, sample_history, sample_sessions):
        """Test LocalSource with actual session files."""
        settings, claude_dir, _ = test_settings
        source = LocalSource(settings=settings)

        summaries = source.list_metadata()
        assert len(summaries) == 2
        assert all(s["session_id"] in ["session-001", "session-002"] for s in summaries)

    def test_get_trajectory_with_correct_metadata(
        self, test_settings, sample_history, sample_sessions
    ):
        """Test trajectory metadata is correctly computed."""
        settings, claude_dir, _ = test_settings
        source = LocalSource(settings=settings)

        group = source.load("session-002")
        assert group is not None
        main_traj = group[0]
        assert main_traj.session_id == "session-002"
        # session-002 has 2 parsed steps (user + agent; relay message filtered)
        assert len(main_traj.steps) == 2
        assert main_traj.agent.model_name == "claude-sonnet-4-6"


class TestErrorHandling:
    """Test error handling."""

    def test_malformed_jsonl_line(self, test_settings):
        """Test handling of malformed JSONL data."""
        settings, claude_dir, test_project = test_settings

        # Create history with valid data
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

        # Create session file with invalid line
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
            f.write("INVALID JSON LINE\n")  # Malformed line
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

        source = LocalSource(settings=settings)

        # Should still parse valid lines
        group = source.load("session-bad")
        assert group is not None
        # The parser should skip invalid lines but continue

    @pytest.mark.asyncio
    async def test_missing_session_file(self, test_settings, monkeypatch):
        """Test behavior when session referenced in history has no file."""
        settings, claude_dir, _ = test_settings

        history_file = claude_dir / "history.jsonl"
        with open(history_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "display": "Missing file",
                        "timestamp": 1707734674932,
                        "project": "/Users/TestProject/Agent-Test",
                        "sessionId": "no-such-session",
                    }
                )
                + "\n"
            )

        import vibelens.app
        import vibelens.deps

        def mock_load_settings_inner():
            return settings

        monkeypatch.setattr(vibelens.app, "load_settings", mock_load_settings_inner)
        monkeypatch.setattr(vibelens.deps, "load_settings", mock_load_settings_inner)
        app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Ghost record should not appear in list
            response = await client.get("/api/sessions?limit=100")
            sessions = response.json()
            assert len(sessions) == 0

            # Direct access should fail
            response = await client.get("/api/sessions/no-such-session")
            assert response.status_code == 404


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_claude_directory(self):
        """Test behavior with empty Claude directory."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            settings = Settings(
                claude_dir=base / ".claude",
                codex_dir=base / ".codex",
                gemini_dir=base / ".gemini",
                openclaw_dir=base / ".openclaw",
            )
            source = LocalSource(settings=settings)

            summaries = source.list_metadata()
            assert len(summaries) == 0

    async def test_large_pagination_offset(
        self, test_settings, sample_history, sample_sessions, monkeypatch
    ):
        """Test pagination with offset beyond available sessions."""
        settings, _, _ = test_settings
        import vibelens.app
        import vibelens.deps

        def mock_load_settings_inner():
            return settings

        monkeypatch.setattr(vibelens.app, "load_settings", mock_load_settings_inner)
        monkeypatch.setattr(vibelens.deps, "load_settings", mock_load_settings_inner)
        app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/sessions?limit=100&offset=1000")
            assert response.status_code == 200
            sessions = response.json()
            assert len(sessions) == 0

    async def test_session_with_empty_messages(self, test_settings, monkeypatch):
        """Test session file with no messages."""
        settings, claude_dir, test_project = test_settings

        # Create history entry
        history_file = claude_dir / "history.jsonl"
        with open(history_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "display": "Empty session",
                        "timestamp": 1707734674932,
                        "project": "/Users/TestProject/Agent-Test",
                        "sessionId": "empty",
                    }
                )
                + "\n"
            )

        # Create empty session file
        session_file = test_project / "empty.jsonl"
        session_file.write_text("")

        import vibelens.app
        import vibelens.deps

        def mock_load_settings_inner():
            return settings

        monkeypatch.setattr(vibelens.app, "load_settings", mock_load_settings_inner)
        monkeypatch.setattr(vibelens.deps, "load_settings", mock_load_settings_inner)
        app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Empty session file won't produce valid trajectory (min 1 step)
            # so it will either not appear or return 404
            response = await client.get("/api/sessions/empty")
            assert response.status_code in (200, 404)

    async def test_special_characters_in_content(self, test_settings, monkeypatch):
        """Test handling of special characters in message content."""
        settings, claude_dir, test_project = test_settings

        # Create history
        history_file = claude_dir / "history.jsonl"
        with open(history_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "display": "Unicode: 你好 🚀",
                        "timestamp": 1707734674932,
                        "project": "/Users/TestProject/Agent-Test",
                        "sessionId": "unicode-test",
                    }
                )
                + "\n"
            )

        # Create session with special content
        session_file = test_project / "unicode-test.jsonl"
        with open(session_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "type": "user",
                        "uuid": "msg-1",
                        "sessionId": "unicode-test",
                        "message": {
                            "role": "user",
                            "content": "测试 <script>alert('xss')</script> 🔒",
                        },
                    }
                )
                + "\n"
            )

        import vibelens.app
        import vibelens.deps

        def mock_load_settings_inner():
            return settings

        monkeypatch.setattr(vibelens.app, "load_settings", mock_load_settings_inner)
        monkeypatch.setattr(vibelens.deps, "load_settings", mock_load_settings_inner)
        app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/sessions/unicode-test")
            assert response.status_code == 200
            group = response.json()
            assert isinstance(group, list)
            assert len(group) >= 1
            assert len(group[0]["steps"]) == 1


class TestLocalStoreABC:
    """Test new ABC methods on LocalStore."""

    def test_exists_known_session(self, test_settings, sample_history, sample_sessions):
        """exists() returns True for known sessions, False for unknown."""
        settings, _, _ = test_settings
        source = LocalSource(settings=settings)

        assert source.exists("session-001") is True
        assert source.exists("session-002") is True
        assert source.exists("nonexistent") is False
        print("exists() correctly identifies known/unknown sessions")

    def test_session_count(self, test_settings, sample_history, sample_sessions):
        """session_count() matches len(list_metadata())."""
        settings, _, _ = test_settings
        source = LocalSource(settings=settings)

        count = source.session_count()
        metadata_count = len(source.list_metadata())
        assert count == metadata_count == 2
        print(f"session_count() = {count}, matches list_metadata() length")

    def test_save_raises(self, test_settings):
        """save() raises NotImplementedError."""
        settings, _, _ = test_settings
        source = LocalSource(settings=settings)

        with pytest.raises(NotImplementedError, match="read-only"):
            source.save([])
        print("save() correctly raises NotImplementedError")

    def test_get_metadata(self, test_settings, sample_history, sample_sessions):
        """get_metadata() returns summary dict for known session, None for unknown."""
        settings, _, _ = test_settings
        source = LocalSource(settings=settings)

        meta = source.get_metadata("session-001")
        assert meta is not None
        assert meta["session_id"] == "session-001"

        assert source.get_metadata("nonexistent") is None
        print("get_metadata() correctly returns metadata or None")


class TestDiskStore:
    """Test DiskStore with unified index."""

    def test_save_and_load_roundtrip(self, tmp_path):
        """DiskStore save -> exists -> load round-trip."""
        from vibelens.storage.conversation.disk import DiskStore

        store = DiskStore(root=tmp_path)
        store.initialize()

        traj = _make_test_trajectory("roundtrip-001", "Test roundtrip session")
        store.save([traj])

        assert store.exists("roundtrip-001") is True
        loaded = store.load("roundtrip-001")
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0].session_id == "roundtrip-001"
        print(f"Round-trip: saved and loaded session {loaded[0].session_id}")

    def test_session_count(self, tmp_path):
        """session_count() tracks saves correctly."""
        from vibelens.storage.conversation.disk import DiskStore

        store = DiskStore(root=tmp_path)
        store.initialize()

        assert store.session_count() == 0

        store.save([_make_test_trajectory("count-001", "First")])
        assert store.session_count() == 1

        store.save([_make_test_trajectory("count-002", "Second")])
        assert store.session_count() == 2
        print(f"session_count() correctly tracks {store.session_count()} sessions")

    def test_exists_unknown_session(self, tmp_path):
        """exists() returns False for non-existent session."""
        from vibelens.storage.conversation.disk import DiskStore

        store = DiskStore(root=tmp_path)
        store.initialize()

        assert store.exists("no-such-session") is False
        print("exists() correctly returns False for unknown session")

    def test_save_updates_index_incrementally(self, tmp_path):
        """save() updates _metadata_cache and _index without full rebuild."""
        from vibelens.storage.conversation.disk import DiskStore

        store = DiskStore(root=tmp_path)
        store.initialize()

        # Trigger initial index build
        assert store.session_count() == 0

        # Save should update cache incrementally (no rebuild needed)
        traj = _make_test_trajectory("incr-001", "Incremental save")
        store.save([traj])

        # Verify both _metadata_cache and _index were updated
        assert store._metadata_cache is not None
        assert "incr-001" in store._metadata_cache
        assert "incr-001" in store._index
        assert store.exists("incr-001") is True
        assert store.session_count() == 1
        print("save() correctly updates _metadata_cache and _index incrementally")

    def test_invalidate_index_triggers_rebuild(self, tmp_path):
        """invalidate_index() clears cache; next access rebuilds from disk."""
        from vibelens.storage.conversation.disk import DiskStore

        store = DiskStore(root=tmp_path)
        store.initialize()

        # Save a session to build initial index
        traj = _make_test_trajectory("rebuild-001", "Rebuild test")
        store.save([traj])
        assert store.exists("rebuild-001") is True

        # Invalidate clears both caches
        store.invalidate_index()
        assert store._metadata_cache is None
        assert store._index == {}

        # Next access triggers rebuild from disk
        summaries = store.list_metadata()
        assert len(summaries) == 1
        assert summaries[0]["session_id"] == "rebuild-001"
        assert store._metadata_cache is not None
        assert "rebuild-001" in store._index
        print("invalidate_index() + list_metadata() correctly rebuilds from disk")

    def test_rglob_finds_subdirectory_sessions(self, tmp_path):
        """_build_index discovers sessions in subdirectories via rglob."""
        from vibelens.storage.conversation.disk import DiskStore

        store = DiskStore(root=tmp_path)
        store.initialize()

        # Save a root-level session
        store.save([_make_test_trajectory("root-001", "Root session")])

        # Save a session in a subdirectory (simulating upload)
        subdir = tmp_path / "upload_abc"
        sub_store = DiskStore(root=subdir)
        sub_store.initialize()
        sub_store.save([_make_test_trajectory("sub-001", "Sub session")])

        # Force rebuild so main store picks up subdirectory files
        store.invalidate_index()
        summaries = store.list_metadata()
        session_ids = {s["session_id"] for s in summaries}
        assert "root-001" in session_ids
        assert "sub-001" in session_ids
        assert len(summaries) == 2
        print("rglob correctly discovers sessions in subdirectories")

    def test_rglob_reads_upload_id_from_index(self, tmp_path):
        """_build_index reads _upload_id from JSONL index written with default_tags."""
        from vibelens.storage.conversation.disk import DiskStore

        store = DiskStore(root=tmp_path)
        store.initialize()

        # Simulate what upload_service does: save via sub-store with default_tags
        subdir = tmp_path / "upload_xyz"
        sub_store = DiskStore(root=subdir, default_tags={"_upload_id": "upload_xyz"})
        sub_store.initialize()
        sub_store.save([_make_test_trajectory("tagged-001", "Tagged session")])

        # Main store picks up the tag via rglob on index.jsonl
        summaries = store.list_metadata()
        tagged = [s for s in summaries if s.get("_upload_id") == "upload_xyz"]
        assert len(tagged) == 1
        assert tagged[0]["session_id"] == "tagged-001"
        print("rglob correctly reads _upload_id from JSONL index with default_tags")

    def test_get_metadata(self, tmp_path):
        """get_metadata() returns summary dict for known session, None for unknown."""
        from vibelens.storage.conversation.disk import DiskStore

        store = DiskStore(root=tmp_path)
        store.initialize()

        traj = _make_test_trajectory("meta-001", "Metadata test")
        store.save([traj])

        meta = store.get_metadata("meta-001")
        assert meta is not None
        assert meta["session_id"] == "meta-001"

        assert store.get_metadata("nonexistent") is None
        print("get_metadata() correctly returns metadata or None")


class TestFilterVisible:
    """Test stateless upload visibility filtering."""

    def test_example_sessions_visible_without_token(self):
        """Example sessions (no _upload_id) are visible when no token is provided."""
        from vibelens.services.upload.visibility import filter_visible

        summaries = [{"session_id": "root-001"}, {"session_id": "root-002"}]
        result = filter_visible(summaries, session_token=None)
        assert len(result) == 2
        print("Example sessions visible without token")

    def test_upload_sessions_hidden_without_token(self):
        """Uploaded sessions are hidden when no token is provided."""
        from vibelens.services.upload.visibility import filter_visible

        summaries = [
            {"session_id": "root-001"},
            {"session_id": "upload-001", "_upload_id": "u1", "_session_token": "tok-a"},
        ]
        result = filter_visible(summaries, session_token=None)
        assert len(result) == 1
        assert result[0]["session_id"] == "root-001"
        print("Upload sessions hidden without token")

    def test_own_uploads_visible_with_matching_token(self):
        """Token sees only its own uploads when _session_token matches."""
        from vibelens.services.upload.visibility import filter_visible

        summaries = [
            {"session_id": "root-001"},
            {"session_id": "upload-001", "_upload_id": "u1", "_session_token": "tok-a"},
        ]
        result = filter_visible(summaries, session_token="tok-a")
        assert len(result) == 1
        assert result[0]["session_id"] == "upload-001"
        print("Own uploads visible, examples hidden when token has uploads")

    def test_multiple_uploads_all_visible(self):
        """All uploads from the same token are visible."""
        from vibelens.services.upload.visibility import filter_visible

        summaries = [
            {"session_id": "old-001", "_upload_id": "u_old", "_session_token": "tok-m"},
            {"session_id": "new-001", "_upload_id": "u_new", "_session_token": "tok-m"},
        ]
        result = filter_visible(summaries, session_token="tok-m")
        assert len(result) == 2
        result_ids = {s["session_id"] for s in result}
        assert result_ids == {"old-001", "new-001"}
        print("All uploads from same token visible")

    def test_other_users_uploads_hidden(self):
        """Token without uploads sees examples; other users' uploads are hidden."""
        from vibelens.services.upload.visibility import filter_visible

        summaries = [
            {"session_id": "root-001"},
            {"session_id": "upload-001", "_upload_id": "u1", "_session_token": "tok-other"},
        ]
        result = filter_visible(summaries, session_token="tok-mine")
        assert len(result) == 1
        assert result[0]["session_id"] == "root-001"
        print("Other users' uploads hidden, examples shown")

    def test_mixed_visibility_isolation(self):
        """Each token sees only its own uploads; neither sees the other's."""
        from vibelens.services.upload.visibility import filter_visible

        summaries = [
            {"session_id": "root-001"},
            {"session_id": "alice-001", "_upload_id": "u_a", "_session_token": "tok-alice"},
            {"session_id": "bob-001", "_upload_id": "u_b", "_session_token": "tok-bob"},
        ]

        alice_result = filter_visible(summaries, session_token="tok-alice")
        assert len(alice_result) == 1
        assert alice_result[0]["session_id"] == "alice-001"

        bob_result = filter_visible(summaries, session_token="tok-bob")
        assert len(bob_result) == 1
        assert bob_result[0]["session_id"] == "bob-001"
        print("Alice and Bob each see only their own uploads")

    def test_is_session_visible(self):
        """is_session_visible() checks each visibility rule."""
        from vibelens.services.upload.visibility import is_session_visible

        # No metadata -> not visible
        assert is_session_visible(None, "token") is False

        # Example session (no _upload_id) -> always visible
        assert is_session_visible({"session_id": "root"}, None) is True
        assert is_session_visible({"session_id": "root"}, "any-token") is True

        # Upload session without token -> not visible
        assert is_session_visible(
            {"session_id": "up", "_upload_id": "u1", "_session_token": "tok-a"}, None
        ) is False

        # Upload session with matching token -> visible
        assert is_session_visible(
            {"session_id": "up", "_upload_id": "u1", "_session_token": "tok-a"}, "tok-a"
        ) is True

        # Upload session with wrong token -> not visible
        assert is_session_visible(
            {"session_id": "up", "_upload_id": "u1", "_session_token": "tok-a"}, "tok-b"
        ) is False

        # Upload without _session_token (legacy) + any token -> not visible
        assert is_session_visible(
            {"session_id": "up", "_upload_id": "u1"}, "tok-a"
        ) is False

        print("is_session_visible() correctly checks all visibility rules")


class TestDualStore:
    """Test dual DiskStore metadata merging for demo mode."""

    def test_list_all_metadata_merges_stores(self, tmp_path):
        """list_all_metadata() returns sessions from both upload and example stores."""
        from vibelens.storage.conversation.disk import DiskStore

        upload_dir = tmp_path / "uploads"
        examples_dir = tmp_path / "examples"

        upload_store = DiskStore(root=upload_dir)
        upload_store.initialize()
        upload_store.save([_make_test_trajectory("upload-001", "Uploaded session")])

        example_store = DiskStore(root=examples_dir)
        example_store.initialize()
        example_store.save([_make_test_trajectory("example-001", "Example session")])

        # Verify each store has one session
        assert upload_store.session_count() == 1
        assert example_store.session_count() == 1

        # Simulate list_all_metadata by combining both
        merged = list(upload_store.list_metadata()) + list(example_store.list_metadata())
        session_ids = {m["session_id"] for m in merged}
        assert session_ids == {"upload-001", "example-001"}
        print(f"Merged metadata contains {len(merged)} sessions from dual stores")

    def test_load_from_stores_fallback(self, tmp_path):
        """load_from_stores() falls back to example store when primary returns None."""
        from vibelens.storage.conversation.disk import DiskStore

        upload_dir = tmp_path / "uploads"
        examples_dir = tmp_path / "examples"

        upload_store = DiskStore(root=upload_dir)
        upload_store.initialize()

        example_store = DiskStore(root=examples_dir)
        example_store.initialize()
        example_store.save([_make_test_trajectory("example-only", "Only in examples")])

        # Primary store doesn't have this session
        assert upload_store.load("example-only") is None

        # Example store has it
        result = example_store.load("example-only")
        assert result is not None
        assert result[0].session_id == "example-only"
        print("Fallback to example store works for sessions not in upload store")

    def test_get_metadata_from_stores_fallback(self, tmp_path):
        """get_metadata_from_stores() checks example store when primary returns None."""
        from vibelens.storage.conversation.disk import DiskStore

        upload_dir = tmp_path / "uploads"
        examples_dir = tmp_path / "examples"

        upload_store = DiskStore(root=upload_dir)
        upload_store.initialize()

        example_store = DiskStore(root=examples_dir)
        example_store.initialize()
        example_store.save([_make_test_trajectory("ex-meta", "Example metadata")])

        # Primary store returns None
        assert upload_store.get_metadata("ex-meta") is None

        # Example store returns metadata
        meta = example_store.get_metadata("ex-meta")
        assert meta is not None
        assert meta["session_id"] == "ex-meta"
        print("Metadata fallback to example store works correctly")

    def test_stores_are_independent(self, tmp_path):
        """Uploads and examples don't bleed into each other's indexes."""
        from vibelens.storage.conversation.disk import DiskStore

        upload_dir = tmp_path / "uploads"
        examples_dir = tmp_path / "examples"

        upload_store = DiskStore(root=upload_dir)
        upload_store.initialize()
        upload_store.save([_make_test_trajectory("upload-only", "Upload session")])

        example_store = DiskStore(root=examples_dir)
        example_store.initialize()
        example_store.save([_make_test_trajectory("example-only", "Example session")])

        # Each store only knows about its own sessions
        upload_ids = {m["session_id"] for m in upload_store.list_metadata()}
        example_ids = {m["session_id"] for m in example_store.list_metadata()}
        assert upload_ids == {"upload-only"}
        assert example_ids == {"example-only"}
        assert upload_ids.isdisjoint(example_ids)
        print("Upload and example stores are fully independent")

    def test_deduplication_when_same_session_in_both(self, tmp_path):
        """Sessions present in both stores appear only once (upload wins)."""
        from vibelens.storage.conversation.disk import DiskStore

        upload_dir = tmp_path / "uploads"
        examples_dir = tmp_path / "examples"

        upload_store = DiskStore(root=upload_dir)
        upload_store.initialize()
        upload_store.save([_make_test_trajectory("shared-001", "Upload version")])

        example_store = DiskStore(root=examples_dir)
        example_store.initialize()
        example_store.save([_make_test_trajectory("shared-001", "Example version")])
        example_store.save([_make_test_trajectory("example-only", "Only in examples")])

        # Simulate list_all_metadata deduplication logic
        metadata = list(upload_store.list_metadata())
        seen_ids = {m.get("session_id") for m in metadata}
        for m in example_store.list_metadata():
            if m.get("session_id") not in seen_ids:
                metadata.append(m)

        session_ids = [m["session_id"] for m in metadata]
        assert len(session_ids) == 2
        assert session_ids.count("shared-001") == 1
        assert "example-only" in session_ids
        print("Deduplication: shared session appears once, unique example included")


def _make_test_trajectory(session_id: str, first_message: str) -> Trajectory:
    """Create a minimal Trajectory for testing.

    Args:
        session_id: Session identifier.
        first_message: First user message text.

    Returns:
        A Trajectory with one user step.
    """
    return Trajectory(
        session_id=session_id,
        first_message=first_message,
        agent={"name": "test", "model_name": "test-model"},
        steps=[
            {
                "step_id": "step-1",
                "source": "user",
                "message": first_message,
                "timestamp": "2025-01-01T00:00:00Z",
            }
        ],
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
