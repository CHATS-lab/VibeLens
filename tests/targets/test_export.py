"""Unit tests for vibelens.targets.export serializer."""

from datetime import UTC, datetime

from vibelens.models.message import Message, TokenUsage, ToolCall
from vibelens.models.session import SessionDetail, SessionSummary, SubAgentSession
from vibelens.targets.export import VIBELENS_EXPORT_VERSION, serialize_export


def _make_detail(
    agent_format: str = "codex",
    sub_sessions: list[SubAgentSession] | None = None,
    messages: list[Message] | None = None,
) -> SessionDetail:
    """Build a minimal SessionDetail for testing."""
    summary = SessionSummary(
        session_id="sess-001",
        project_id="proj-001",
        project_name="my-project",
        timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC),
        duration=300,
        message_count=2,
        tool_call_count=1,
        models=["gpt-5.4"],
        first_message="Hello",
        agent_format=agent_format,
    )
    if messages is None:
        messages = [
            Message(
                uuid="msg-u1",
                session_id="sess-001",
                role="user",
                type="user",
                content="Hello",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC),
            ),
            Message(
                uuid="msg-a1",
                session_id="sess-001",
                role="assistant",
                type="assistant",
                content="Hi there",
                model="gpt-5.4",
                thinking="Let me think...",
                timestamp=datetime(2025, 6, 1, 12, 0, 5, tzinfo=UTC),
                usage=TokenUsage(input_tokens=100, output_tokens=50),
                tool_calls=[
                    ToolCall(id="tc-1", name="shell", input={"command": "ls"}, output="file.txt")
                ],
            ),
        ]
    return SessionDetail(
        summary=summary,
        messages=messages,
        sub_sessions=sub_sessions or [],
    )


class TestSerializeExport:
    """Tests for the top-level serialize_export function."""

    def test_version_field(self):
        """Export includes vibelens_version at top level."""
        detail = _make_detail()
        result = serialize_export(detail)
        assert result["vibelens_version"] == VIBELENS_EXPORT_VERSION

    def test_agent_format_field(self):
        """Export includes agent_format from summary."""
        detail = _make_detail(agent_format="codex")
        result = serialize_export(detail)
        assert result["agent_format"] == "codex"

    def test_no_id_field_on_session(self):
        """Session metadata does not include _id."""
        detail = _make_detail()
        result = serialize_export(detail)
        assert "_id" not in result["session"]

    def test_session_id_present(self):
        """Session metadata includes session_id."""
        detail = _make_detail()
        result = serialize_export(detail)
        assert result["session"]["session_id"] == "sess-001"

    def test_no_type_field_on_messages(self):
        """Messages do not include the redundant 'type' field."""
        detail = _make_detail()
        result = serialize_export(detail)
        for msg in result["messages"]:
            assert "type" not in msg

    def test_user_message_omits_assistant_fields(self):
        """User messages omit thinking, tool_calls, usage, and model."""
        detail = _make_detail()
        result = serialize_export(detail)
        user_msg = result["messages"][0]
        assert user_msg["role"] == "user"
        assert "thinking" not in user_msg
        assert "tool_calls" not in user_msg
        assert "usage" not in user_msg
        assert "model" not in user_msg

    def test_assistant_message_includes_fields(self):
        """Assistant messages include model, thinking, usage, tool_calls."""
        detail = _make_detail()
        result = serialize_export(detail)
        assistant_msg = result["messages"][1]
        assert assistant_msg["role"] == "assistant"
        assert assistant_msg["model"] == "gpt-5.4"
        assert assistant_msg["thinking"] == "Let me think..."
        assert assistant_msg["usage"]["input_tokens"] == 100
        assert len(assistant_msg["tool_calls"]) == 1

    def test_assistant_without_thinking_omits_it(self):
        """Assistant message with no thinking omits the field entirely."""
        messages = [
            Message(
                uuid="msg-a1",
                session_id="sess-001",
                role="assistant",
                type="assistant",
                content="Response",
                model="gpt-5.4",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC),
            ),
        ]
        detail = _make_detail(messages=messages)
        result = serialize_export(detail)
        assert "thinking" not in result["messages"][0]

    def test_assistant_without_usage_omits_it(self):
        """Assistant message with no usage omits the field entirely."""
        messages = [
            Message(
                uuid="msg-a1",
                session_id="sess-001",
                role="assistant",
                type="assistant",
                content="Response",
                model="gpt-5.4",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC),
            ),
        ]
        detail = _make_detail(messages=messages)
        result = serialize_export(detail)
        assert "usage" not in result["messages"][0]
        assert "tool_calls" not in result["messages"][0]

    def test_no_session_id_on_messages(self):
        """Messages do not include session_id (implied by envelope)."""
        detail = _make_detail()
        result = serialize_export(detail)
        for msg in result["messages"]:
            assert "session_id" not in msg

    def test_no_is_sidechain_on_messages(self):
        """Messages do not include is_sidechain (implied by nesting)."""
        detail = _make_detail()
        result = serialize_export(detail)
        for msg in result["messages"]:
            assert "is_sidechain" not in msg

    def test_parent_uuid_omitted_when_empty(self):
        """parent_uuid is omitted when empty string."""
        detail = _make_detail()
        result = serialize_export(detail)
        for msg in result["messages"]:
            assert "parent_uuid" not in msg


