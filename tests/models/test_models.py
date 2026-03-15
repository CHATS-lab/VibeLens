"""Unit tests for Pydantic models."""

from datetime import UTC, datetime

import pytest

from vibelens.models.analysis import (
    AgentBehaviorResult,
    TimePattern,
    ToolUsageStat,
    UserPreferenceResult,
)
from vibelens.models.message import ContentBlock, Message, TokenUsage, ToolCall
from vibelens.models.requests import (
    PullRequest,
    PullResult,
    PushRequest,
    PushResult,
    RemoteSessionsQuery,
)
from vibelens.models.session import (
    DataSourceType,
    DataTargetType,
    SessionDetail,
    SessionMetadata,
    SessionSummary,
)


class TestDataSourceType:
    """Test DataSourceType enum."""

    def test_values(self):
        assert DataSourceType.LOCAL == "local"
        assert DataSourceType.HUGGINGFACE == "huggingface"
        assert DataSourceType.MONGODB == "mongodb"

    def test_from_string(self):
        assert DataSourceType("local") is DataSourceType.LOCAL

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            DataSourceType("invalid")


class TestDataTargetType:
    """Test DataTargetType enum."""

    def test_values(self):
        assert DataTargetType.MONGODB == "mongodb"
        assert DataTargetType.HUGGINGFACE == "huggingface"


class TestSessionSummary:
    """Test SessionSummary model."""

    def test_minimal_creation(self):
        summary = SessionSummary(session_id="abc-123")
        assert summary.session_id == "abc-123"
        assert summary.project_id == ""
        assert summary.project_name == ""
        assert summary.timestamp is None
        assert summary.duration == 0
        assert summary.message_count == 0
        assert summary.tool_call_count == 0
        assert summary.models == []
        assert summary.first_message == ""
        assert summary.source_type == DataSourceType.LOCAL
        assert summary.source_name == ""
        assert summary.source_host == ""

    def test_full_creation(self):
        ts = datetime(2025, 1, 15, 10, 30, tzinfo=UTC)
        summary = SessionSummary(
            session_id="sess-1",
            project_id="Users-Foo-Project",
            project_name="Project",
            timestamp=ts,
            duration=120,
            message_count=10,
            tool_call_count=5,
            models=["claude-sonnet-4-6"],
            first_message="Hello world",
            source_type=DataSourceType.HUGGINGFACE,
            source_name="repo/dataset",
            source_host="huggingface.co",
        )
        assert summary.duration == 120
        assert summary.models == ["claude-sonnet-4-6"]
        assert summary.source_type == DataSourceType.HUGGINGFACE

    def test_serialization_roundtrip(self):
        ts = datetime(2025, 1, 15, 10, 30, tzinfo=UTC)
        original = SessionSummary(
            session_id="s1", project_name="Proj", timestamp=ts, message_count=3
        )
        data = original.model_dump()
        restored = SessionSummary(**data)
        assert restored.session_id == original.session_id
        assert restored.timestamp == original.timestamp

    def test_json_serialization(self):
        summary = SessionSummary(session_id="s1", message_count=5)
        json_str = summary.model_dump_json()
        assert '"session_id":"s1"' in json_str
        assert '"message_count":5' in json_str


class TestSessionDetail:
    """Test SessionDetail model."""

    def test_creation(self):
        summary = SessionSummary(session_id="s1")
        detail = SessionDetail(summary=summary)
        assert detail.summary.session_id == "s1"
        assert detail.messages == []

    def test_with_messages(self):
        summary = SessionSummary(session_id="s1")
        detail = SessionDetail(summary=summary, messages=[{"role": "user"}])
        assert len(detail.messages) == 1


class TestSessionMetadata:
    """Test SessionMetadata model."""

    def test_defaults(self):
        meta = SessionMetadata()
        assert meta.message_count == 0
        assert meta.tool_call_count == 0
        assert meta.models == []
        assert meta.first_message == ""
        assert meta.total_input_tokens == 0
        assert meta.total_output_tokens == 0
        assert meta.total_cache_read == 0
        assert meta.total_cache_write == 0
        assert meta.duration == 0

    def test_with_values(self):
        meta = SessionMetadata(
            message_count=10,
            tool_call_count=3,
            models=["claude-sonnet-4-6", "claude-haiku-4-5"],
            total_input_tokens=5000,
            total_output_tokens=2000,
            total_cache_read=1000,
            total_cache_write=500,
            duration=300,
        )
        assert meta.total_input_tokens == 5000
        assert len(meta.models) == 2


