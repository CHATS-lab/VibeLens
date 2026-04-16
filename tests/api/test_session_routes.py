"""Tests for session-related API routes."""

import json

import httpx
import pytest

import vibelens.deps
from vibelens.app import create_app
from vibelens.config import Settings
from vibelens.config.settings import StorageConfig, UploadConfig
from vibelens.models.enums import AgentType
from vibelens.storage.trajectory.local import LocalTrajectoryStore


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
        {
            "display": "What is a ghost record?",
            "pastedContents": {},
            "timestamp": 1707734690000,
            "project": "/Users/TestProject/Agent-Test",
            "sessionId": "session-ghost",
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


@pytest.fixture
async def app_client(test_settings, tmp_path, monkeypatch):
    """Create an async HTTP client with mocked settings and trajectory store."""
    data_dirs, _, _ = test_settings
    settings = Settings(
        storage=StorageConfig(examples_dir=tmp_path / ".vibelens" / "examples"),
        upload=UploadConfig(dir=tmp_path / ".vibelens" / "uploads"),
    )
    monkeypatch.setattr(vibelens.deps, "load_settings", lambda: settings)
    vibelens.deps.reset_singletons()
    vibelens.deps._registry["settings"] = settings
    vibelens.deps._registry["store"] = LocalTrajectoryStore(data_dirs=data_dirs)
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.mark.asyncio
class TestAPIEndpoints:
    """Test API endpoints."""

    async def test_get_projects(self, app_client):
        """Test /api/projects endpoint."""
        response = await app_client.get("/api/projects")
        assert response.status_code == 200
        projects = response.json()
        assert isinstance(projects, list)

    async def test_list_sessions(self, sample_history, sample_sessions, app_client):
        """Test /api/sessions endpoint returns trajectory summaries."""
        response = await app_client.get("/api/sessions?limit=100")
        assert response.status_code == 200
        sessions = response.json()
        assert isinstance(sessions, list)
        assert len(sessions) == 2
        session_ids = [s["session_id"] for s in sessions]
        assert "session-001" in session_ids
        assert "session-002" in session_ids

    async def test_list_sessions_with_pagination(self, sample_history, sample_sessions, app_client):
        """Test pagination parameters."""
        response = await app_client.get("/api/sessions?limit=1&offset=0")
        assert response.status_code == 200
        sessions = response.json()
        assert len(sessions) == 1

    async def test_list_sessions_by_project(self, sample_history, sample_sessions, app_client):
        """Test filtering by project name."""
        response = await app_client.get("/api/sessions?project_name=Agent-Test")
        assert response.status_code == 200
        sessions = response.json()
        assert all(s.get("project_path") == "Agent-Test" for s in sessions)

    async def test_get_session_detail(self, sample_history, sample_sessions, app_client):
        """Test /api/sessions/{id} returns trajectory group as JSON array."""
        response = await app_client.get("/api/sessions/session-001")
        assert response.status_code == 200
        group = response.json()

        assert isinstance(group, list)
        assert len(group) >= 1
        main_traj = group[0]
        assert main_traj["session_id"] == "session-001"
        assert len(main_traj["steps"]) == 2

    async def test_get_nonexistent_session(self, sample_history, app_client):
        """Test error handling for missing sessions."""
        response = await app_client.get("/api/sessions/nonexistent-session")
        assert response.status_code == 404

    async def test_get_ghost_session(self, sample_history, app_client):
        """Test that ghost records without files are filtered out."""
        response = await app_client.get("/api/sessions?limit=100")
        sessions = response.json()
        session_ids = [s["session_id"] for s in sessions]
        assert "session-ghost" not in session_ids

    async def test_session_with_tool_calls(self, sample_history, sample_sessions, app_client):
        """Test parsing of tool calls and results."""
        response = await app_client.get("/api/sessions/session-002")
        assert response.status_code == 200
        group = response.json()
        main_traj = group[0]

        tool_steps = [
            s for s in main_traj["steps"] if s["source"] == "agent" and s.get("tool_calls")
        ]
        assert len(tool_steps) > 0
        assert tool_steps[0]["tool_calls"][0]["function_name"] == "Read"

    async def test_session_token_usage(self, sample_history, sample_sessions, app_client):
        """Test token usage on steps."""
        response = await app_client.get("/api/sessions/session-001")
        assert response.status_code == 200
        group = response.json()
        main_traj = group[0]

        steps = main_traj["steps"]
        total_prompt = sum((s.get("metrics") or {}).get("prompt_tokens", 0) for s in steps)
        assert total_prompt > 0


@pytest.mark.asyncio
class TestSessionErrorHandling:
    """Test error handling via API routes."""

    async def test_missing_session_file(self, test_settings, app_client):
        """Test behavior when session referenced in history has no file."""
        _, claude_dir, _ = test_settings

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

        response = await app_client.get("/api/sessions?limit=100")
        sessions = response.json()
        assert len(sessions) == 0

        response = await app_client.get("/api/sessions/no-such-session")
        assert response.status_code == 404


@pytest.mark.asyncio
class TestSessionEdgeCases:
    """Test edge cases via API routes."""

    async def test_large_pagination_offset(self, sample_history, sample_sessions, app_client):
        """Test pagination with offset beyond available sessions."""
        response = await app_client.get("/api/sessions?limit=100&offset=1000")
        assert response.status_code == 200
        sessions = response.json()
        assert len(sessions) == 0

    async def test_session_with_empty_messages(self, test_settings, app_client):
        """Test session file with no messages."""
        _, claude_dir, test_project = test_settings

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

        session_file = test_project / "empty.jsonl"
        session_file.write_text("")

        response = await app_client.get("/api/sessions/empty")
        assert response.status_code in (200, 404)

    async def test_special_characters_in_content(self, test_settings, app_client):
        """Test handling of special characters in message content."""
        _, claude_dir, test_project = test_settings

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

        response = await app_client.get("/api/sessions/unicode-test")
        assert response.status_code == 200
        group = response.json()
        assert isinstance(group, list)
        assert len(group) >= 1
        assert len(group[0]["steps"]) == 1