class TestSubSessions:
    """Tests for hierarchical sub-session serialization."""

    def test_sub_sessions_hierarchical(self):
        """Sub-sessions are nested with their own messages."""
        sub = SubAgentSession(
            agent_id="agent-abc",
            spawn_index=0,
            spawn_tool_call_id="tc-spawn",
            messages=[
                Message(
                    uuid="msg-sub1",
                    session_id="sess-001",
                    role="user",
                    type="user",
                    content="Sub task",
                    timestamp=datetime(2025, 6, 1, 12, 1, 0, tzinfo=UTC),
                ),
            ],
        )
        detail = _make_detail(sub_sessions=[sub])
        result = serialize_export(detail)
        assert len(result["sub_sessions"]) == 1
        sub_out = result["sub_sessions"][0]
        assert sub_out["agent_id"] == "agent-abc"
        assert sub_out["spawn_index"] == 0
        assert len(sub_out["messages"]) == 1
        assert sub_out["messages"][0]["content"] == "Sub task"

    def test_nested_sub_sessions(self):
        """Nested sub-sessions are recursively serialized."""
        inner_sub = SubAgentSession(
            agent_id="agent-inner",
            messages=[
                Message(
                    uuid="msg-inner",
                    session_id="sess-001",
                    role="assistant",
                    type="assistant",
                    content="Inner response",
                    model="gpt-5.4",
                    timestamp=datetime(2025, 6, 1, 12, 2, 0, tzinfo=UTC),
                ),
            ],
        )
        outer_sub = SubAgentSession(
            agent_id="agent-outer",
            messages=[],
            sub_sessions=[inner_sub],
        )
        detail = _make_detail(sub_sessions=[outer_sub])
        result = serialize_export(detail)
        assert len(result["sub_sessions"][0]["sub_sessions"]) == 1
        inner_out = result["sub_sessions"][0]["sub_sessions"][0]
        assert inner_out["agent_id"] == "agent-inner"


class TestResolveAgentFormat:
    """Tests for agent_format resolution and heuristic fallback."""

    def test_explicit_format(self):
        """Uses agent_format field when set."""
        detail = _make_detail(agent_format="gemini")
        result = serialize_export(detail)
        assert result["agent_format"] == "gemini"

    def test_heuristic_from_model_claude(self):
        """Infers claude_code from claude model prefix."""
        detail = _make_detail(agent_format="")
        detail.summary.models = ["claude-sonnet-4-20250514"]
        result = serialize_export(detail)
        assert result["agent_format"] == "claude_code"

    def test_heuristic_from_model_gpt(self):
        """Infers codex from gpt model prefix."""
        detail = _make_detail(agent_format="")
        detail.summary.models = ["gpt-5.4"]
        result = serialize_export(detail)
        assert result["agent_format"] == "codex"

    def test_unknown_when_no_hints(self):
        """Returns 'unknown' when no format field and no model hints."""
        detail = _make_detail(agent_format="")
        detail.summary.models = []
        result = serialize_export(detail)
        assert result["agent_format"] == "unknown"
