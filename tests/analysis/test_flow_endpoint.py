"""Tests for session flow endpoint and service function."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from vibelens.config import Settings
from vibelens.models.trajectories import (
    Agent,
    FinalMetrics,
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
)
from vibelens.services.flow_service import get_session_flow


def _make_flow_trajectory(
    session_id: str = "flow-test-session",
) -> Trajectory:
    """Build a trajectory with read→edit tool calls for flow graph testing."""
    ts = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)

    user_step = Step(
        step_id="step-user-1",
        source="user",
        message="Fix the auth bug",
        timestamp=ts,
        metrics=Metrics(prompt_tokens=100, completion_tokens=0),
    )

    read_call = ToolCall(
        tool_call_id="tc-read-1",
        function_name="Read",
        arguments={"file_path": "/src/auth.py"},
    )
    grep_call = ToolCall(
        tool_call_id="tc-grep-1",
        function_name="Grep",
        arguments={"pattern": "def login", "path": "/src/"},
    )

    agent_step_1 = Step(
        step_id="step-agent-1",
        source="agent",
        message="Let me investigate the auth code",
        timestamp=datetime(2026, 3, 15, 10, 1, tzinfo=UTC),
        tool_calls=[grep_call, read_call],
        observation=Observation(
            results=[
                ObservationResult(source_call_id="tc-grep-1", content="src/auth.py:10:def login"),
                ObservationResult(source_call_id="tc-read-1", content="file content..."),
            ]
        ),
        metrics=Metrics(prompt_tokens=200, completion_tokens=150),
    )

    edit_call = ToolCall(
        tool_call_id="tc-edit-1",
        function_name="Edit",
        arguments={"file_path": "/src/auth.py", "old_string": "bug", "new_string": "fix"},
    )
    bash_call = ToolCall(
        tool_call_id="tc-bash-1",
        function_name="Bash",
        arguments={"command": "pytest tests/"},
    )

    agent_step_2 = Step(
        step_id="step-agent-2",
        source="agent",
        message="I'll fix the bug and run tests",
        timestamp=datetime(2026, 3, 15, 10, 2, tzinfo=UTC),
        tool_calls=[edit_call, bash_call],
        observation=Observation(
            results=[
                ObservationResult(source_call_id="tc-edit-1", content="Edit applied"),
                ObservationResult(source_call_id="tc-bash-1", content="All tests passed"),
            ]
        ),
        metrics=Metrics(prompt_tokens=200, completion_tokens=100),
    )

    return Trajectory(
        session_id=session_id,
        project_path="/Users/test/myproject",
        agent=Agent(name="claude-code", model_name="claude-sonnet-4-6"),
        steps=[user_step, agent_step_1, agent_step_2],
        final_metrics=FinalMetrics(duration=120, total_steps=3, tool_call_count=4),
    )


class TestGetSessionFlow:
    """Tests for the get_session_flow service function."""

    def test_returns_none_for_missing_session(self):
        """Non-existent session returns None."""
        with patch("vibelens.services.flow_service.get_store") as mock_store:
            mock_store.return_value.load.return_value = None
            result = get_session_flow("nonexistent", None)
            assert result is None

    def test_returns_flow_data_structure(self):
        """Valid session returns dict with expected keys."""
        traj = _make_flow_trajectory()
        with patch("vibelens.services.flow_service.get_store") as mock_store:
            mock_store.return_value.load.return_value = [traj]
            result = get_session_flow("flow-test-session", None)

        assert result is not None
        assert result["session_id"] == "flow-test-session"
        assert "tool_graph" in result
        assert "phase_segments" in result

    def test_tool_graph_has_nodes_and_edges(self):
        """Tool graph contains nodes for each tool call and inferred edges."""
        traj = _make_flow_trajectory()
        with patch("vibelens.services.flow_service.get_store") as mock_store:
            mock_store.return_value.load.return_value = [traj]
            result = get_session_flow("flow-test-session", None)

        graph = result["tool_graph"]
        assert graph["session_id"] == "flow-test-session"
        assert len(graph["nodes"]) == 4
        assert isinstance(graph["edges"], list)
        assert len(graph["edges"]) > 0
        assert isinstance(graph["root_nodes"], list)

    def test_tool_graph_contains_read_before_write_edge(self):
        """Read(auth.py) followed by Edit(auth.py) produces read_before_write edge."""
        traj = _make_flow_trajectory()
        with patch("vibelens.services.flow_service.get_store") as mock_store:
            mock_store.return_value.load.return_value = [traj]
            result = get_session_flow("flow-test-session", None)

        graph = result["tool_graph"]
        rbw_edges = [e for e in graph["edges"] if e["relation"] == "read_before_write"]
        assert len(rbw_edges) >= 1
        edge = rbw_edges[0]
        assert edge["source_tool_call_id"] == "tc-read-1"
        assert edge["target_tool_call_id"] == "tc-edit-1"
        assert edge["shared_resource"] == "/src/auth.py"

    def test_tool_graph_contains_search_then_read_edge(self):
        """Grep followed by Read produces search_then_read edge."""
        traj = _make_flow_trajectory()
        with patch("vibelens.services.flow_service.get_store") as mock_store:
            mock_store.return_value.load.return_value = [traj]
            result = get_session_flow("flow-test-session", None)

        graph = result["tool_graph"]
        str_edges = [e for e in graph["edges"] if e["relation"] == "search_then_read"]
        assert len(str_edges) >= 1
        assert str_edges[0]["source_tool_call_id"] == "tc-grep-1"
        assert str_edges[0]["target_tool_call_id"] == "tc-read-1"

    def test_phase_segments_cover_session(self):
        """Phase segments list is non-empty and has expected structure."""
        traj = _make_flow_trajectory()
        with patch("vibelens.services.flow_service.get_store") as mock_store:
            mock_store.return_value.load.return_value = [traj]
            result = get_session_flow("flow-test-session", None)

        segments = result["phase_segments"]
        assert isinstance(segments, list)
        assert len(segments) >= 1
        seg = segments[0]
        assert "phase" in seg
        assert "start_index" in seg
        assert "end_index" in seg

    def test_empty_session_returns_empty_graph(self):
        """Session with no tool calls returns empty graph."""
        traj = Trajectory(
            session_id="empty-session",
            project_path="/test",
            agent=Agent(name="claude-code", model_name="claude-sonnet-4-6"),
            steps=[
                Step(
                    step_id="step-1",
                    source="user",
                    message="Hello",
                    metrics=Metrics(prompt_tokens=10, completion_tokens=0),
                ),
            ],
            final_metrics=FinalMetrics(duration=5, total_steps=1, tool_call_count=0),
        )
        with patch("vibelens.services.flow_service.get_store") as mock_store:
            mock_store.return_value.load.return_value = [traj]
            result = get_session_flow("empty-session", None)

        graph = result["tool_graph"]
        assert len(graph["nodes"]) == 0
        assert len(graph["edges"]) == 0


@pytest.fixture
def _e2e_settings(tmp_path: Path):
    """Create settings with temp Claude dir for API tests."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    projects_dir = claude_dir / "projects"
    projects_dir.mkdir()
    project_dir = projects_dir / "-Users-TestProject-Agent-Test"
    project_dir.mkdir()
    return (
        Settings(
            claude_dir=claude_dir,
            codex_dir=tmp_path / ".codex",
            gemini_dir=tmp_path / ".gemini",
        ),
        claude_dir,
        project_dir,
    )


