"""End-to-end tests for VibeLens application."""

import json
from pathlib import Path

import httpx
import pytest

from vibelens.app import create_app
from vibelens.config import Settings
from vibelens.storage.local import LocalStore as LocalSource


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
