"""Tests for the MongoDB data target."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vibelens.models.message import Message, SubAgentSession, TokenUsage, ToolCall
from vibelens.models.session import (
    DataSourceType,
    ParseDiagnostics,
    SessionDetail,
    SessionSummary,
)
from vibelens.targets.mongodb import (
    MAIN_AGENT_ID,
    _extract_sub_session_metadata,
    _flatten_messages,
    _serialize_message,
    _serialize_session,
)


def _make_summary(session_id: str = "test-session-1") -> SessionSummary:
    """Build a sample SessionSummary for testing."""
    return SessionSummary(
        session_id=session_id,
        project_id="encoded-project",
        project_name="my-project",
        timestamp=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC),
        duration=300,
        message_count=5,
        tool_call_count=3,
        models=["claude-opus-4-6"],
        first_message="Hello, fix the bug",
        source_type=DataSourceType.LOCAL,
        source_name="local",
        source_host="",
        total_input_tokens=1000,
        total_output_tokens=500,
        total_cache_read=200,
        total_cache_write=100,
        diagnostics=ParseDiagnostics(completeness_score=0.95),
    )


def _make_message(
    uuid: str = "msg-1",
    session_id: str = "test-session-1",
    role: str = "user",
) -> Message:
    """Build a sample Message for testing."""
    return Message(
        uuid=uuid,
        session_id=session_id,
        parent_uuid="",
        role=role,
        type=role,
        content="Hello world",
        model="claude-opus-4-6",
        timestamp=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC),
        usage=TokenUsage(input_tokens=100, output_tokens=50),
        tool_calls=[
            ToolCall(id="tc-1", name="Read", input={"file_path": "main.py"}, summary="main.py")
        ],
    )


def _make_detail(session_id: str = "test-session-1") -> SessionDetail:
    """Build a sample SessionDetail for testing."""
    return SessionDetail(
        summary=_make_summary(session_id),
        messages=[
            _make_message("msg-1", session_id, "user"),
            _make_message("msg-2", session_id, "assistant"),
        ],
    )


def _make_detail_with_subagents() -> SessionDetail:
    """Build a SessionDetail with sub-agent sessions."""
    session_id = "test-session-sub"
    sub = SubAgentSession(
        agent_id="agent-abc123",
        spawn_index=1,
        spawn_tool_call_id="tc-spawn-1",
        messages=[
            _make_message("sub-msg-1", session_id, "user"),
            _make_message("sub-msg-2", session_id, "assistant"),
        ],
        sub_sessions=[
            SubAgentSession(
                agent_id="agent-nested",
                spawn_index=0,
                spawn_tool_call_id="tc-spawn-nested",
                messages=[_make_message("nested-msg-1", session_id, "assistant")],
            )
        ],
    )
    return SessionDetail(
        summary=_make_summary(session_id),
        messages=[_make_message("main-msg-1", session_id, "user")],
        sub_sessions=[sub],
    )


class TestSerializeSession:
    """Tests for _serialize_session."""

    def test_basic_fields(self):
        detail = _make_detail()
        doc = _serialize_session(detail)

        assert doc["_id"] == "test-session-1"
        assert doc["project_id"] == "encoded-project"
        assert doc["project_name"] == "my-project"
        assert doc["duration"] == 300
        assert doc["message_count"] == 5
        assert doc["tool_call_count"] == 3
        assert doc["models"] == ["claude-opus-4-6"]
        assert doc["first_message"] == "Hello, fix the bug"
        assert doc["source_type"] == "local"
        print(f"Session doc: {doc}")

    def test_timestamp_serialized(self):
        detail = _make_detail()
        doc = _serialize_session(detail)

        assert doc["timestamp"] is not None
        assert "2025-06-15" in doc["timestamp"]
        print(f"Timestamp: {doc['timestamp']}")

    def test_token_fields(self):
        detail = _make_detail()
        doc = _serialize_session(detail)

        assert doc["total_input_tokens"] == 1000
        assert doc["total_output_tokens"] == 500
        assert doc["total_cache_read"] == 200
        assert doc["total_cache_write"] == 100

    def test_diagnostics_serialized(self):
        detail = _make_detail()
        doc = _serialize_session(detail)

        assert doc["diagnostics"] is not None
        assert doc["diagnostics"]["completeness_score"] == 0.95

    def test_diagnostics_none(self):
        detail = _make_detail()
        detail.summary.diagnostics = None
        doc = _serialize_session(detail)

        assert doc["diagnostics"] is None

    def test_sub_sessions_metadata(self):
        detail = _make_detail_with_subagents()
        doc = _serialize_session(detail)

        assert len(doc["sub_sessions"]) == 1
        sub = doc["sub_sessions"][0]
        assert sub["agent_id"] == "agent-abc123"
        assert sub["spawn_index"] == 1
        assert sub["spawn_tool_call_id"] == "tc-spawn-1"
        assert len(sub["sub_sessions"]) == 1
        assert sub["sub_sessions"][0]["agent_id"] == "agent-nested"
        print(f"Sub-session metadata: {doc['sub_sessions']}")


class TestExtractSubSessionMetadata:
    """Tests for _extract_sub_session_metadata."""

    def test_basic_extraction(self):
        sub = SubAgentSession(
            agent_id="agent-test",
            spawn_index=2,
            spawn_tool_call_id="tc-42",
            messages=[_make_message()],
        )
        meta = _extract_sub_session_metadata(sub)

        assert meta["agent_id"] == "agent-test"
        assert meta["spawn_index"] == 2
        assert meta["spawn_tool_call_id"] == "tc-42"
        assert meta["sub_sessions"] == []
        assert "messages" not in meta
        print(f"Extracted metadata: {meta}")

    def test_nested_sub_sessions(self):
        nested = SubAgentSession(agent_id="agent-inner", messages=[])
        outer = SubAgentSession(
            agent_id="agent-outer", messages=[], sub_sessions=[nested]
        )
        meta = _extract_sub_session_metadata(outer)

        assert len(meta["sub_sessions"]) == 1
        assert meta["sub_sessions"][0]["agent_id"] == "agent-inner"


class TestSerializeMessage:
    """Tests for _serialize_message."""

    def test_basic_fields(self):
        msg = _make_message()
        doc = _serialize_message(msg, MAIN_AGENT_ID)

        assert doc["_id"] == "msg-1"
        assert doc["session_id"] == "test-session-1"
        assert doc["agent_id"] == ""
        assert doc["role"] == "user"
        assert doc["content"] == "Hello world"
        assert doc["model"] == "claude-opus-4-6"
        print(f"Message doc: {doc}")

    def test_agent_id_set(self):
        msg = _make_message()
        doc = _serialize_message(msg, "agent-xyz")

        assert doc["agent_id"] == "agent-xyz"

    def test_usage_serialized(self):
        msg = _make_message()
        doc = _serialize_message(msg, MAIN_AGENT_ID)

        assert doc["usage"] is not None
        assert doc["usage"]["input_tokens"] == 100
        assert doc["usage"]["output_tokens"] == 50

    def test_usage_none(self):
        msg = _make_message()
        msg.usage = None
        doc = _serialize_message(msg, MAIN_AGENT_ID)

        assert doc["usage"] is None

    def test_tool_calls_serialized(self):
        msg = _make_message()
        doc = _serialize_message(msg, MAIN_AGENT_ID)

        assert len(doc["tool_calls"]) == 1
        assert doc["tool_calls"][0]["name"] == "Read"
        assert doc["tool_calls"][0]["id"] == "tc-1"

    def test_timestamp_serialized(self):
        msg = _make_message()
        doc = _serialize_message(msg, MAIN_AGENT_ID)

        assert doc["timestamp"] is not None
        assert "2025-06-15" in doc["timestamp"]

    def test_content_as_list(self):
        """Content blocks should serialize to list of dicts."""
        from vibelens.models.message import ContentBlock

        msg = _make_message()
        msg.content = [ContentBlock(type="text", text="Hello")]
        doc = _serialize_message(msg, MAIN_AGENT_ID)

        assert isinstance(doc["content"], list)
        assert doc["content"][0]["type"] == "text"
        assert doc["content"][0]["text"] == "Hello"


class TestFlattenMessages:
    """Tests for _flatten_messages."""

    def test_main_messages_only(self):
        detail = _make_detail()
        docs = _flatten_messages(detail)

        assert len(docs) == 2
        assert all(d["agent_id"] == MAIN_AGENT_ID for d in docs)
        print(f"Flattened {len(docs)} messages (main only)")

    def test_with_sub_agents(self):
        detail = _make_detail_with_subagents()
        docs = _flatten_messages(detail)

        # 1 main + 2 sub + 1 nested
        assert len(docs) == 4

        agent_ids = [d["agent_id"] for d in docs]
        assert "" in agent_ids
        assert "agent-abc123" in agent_ids
        assert "agent-nested" in agent_ids
        print(f"Flattened {len(docs)} messages with agent_ids: {agent_ids}")

    def test_empty_session(self):
        detail = SessionDetail(summary=_make_summary(), messages=[], sub_sessions=[])
        docs = _flatten_messages(detail)

        assert docs == []


class TestPushSessions:
    """Tests for MongoDBTarget.push_sessions."""

    @pytest.mark.asyncio
    async def test_push_single_session(self):
        from vibelens.targets.mongodb import MongoDBTarget

        with patch("vibelens.targets.mongodb.AsyncIOMotorClient"):
            target = MongoDBTarget("mongodb://localhost:27017", "test_db")

        target.sessions = MagicMock()
        target.sessions.find_one = AsyncMock(return_value=None)
        target.sessions.insert_one = AsyncMock()
        target.messages = MagicMock()
        target.messages.insert_many = AsyncMock()

        detail = _make_detail()
        result = await target.push_sessions([detail])

        assert result.total == 1
        assert result.uploaded == 1
        assert result.skipped == 0
        assert result.errors == []
        target.sessions.insert_one.assert_awaited_once()
        target.messages.insert_many.assert_awaited_once()
        print(f"Push result: {result}")

    @pytest.mark.asyncio
    async def test_push_skips_existing(self):
        from vibelens.targets.mongodb import MongoDBTarget

        with patch("vibelens.targets.mongodb.AsyncIOMotorClient"):
            target = MongoDBTarget("mongodb://localhost:27017", "test_db")

        target.sessions = MagicMock()
        target.sessions.find_one = AsyncMock(return_value={"_id": "test-session-1"})
        target.sessions.insert_one = AsyncMock()
        target.messages = MagicMock()

        detail = _make_detail()
        result = await target.push_sessions([detail])

        assert result.total == 1
        assert result.uploaded == 0
        assert result.skipped == 1
        target.sessions.insert_one.assert_not_awaited()
        print(f"Skipped existing: {result}")

    @pytest.mark.asyncio
    async def test_push_with_sub_agents(self):
        from vibelens.targets.mongodb import MongoDBTarget

        with patch("vibelens.targets.mongodb.AsyncIOMotorClient"):
            target = MongoDBTarget("mongodb://localhost:27017", "test_db")

        target.sessions = MagicMock()
        target.sessions.find_one = AsyncMock(return_value=None)
        target.sessions.insert_one = AsyncMock()
        target.messages = MagicMock()
        target.messages.insert_many = AsyncMock()

        detail = _make_detail_with_subagents()
        result = await target.push_sessions([detail])

        assert result.uploaded == 1
        # 4 messages total (1 main + 2 sub + 1 nested)
        call_args = target.messages.insert_many.call_args[0][0]
        assert len(call_args) == 4
        print(f"Pushed with sub-agents: {len(call_args)} messages")

    @pytest.mark.asyncio
    async def test_push_error_handling(self):
        from vibelens.targets.mongodb import MongoDBTarget

        with patch("vibelens.targets.mongodb.AsyncIOMotorClient"):
            target = MongoDBTarget("mongodb://localhost:27017", "test_db")

        target.sessions = MagicMock()
        target.sessions.find_one = AsyncMock(side_effect=Exception("Connection lost"))
        target.messages = MagicMock()

        detail = _make_detail()
        result = await target.push_sessions([detail])

        assert result.total == 1
        assert result.uploaded == 0
        assert result.skipped == 0
        assert len(result.errors) == 1
        assert "Connection lost" in result.errors[0]["error"]
        print(f"Error handled: {result.errors}")

    @pytest.mark.asyncio
    async def test_push_multiple_sessions(self):
        from vibelens.targets.mongodb import MongoDBTarget

        with patch("vibelens.targets.mongodb.AsyncIOMotorClient"):
            target = MongoDBTarget("mongodb://localhost:27017", "test_db")

        call_count = 0

        async def find_one_side_effect(query, projection):
            nonlocal call_count
            call_count += 1
            # First session exists, second doesn't
            if query["_id"] == "session-1":
                return {"_id": "session-1"}
            return None

        target.sessions = MagicMock()
        target.sessions.find_one = AsyncMock(side_effect=find_one_side_effect)
        target.sessions.insert_one = AsyncMock()
        target.messages = MagicMock()
        target.messages.insert_many = AsyncMock()

        sessions = [_make_detail("session-1"), _make_detail("session-2")]
        result = await target.push_sessions(sessions)

        assert result.total == 2
        assert result.uploaded == 1
        assert result.skipped == 1
        print(f"Mixed push: {result}")

    @pytest.mark.asyncio
    async def test_push_empty_messages(self):
        from vibelens.targets.mongodb import MongoDBTarget

        with patch("vibelens.targets.mongodb.AsyncIOMotorClient"):
            target = MongoDBTarget("mongodb://localhost:27017", "test_db")

        target.sessions = MagicMock()
        target.sessions.find_one = AsyncMock(return_value=None)
        target.sessions.insert_one = AsyncMock()
        target.messages = MagicMock()
        target.messages.insert_many = AsyncMock()

        detail = SessionDetail(summary=_make_summary(), messages=[], sub_sessions=[])
        result = await target.push_sessions([detail])

        assert result.uploaded == 1
        target.messages.insert_many.assert_not_awaited()
        print("Pushed session with no messages")


class TestEnsureIndexes:
    """Tests for MongoDBTarget.ensure_indexes."""

    @pytest.mark.asyncio
    async def test_creates_indexes(self):
        from vibelens.targets.mongodb import MongoDBTarget

        with patch("vibelens.targets.mongodb.AsyncIOMotorClient"):
            target = MongoDBTarget("mongodb://localhost:27017", "test_db")

        target.sessions = MagicMock()
        target.sessions.create_index = AsyncMock()
        target.messages = MagicMock()
        target.messages.create_index = AsyncMock()

        await target.ensure_indexes()

        assert target.sessions.create_index.await_count == 3
        assert target.messages.create_index.await_count == 2
        print("Indexes created successfully")