class TestPushRequest:
    """Test PushRequest model."""

    def test_creation(self):
        req = PushRequest(session_ids=["s1", "s2"], target=DataTargetType.MONGODB)
        assert len(req.session_ids) == 2
        assert req.target == DataTargetType.MONGODB

    def test_missing_required_fields(self):
        with pytest.raises(ValueError):
            PushRequest()


class TestPushResult:
    """Test PushResult model."""

    def test_creation(self):
        result = PushResult(total=10, uploaded=8, skipped=2)
        assert result.errors == []

    def test_with_errors(self):
        result = PushResult(
            total=5,
            uploaded=3,
            skipped=1,
            errors=[{"session_id": "s1", "error": "timeout"}],
        )
        assert len(result.errors) == 1


class TestPullRequest:
    """Test PullRequest model."""

    def test_defaults(self):
        req = PullRequest(repo_id="org/dataset")
        assert req.force_refresh is False

    def test_force_refresh(self):
        req = PullRequest(repo_id="org/dataset", force_refresh=True)
        assert req.force_refresh is True


class TestPullResult:
    """Test PullResult model."""

    def test_creation(self):
        result = PullResult(
            repo_id="org/dataset", sessions_imported=10, messages_imported=200, skipped=3
        )
        assert result.sessions_imported == 10


class TestRemoteSessionsQuery:
    """Test RemoteSessionsQuery model."""

    def test_defaults(self):
        query = RemoteSessionsQuery()
        assert query.project_id is None
        assert query.source_type is None
        assert query.limit == 100
        assert query.offset == 0

    def test_with_filters(self):
        query = RemoteSessionsQuery(
            project_id="proj-1", source_type=DataSourceType.MONGODB, limit=50, offset=10
        )
        assert query.project_id == "proj-1"
        assert query.limit == 50


class TestToolCall:
    """Test ToolCall model."""

    def test_minimal(self):
        tc = ToolCall(name="Bash")
        assert tc.id == ""
        assert tc.name == "Bash"
        assert tc.input is None
        assert tc.output is None
        assert tc.is_error is False

    def test_full(self):
        tc = ToolCall(
            id="tool-123",
            name="Read",
            input={"file_path": "/tmp/test.py"},
            output="file contents here",
            is_error=False,
        )
        assert tc.id == "tool-123"
        assert tc.input["file_path"] == "/tmp/test.py"

    def test_error_tool_call(self):
        tc = ToolCall(name="Bash", output="command not found", is_error=True)
        assert tc.is_error is True

    def test_string_input(self):
        tc = ToolCall(name="Bash", input="ls -la")
        assert tc.input == "ls -la"


class TestTokenUsage:
    """Test TokenUsage model."""

    def test_defaults(self):
        usage = TokenUsage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cache_creation_tokens == 0
        assert usage.cache_read_tokens == 0

    def test_with_values(self):
        usage = TokenUsage(
            input_tokens=1000,
            output_tokens=500,
            cache_creation_tokens=200,
            cache_read_tokens=800,
        )
        assert usage.input_tokens == 1000
        assert usage.cache_read_tokens == 800


class TestContentBlock:
    """Test ContentBlock model."""

    def test_text_block(self):
        block = ContentBlock(type="text", text="Hello world")
        assert block.type == "text"
        assert block.text == "Hello world"
        assert block.thinking is None

    def test_thinking_block(self):
        block = ContentBlock(type="thinking", thinking="Let me analyze this...")
        assert block.type == "thinking"
        assert block.thinking == "Let me analyze this..."

    def test_tool_use_block(self):
        block = ContentBlock(
            type="tool_use",
            id="tu-123",
            name="Bash",
            input={"command": "ls"},
        )
        assert block.name == "Bash"
        assert block.id == "tu-123"

    def test_tool_result_block(self):
        block = ContentBlock(
            type="tool_result",
            tool_use_id="tu-123",
            content="output here",
            is_error=False,
        )
        assert block.tool_use_id == "tu-123"
        assert block.is_error is False

    def test_all_fields_none_by_default(self):
        block = ContentBlock(type="text")
        assert block.text is None
        assert block.thinking is None
        assert block.id is None
        assert block.name is None
        assert block.input is None
        assert block.tool_use_id is None
        assert block.content is None
        assert block.is_error is None