@pytest.fixture
def _e2e_session(_e2e_settings):
    """Create a session-002 file with tool calls."""
    _, claude_dir, project_dir = _e2e_settings
    history_file = claude_dir / "history.jsonl"
    history_file.write_text(
        json.dumps(
            {
                "display": "Explain JWT",
                "pastedContents": {},
                "timestamp": 1707734680000,
                "project": "/Users/TestProject/Agent-Test",
                "sessionId": "session-002",
            }
        )
        + "\n"
    )
    session_file = project_dir / "session-002.jsonl"
    lines = [
        {
            "type": "user",
            "uuid": "msg-003",
            "sessionId": "session-002",
            "timestamp": 1707734685000,
            "message": {"role": "user", "content": "Explain JWT"},
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
                    {"type": "text", "text": "Let me look..."},
                    {
                        "type": "tool_use",
                        "id": "tool-001",
                        "name": "Read",
                        "input": {"file_path": "/tmp/jwt.md"},
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
                        "content": "JWT docs...",
                        "is_error": False,
                    }
                ],
            },
        },
    ]
    session_file.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    return _e2e_settings


@pytest.mark.asyncio
class TestFlowAPIEndpoint:
    """Tests for the /analysis/sessions/{id}/flow API endpoint."""

    async def test_flow_endpoint_returns_200(self, _e2e_session, monkeypatch):
        """Flow endpoint returns 200 with valid session."""
        settings, _, _ = _e2e_session
        import httpx

        import vibelens.app
        import vibelens.deps

        def mock_load_settings():
            return settings

        monkeypatch.setattr(vibelens.app, "load_settings", mock_load_settings)
        monkeypatch.setattr(vibelens.deps, "load_settings", mock_load_settings)
        app = vibelens.app.create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/sessions/session-002/flow")
            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
            assert "tool_graph" in data
            assert "phase_segments" in data

    async def test_flow_endpoint_returns_404_for_missing(self, _e2e_settings, monkeypatch):
        """Flow endpoint returns 404 for non-existent session."""
        settings, _, _ = _e2e_settings
        import httpx

        import vibelens.app
        import vibelens.deps

        def mock_load_settings():
            return settings

        monkeypatch.setattr(vibelens.app, "load_settings", mock_load_settings)
        monkeypatch.setattr(vibelens.deps, "load_settings", mock_load_settings)
        app = vibelens.app.create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/sessions/nonexistent/flow")
            assert response.status_code == 404
