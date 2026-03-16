"""Tests for the MongoDB data source."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vibelens.models.message import Message
from vibelens.models.requests import RemoteSessionsQuery
from vibelens.models.session import DataSourceType, SessionSummary
from vibelens.sources.mongodb import (
    _deserialize_message,
    _deserialize_session,
    _reconstruct_sub_sessions,
)


def _make_session_doc(session_id: str = "test-session-1") -> dict:
    """Build a sample MongoDB session document."""
    return {
        "_id": session_id,
        "project_id": "encoded-project",
        "project_name": "my-project",
        "timestamp": "2025-06-15T10:00:00+00:00",
        "duration": 300,
        "message_count": 5,
        "tool_call_count": 3,
        "models": ["claude-opus-4-6"],
        "first_message": "Hello, fix the bug",
        "source_type": "local",
        "source_name": "local",
        "source_host": "",
        "total_input_tokens": 1000,
        "total_output_tokens": 500,
        "total_cache_read": 200,
        "total_cache_write": 100,
        "diagnostics": {
            "completeness_score": 0.95,
            "skipped_lines": 0,
            "orphaned_tool_calls": 0,
            "orphaned_tool_results": 0,
        },
        "sub_sessions": [],
    }


def _make_message_doc(
    uuid: str = "msg-1", session_id: str = "test-session-1", agent_id: str = "", role: str = "user"
) -> dict:
    """Build a sample MongoDB message document."""
    return {
        "_id": uuid,
        "session_id": session_id,
        "agent_id": agent_id,
        "parent_uuid": "",
        "role": role,
        "type": role,
        "content": "Hello world",
        "thinking": None,
        "model": "claude-opus-4-6",
        "timestamp": "2025-06-15T10:00:00+00:00",
        "is_sidechain": False,
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
        },
        "tool_calls": [],
    }


class _AsyncCursorMock:
    """Mock for an async MongoDB cursor that supports sort/skip/limit chaining."""

    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def sort(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return self

    def skip(self, n: int):  # noqa: ANN201
        self._docs = self._docs[n:]
        return self

    def limit(self, n: int):  # noqa: ANN201
        self._docs = self._docs[:n]
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._docs:
            raise StopAsyncIteration
        return self._docs.pop(0)


class TestDeserializeSession:
    """Tests for _deserialize_session."""

    def test_basic_fields(self):
        doc = _make_session_doc()
        summary = _deserialize_session(doc)

        assert isinstance(summary, SessionSummary)
        assert summary.session_id == "test-session-1"
        assert summary.project_name == "my-project"
        assert summary.duration == 300
        assert summary.models == ["claude-opus-4-6"]
        print(f"Deserialized: {summary.session_id}")

    def test_token_fields(self):
        doc = _make_session_doc()
        summary = _deserialize_session(doc)

        assert summary.total_input_tokens == 1000
        assert summary.total_output_tokens == 500

    def test_diagnostics(self):
        doc = _make_session_doc()
        summary = _deserialize_session(doc)

        assert summary.diagnostics is not None
        assert summary.diagnostics.completeness_score == 0.95

    def test_diagnostics_none(self):
        doc = _make_session_doc()
        doc["diagnostics"] = None
        summary = _deserialize_session(doc)

        assert summary.diagnostics is None

    def test_missing_fields_use_defaults(self):
        doc = {"_id": "minimal-session"}
        summary = _deserialize_session(doc)

        assert summary.session_id == "minimal-session"
        assert summary.project_name == ""
        assert summary.models == []
        assert summary.duration == 0
        print(f"Minimal session: {summary}")


class TestDeserializeMessage:
    """Tests for _deserialize_message."""

    def test_basic_fields(self):
        doc = _make_message_doc()
        msg = _deserialize_message(doc)

        assert isinstance(msg, Message)
        assert msg.uuid == "msg-1"
        assert msg.role == "user"
        assert msg.content == "Hello world"
        print(f"Deserialized message: {msg.uuid}")

    def test_usage_deserialized(self):
        doc = _make_message_doc()
        msg = _deserialize_message(doc)

        assert msg.usage is not None
        assert msg.usage.input_tokens == 100

    def test_usage_none(self):
        doc = _make_message_doc()
        doc["usage"] = None
        msg = _deserialize_message(doc)

        assert msg.usage is None

    def test_tool_calls_deserialized(self):
        doc = _make_message_doc()
        doc["tool_calls"] = [
            {
                "id": "tc-1",
                "name": "Read",
                "input": {},
                "output": None,
                "is_error": False,
                "summary": "",
                "category": "",
                "output_digest": "",
            },
        ]
        msg = _deserialize_message(doc)

        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "Read"


class TestReconstructSubSessions:
    """Tests for _reconstruct_sub_sessions."""

    def test_empty_meta(self):
        result = _reconstruct_sub_sessions([], {})
        assert result == []

    def test_single_sub_agent(self):
        meta = [
            {
                "agent_id": "agent-1",
                "spawn_index": 0,
                "spawn_tool_call_id": "tc-1",
                "sub_sessions": [],
            }
        ]
        messages_by_agent = {
            "agent-1": [
                Message(uuid="m1", session_id="s1", role="user", type="user"),
                Message(uuid="m2", session_id="s1", role="assistant", type="assistant"),
            ]
        }
        result = _reconstruct_sub_sessions(meta, messages_by_agent)

        assert len(result) == 1
        assert result[0].agent_id == "agent-1"
        assert len(result[0].messages) == 2
        assert result[0].sub_sessions == []
        print(f"Reconstructed: {result[0].agent_id} with {len(result[0].messages)} messages")

    def test_nested_sub_agents(self):
        meta = [
            {
                "agent_id": "agent-outer",
                "spawn_index": 1,
                "spawn_tool_call_id": "tc-outer",
                "sub_sessions": [
                    {
                        "agent_id": "agent-inner",
                        "spawn_index": 0,
                        "spawn_tool_call_id": "tc-inner",
                        "sub_sessions": [],
                    }
                ],
            }
        ]
        messages_by_agent = {
            "agent-outer": [Message(uuid="m1", session_id="s1", role="user", type="user")],
            "agent-inner": [
                Message(uuid="m2", session_id="s1", role="assistant", type="assistant"),
            ],
        }
        result = _reconstruct_sub_sessions(meta, messages_by_agent)

        assert len(result) == 1
        assert result[0].agent_id == "agent-outer"
        assert len(result[0].sub_sessions) == 1
        assert result[0].sub_sessions[0].agent_id == "agent-inner"
        assert len(result[0].sub_sessions[0].messages) == 1
        print("Nested sub-agents reconstructed")

    def test_missing_messages(self):
        meta = [
            {
                "agent_id": "agent-x",
                "spawn_index": 0,
                "spawn_tool_call_id": "tc-x",
                "sub_sessions": [],
            }
        ]
        result = _reconstruct_sub_sessions(meta, {})

        assert len(result) == 1
        assert result[0].messages == []
        print("Missing messages handled gracefully")


class TestListSessions:
    """Tests for MongoDBSource.list_sessions."""

    @pytest.mark.asyncio
    async def test_list_all(self):
        from vibelens.sources.mongodb import MongoDBSource

        with patch("vibelens.sources.mongodb.AsyncIOMotorClient"):
            source = MongoDBSource("mongodb://localhost:27017", "test_db")

        docs = [_make_session_doc(f"s-{i}") for i in range(3)]
        source.sessions = MagicMock()
        source.sessions.find = MagicMock(return_value=_AsyncCursorMock(docs))

        query = RemoteSessionsQuery(limit=100)
        result = await source.list_sessions(query)

        assert len(result) == 3
        assert all(isinstance(s, SessionSummary) for s in result)
        print(f"Listed {len(result)} sessions")

    @pytest.mark.asyncio
    async def test_list_with_source_filter(self):
        from vibelens.sources.mongodb import MongoDBSource

        with patch("vibelens.sources.mongodb.AsyncIOMotorClient"):
            source = MongoDBSource("mongodb://localhost:27017", "test_db")

        docs = [_make_session_doc("s-1")]
        source.sessions = MagicMock()
        source.sessions.find = MagicMock(return_value=_AsyncCursorMock(docs))

        query = RemoteSessionsQuery(source_type=DataSourceType.LOCAL, limit=100)
        result = await source.list_sessions(query)

        assert len(result) == 1
        find_filter = source.sessions.find.call_args[0][0]
        assert find_filter["source_type"] == "local"
        print(f"Filter applied: {find_filter}")

    @pytest.mark.asyncio
    async def test_list_with_project_filter(self):
        from vibelens.sources.mongodb import MongoDBSource

        with patch("vibelens.sources.mongodb.AsyncIOMotorClient"):
            source = MongoDBSource("mongodb://localhost:27017", "test_db")

        source.sessions = MagicMock()
        source.sessions.find = MagicMock(return_value=_AsyncCursorMock([]))

        query = RemoteSessionsQuery(project_id="my-project", limit=100)
        await source.list_sessions(query)

        find_filter = source.sessions.find.call_args[0][0]
        assert find_filter["project_name"] == "my-project"

    @pytest.mark.asyncio
    async def test_list_pagination(self):
        from vibelens.sources.mongodb import MongoDBSource

        with patch("vibelens.sources.mongodb.AsyncIOMotorClient"):
            source = MongoDBSource("mongodb://localhost:27017", "test_db")

        docs = [_make_session_doc(f"s-{i}") for i in range(5)]
        source.sessions = MagicMock()
        source.sessions.find = MagicMock(return_value=_AsyncCursorMock(docs))

        query = RemoteSessionsQuery(limit=2, offset=1)
        result = await source.list_sessions(query)

        # Cursor mock applies skip(1) then limit(2)
        assert len(result) == 2
        print(f"Pagination: got {len(result)} sessions")

    @pytest.mark.asyncio
    async def test_list_empty(self):
        from vibelens.sources.mongodb import MongoDBSource

        with patch("vibelens.sources.mongodb.AsyncIOMotorClient"):
            source = MongoDBSource("mongodb://localhost:27017", "test_db")

        source.sessions = MagicMock()
        source.sessions.find = MagicMock(return_value=_AsyncCursorMock([]))

        query = RemoteSessionsQuery(limit=100)
        result = await source.list_sessions(query)

        assert result == []


class TestGetSession:
    """Tests for MongoDBSource.get_session."""

    @pytest.mark.asyncio
    async def test_existing_session(self):
        from vibelens.sources.mongodb import MongoDBSource

        with patch("vibelens.sources.mongodb.AsyncIOMotorClient"):
            source = MongoDBSource("mongodb://localhost:27017", "test_db")

        session_doc = _make_session_doc()
        message_docs = [
            _make_message_doc("msg-1", "test-session-1", "", "user"),
            _make_message_doc("msg-2", "test-session-1", "", "assistant"),
        ]

        source.sessions = MagicMock()
        source.sessions.find_one = AsyncMock(return_value=session_doc)
        source.messages = MagicMock()
        source.messages.find = MagicMock(return_value=_AsyncCursorMock(message_docs))

        detail = await source.get_session("test-session-1")

        assert detail is not None
        assert detail.summary.session_id == "test-session-1"
        assert len(detail.messages) == 2
        assert detail.sub_sessions == []
        print(f"Got session: {detail.summary.session_id} with {len(detail.messages)} messages")

    @pytest.mark.asyncio
    async def test_nonexistent_session(self):
        from vibelens.sources.mongodb import MongoDBSource

        with patch("vibelens.sources.mongodb.AsyncIOMotorClient"):
            source = MongoDBSource("mongodb://localhost:27017", "test_db")

        source.sessions = MagicMock()
        source.sessions.find_one = AsyncMock(return_value=None)

        detail = await source.get_session("does-not-exist")

        assert detail is None
        print("Nonexistent session returned None")

    @pytest.mark.asyncio
    async def test_session_with_sub_agents(self):
        from vibelens.sources.mongodb import MongoDBSource

        with patch("vibelens.sources.mongodb.AsyncIOMotorClient"):
            source = MongoDBSource("mongodb://localhost:27017", "test_db")

        session_doc = _make_session_doc()
        session_doc["sub_sessions"] = [
            {
                "agent_id": "agent-abc",
                "spawn_index": 0,
                "spawn_tool_call_id": "tc-1",
                "sub_sessions": [],
            }
        ]

        message_docs = [
            _make_message_doc("msg-1", "test-session-1", "", "user"),
            _make_message_doc("sub-msg-1", "test-session-1", "agent-abc", "assistant"),
        ]

        source.sessions = MagicMock()
        source.sessions.find_one = AsyncMock(return_value=session_doc)
        source.messages = MagicMock()
        source.messages.find = MagicMock(return_value=_AsyncCursorMock(message_docs))

        detail = await source.get_session("test-session-1")

        assert detail is not None
        assert len(detail.messages) == 1
        assert len(detail.sub_sessions) == 1
        assert detail.sub_sessions[0].agent_id == "agent-abc"
        assert len(detail.sub_sessions[0].messages) == 1
        print(f"Sub-agent reconstructed: {detail.sub_sessions[0].agent_id}")


class TestListProjects:
    """Tests for MongoDBSource.list_projects."""

    @pytest.mark.asyncio
    async def test_list_projects(self):
        from vibelens.sources.mongodb import MongoDBSource

        with patch("vibelens.sources.mongodb.AsyncIOMotorClient"):
            source = MongoDBSource("mongodb://localhost:27017", "test_db")

        source.sessions = MagicMock()
        source.sessions.distinct = AsyncMock(return_value=["project-b", "project-a", "project-c"])

        projects = await source.list_projects()

        assert projects == ["project-a", "project-b", "project-c"]
        print(f"Projects: {projects}")

    @pytest.mark.asyncio
    async def test_list_projects_empty(self):
        from vibelens.sources.mongodb import MongoDBSource

        with patch("vibelens.sources.mongodb.AsyncIOMotorClient"):
            source = MongoDBSource("mongodb://localhost:27017", "test_db")

        source.sessions = MagicMock()
        source.sessions.distinct = AsyncMock(return_value=[])

        projects = await source.list_projects()

        assert projects == []
        print("Empty projects list")