class TestMessage:
    """Test Message model."""

    def test_minimal(self):
        msg = Message(uuid="m1", session_id="s1", role="user", type="user")
        assert msg.uuid == "m1"
        assert msg.content == ""
        assert msg.model == ""
        assert msg.is_sidechain is False
        assert msg.usage is None
        assert msg.tool_calls == []

    def test_string_content(self):
        msg = Message(uuid="m1", session_id="s1", role="user", type="user", content="Hello")
        assert msg.content == "Hello"

    def test_block_content(self):
        blocks = [ContentBlock(type="text", text="Hi")]
        msg = Message(
            uuid="m1", session_id="s1", role="assistant", type="assistant", content=blocks
        )
        assert isinstance(msg.content, list)
        assert msg.content[0].text == "Hi"

    def test_with_usage(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        msg = Message(uuid="m1", session_id="s1", role="assistant", type="assistant", usage=usage)
        assert msg.usage.input_tokens == 100

    def test_with_tool_calls(self):
        tc = ToolCall(name="Read", input={"file_path": "/tmp/f.py"})
        msg = Message(
            uuid="m1",
            session_id="s1",
            role="assistant",
            type="assistant",
            tool_calls=[tc],
        )
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "Read"

    def test_sidechain_message(self):
        msg = Message(
            uuid="m1", session_id="s1", role="assistant", type="assistant", is_sidechain=True
        )
        assert msg.is_sidechain is True


class TestToolUsageStat:
    """Test ToolUsageStat model."""

    def test_creation(self):
        stat = ToolUsageStat(tool_name="Bash", call_count=50, avg_per_session=2.5, error_rate=0.1)
        assert stat.tool_name == "Bash"
        assert stat.error_rate == 0.1


class TestTimePattern:
    """Test TimePattern model."""

    def test_creation(self):
        tp = TimePattern(
            hour_distribution={9: 5, 10: 8},
            weekday_distribution={0: 10, 4: 15},
            avg_session_duration=1800.0,
            avg_messages_per_session=25.0,
        )
        assert tp.hour_distribution[10] == 8
        assert tp.avg_session_duration == 1800.0


class TestUserPreferenceResult:
    """Test UserPreferenceResult model."""

    def test_creation(self):
        result = UserPreferenceResult(
            source_name="local",
            session_count=100,
            tool_usage=[],
            time_pattern=TimePattern(
                hour_distribution={},
                weekday_distribution={},
                avg_session_duration=0.0,
                avg_messages_per_session=0.0,
            ),
            model_distribution={"claude-sonnet-4-6": 80},
            project_distribution={"MyProject": 50},
            top_tool_sequences=[["Read", "Edit"]],
        )
        assert result.session_count == 100
        assert len(result.top_tool_sequences) == 1


class TestAgentBehaviorResult:
    """Test AgentBehaviorResult model."""

    def test_creation(self):
        result = AgentBehaviorResult(
            model="claude-sonnet-4-6",
            session_count=50,
            avg_tool_calls_per_session=8.5,
            avg_tokens_per_session=15000.0,
            tool_selection_variability=0.75,
            common_tool_patterns=[{"pattern": ["Read", "Edit"], "count": 30}],
        )
        assert result.thinking_action_consistency is None
        assert result.tool_selection_variability == 0.75

    def test_with_thinking_consistency(self):
        result = AgentBehaviorResult(
            model="claude-sonnet-4-6",
            session_count=10,
            avg_tool_calls_per_session=5.0,
            avg_tokens_per_session=10000.0,
            tool_selection_variability=0.5,
            common_tool_patterns=[],
            thinking_action_consistency=0.85,
        )
        assert result.thinking_action_consistency == 0.85
