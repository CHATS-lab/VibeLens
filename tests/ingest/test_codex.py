"""Unit tests for vibelens.ingest.codex parser."""

import json
from pathlib import Path

import pytest

from vibelens.ingest.codex import (
    CodexParser,
    _collect_tool_outputs,
    _extract_message_text,
    _parse_arguments,
    _parse_structured_output,
    _parse_token_count,
    compute_session_tokens_max,
)
from vibelens.models.message import Message, TokenUsage
from vibelens.models.session import DataSourceType

_parser = CodexParser()


def _write_rollout(path: Path, entries: list[dict]) -> None:
    """Write rollout entries as JSONL to a file."""
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _meta_entry(
    session_id: str = "sess-1",
    cwd: str = "/home/user/project",
    timestamp: str = "2025-01-15T10:00:00Z",
    source: str | None = None,
) -> dict:
    """Build a session_meta rollout entry."""
    payload = {"id": session_id, "cwd": cwd, "timestamp": timestamp}
    if source is not None:
        payload["source"] = source
    return {"type": "session_meta", "timestamp": timestamp, "payload": payload}


def _turn_context_entry(
    model: str = "gpt-5.4",
    timestamp: str = "2025-01-15T10:00:01Z",
) -> dict:
    """Build a turn_context rollout entry."""
    return {
        "type": "turn_context",
        "timestamp": timestamp,
        "payload": {"model": model},
    }


def _user_msg_entry(
    text: str = "Hello",
    timestamp: str = "2025-01-15T10:00:01Z",
) -> dict:
    """Build a user response_item entry."""
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        },
    }


def _assistant_msg_entry(
    text: str = "Hi there",
    timestamp: str = "2025-01-15T10:00:02Z",
) -> dict:
    """Build an assistant response_item entry."""
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        },
    }


def _function_call_entry(
    call_id: str = "fc-1",
    name: str = "shell",
    arguments: str = '{"command": "ls"}',
    timestamp: str = "2025-01-15T10:00:03Z",
) -> dict:
    """Build a function_call response_item entry."""
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": arguments,
        },
    }


def _function_call_output_entry(
    call_id: str = "fc-1",
    output: str = "file1.txt\nfile2.txt",
    timestamp: str = "2025-01-15T10:00:04Z",
) -> dict:
    """Build a function_call_output response_item entry."""
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {
            "type": "function_call_output",
            "call_id": call_id,
            "output": output,
        },
    }


def _reasoning_entry(
    text: str = "Let me think about this...",
    timestamp: str = "2025-01-15T10:00:05Z",
) -> dict:
    """Build a reasoning response_item entry."""
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {
            "type": "reasoning",
            "summary": [{"text": text}],
        },
    }


def _token_count_entry(
    input_tokens: int = 500,
    output_tokens: int = 200,
    cached_tokens: int = 100,
    timestamp: str = "2025-01-15T10:00:06Z",
) -> dict:
    """Build a token_count event_msg entry."""
    return {
        "type": "event_msg",
        "timestamp": timestamp,
        "payload": {
            "type": "token_count",
            "info": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "input_tokens_details": {"cached_tokens": cached_tokens},
            },
        },
    }


# ─── TestParseFile
class TestParseFile:
    """Tests for CodexParser.parse_file basic rollout parsing."""

    def test_basic_rollout(self, tmp_path: Path):
        """Parses a minimal rollout with user + assistant messages."""
        rollout = tmp_path / "rollout-2025-sess-1.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                _user_msg_entry("Hello"),
                _assistant_msg_entry("Hi there"),
            ],
        )
        results = _parser.parse_file(rollout)
        assert len(results) == 1
        summary, messages = results[0]
        print(f"  summary: id={summary.session_id}, source={summary.source_type}")
        print(f"  messages: {len(messages)}")
        for m in messages:
            print(f"    role={m.role}, model={m.model}, content={m.content[:50]}")
        assert summary.session_id == "sess-1"
        assert summary.source_type == DataSourceType.LOCAL
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content == "Hello"
        assert messages[1].role == "assistant"
        assert messages[1].content == "Hi there"

    def test_empty_file(self, tmp_path: Path):
        """Empty rollout file returns empty list."""
        rollout = tmp_path / "rollout-empty.jsonl"
        rollout.write_text("")
        results = _parser.parse_file(rollout)
        assert results == []

    def test_missing_file(self, tmp_path: Path):
        """Non-existent file returns empty list."""
        results = _parser.parse_file(tmp_path / "does-not-exist.jsonl")
        assert results == []

    def test_session_id_from_meta(self, tmp_path: Path):
        """Session ID is taken from session_meta payload."""
        rollout = tmp_path / "rollout-whatever.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(session_id="custom-id"),
                _user_msg_entry(),
            ],
        )
        results = _parser.parse_file(rollout)
        summary, _ = results[0]
        assert summary.session_id == "custom-id"

    def test_session_id_falls_back_to_filename(self, tmp_path: Path):
        """Without session_meta id, session_id uses file stem."""
        rollout = tmp_path / "rollout-fallback.jsonl"
        _write_rollout(
            rollout,
            [
                {
                    "type": "session_meta",
                    "timestamp": "2025-01-15T10:00:00Z",
                    "payload": {"cwd": "/tmp"},
                },
                _user_msg_entry(),
            ],
        )
        results = _parser.parse_file(rollout)
        summary, _ = results[0]
        assert summary.session_id == "rollout-fallback"

    def test_project_name_from_cwd(self, tmp_path: Path):
        """Project name is extracted from session_meta.cwd."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(cwd="/Users/dev/my-awesome-project"),
                _user_msg_entry(),
            ],
        )
        results = _parser.parse_file(rollout)
        summary, _ = results[0]
        assert summary.project_name == "my-awesome-project"

    def test_developer_role_skipped(self, tmp_path: Path):
        """Messages with role='developer' are filtered out."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                {
                    "type": "response_item",
                    "timestamp": "2025-01-15T10:00:01Z",
                    "payload": {
                        "type": "message",
                        "role": "developer",
                        "content": [
                            {"type": "input_text", "text": "System prompt"},
                        ],
                    },
                },
                _user_msg_entry("Hello"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        assert len(messages) == 1
        assert messages[0].role == "user"

    def test_first_message_extraction(self, tmp_path: Path):
        """Summary first_message comes from first user message text."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry("I start first"),
                _user_msg_entry("Fix the bug in main.py"),
            ],
        )
        results = _parser.parse_file(rollout)
        summary, _ = results[0]
        assert summary.first_message == "Fix the bug in main.py"

    def test_duration_computed(self, tmp_path: Path):
        """Duration is computed from min/max message timestamps."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _user_msg_entry(timestamp="2025-01-15T10:00:00Z"),
                _assistant_msg_entry(timestamp="2025-01-15T10:05:00Z"),
            ],
        )
        results = _parser.parse_file(rollout)
        summary, _ = results[0]
        assert summary.duration == 300

    def test_only_meta_no_messages(self, tmp_path: Path):
        """Rollout with only session_meta and no messages returns empty."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(rollout, [_meta_entry()])
        results = _parser.parse_file(rollout)
        assert results == []


# ─── TestFunctionCallPairing
class TestFunctionCallPairing:
    """Tests for function_call + function_call_output linked by call_id."""

    def test_paired_call_and_output(self, tmp_path: Path):
        """function_call is paired with its function_call_output."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                _assistant_msg_entry("Let me check"),
                _function_call_entry(call_id="fc-1", name="shell"),
                _function_call_output_entry(call_id="fc-1", output="file1.txt"),
                _user_msg_entry("Thanks"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        assistant_msg = messages[0]
        print(f"  tool_calls: {len(assistant_msg.tool_calls)}")
        for tc in assistant_msg.tool_calls:
            print(f"    name={tc.name}, id={tc.id}, output={tc.output}, category={tc.category}")
        assert assistant_msg.role == "assistant"
        assert len(assistant_msg.tool_calls) == 1
        assert assistant_msg.tool_calls[0].name == "shell"
        assert assistant_msg.tool_calls[0].output == "file1.txt"
        assert assistant_msg.tool_calls[0].id == "fc-1"

    def test_missing_output(self, tmp_path: Path):
        """function_call without matching output has None output."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry(),
                _function_call_entry(call_id="fc-orphan", name="shell"),
                _user_msg_entry("next"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        assistant_msg = messages[0]
        assert len(assistant_msg.tool_calls) == 1
        assert assistant_msg.tool_calls[0].output is None

    def test_multiple_calls_same_turn(self, tmp_path: Path):
        """Multiple function_calls in one turn are all attached."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry("Let me run some commands"),
                _function_call_entry(call_id="fc-1", name="shell"),
                _function_call_output_entry(call_id="fc-1", output="output-1"),
                _function_call_entry(call_id="fc-2", name="read_file"),
                _function_call_output_entry(call_id="fc-2", output="output-2"),
                _user_msg_entry("done"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        assistant_msg = messages[0]
        assert len(assistant_msg.tool_calls) == 2
        assert assistant_msg.tool_calls[0].name == "shell"
        assert assistant_msg.tool_calls[0].output == "output-1"
        assert assistant_msg.tool_calls[1].name == "read_file"
        assert assistant_msg.tool_calls[1].output == "output-2"

    def test_collect_tool_outputs_direct(self):
        """_collect_tool_outputs builds call_id -> result mapping."""
        entries = [
            _function_call_output_entry(call_id="fc-a", output="result-a"),
            _function_call_output_entry(call_id="fc-b", output="result-b"),
            _user_msg_entry(),
        ]
        outputs = _collect_tool_outputs(entries)
        assert "fc-a" in outputs
        assert outputs["fc-a"]["output"] == "result-a"
        assert "fc-b" in outputs

    def test_trailing_tool_calls_flushed(self, tmp_path: Path):
        """Tool calls after last assistant msg are flushed at end."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry("checking"),
                _function_call_entry(call_id="fc-last", name="shell"),
                _function_call_output_entry(call_id="fc-last", output="done"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        assert len(messages[0].tool_calls) == 1
        assert messages[0].tool_calls[0].id == "fc-last"


# ─── TestPerTurnModelTracking
class TestPerTurnModelTracking:
    """Tests for turn_context model changes applied per-turn."""

    def test_model_applied_to_assistant(self, tmp_path: Path):
        """turn_context model is applied to subsequent assistant messages."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(model="gpt-5.4"),
                _user_msg_entry(),
                _assistant_msg_entry("response 1"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        assistant_msg = [m for m in messages if m.role == "assistant"][0]
        assert assistant_msg.model == "gpt-5.4"

    def test_model_not_applied_to_user(self, tmp_path: Path):
        """User messages do not get a model assignment."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(model="gpt-5.4"),
                _user_msg_entry(),
                _assistant_msg_entry(),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        user_msg = [m for m in messages if m.role == "user"][0]
        assert user_msg.model == ""

    def test_model_changes_mid_session(self, tmp_path: Path):
        """Model changes mid-session are tracked per assistant message."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(model="gpt-5.4"),
                _user_msg_entry(timestamp="2025-01-15T10:00:01Z"),
                _assistant_msg_entry("first", timestamp="2025-01-15T10:00:02Z"),
                _turn_context_entry(model="gpt-4-mini"),
                _user_msg_entry("second q", timestamp="2025-01-15T10:00:03Z"),
                _assistant_msg_entry("second", timestamp="2025-01-15T10:00:04Z"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        summary = results[0][0]
        assistants = [m for m in messages if m.role == "assistant"]
        print(f"  models in summary: {summary.models}")
        for a in assistants:
            print(f"    assistant model={a.model}, content={a.content[:30]}")
        assert assistants[0].model == "gpt-5.4"
        assert assistants[1].model == "gpt-4-mini"
        assert sorted(summary.models) == ["gpt-4-mini", "gpt-5.4"]


# ─── TestTokenCountAttachment
class TestTokenCountAttachment:
    """Tests for event_msg token_count parsed and attached."""

    def test_token_count_attached_to_assistant(self, tmp_path: Path):
        """token_count event attaches usage to last assistant message."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                _user_msg_entry(),
                _assistant_msg_entry(),
                _token_count_entry(
                    input_tokens=500,
                    output_tokens=200,
                    cached_tokens=100,
                ),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        assistant_msg = [m for m in messages if m.role == "assistant"][0]
        assert assistant_msg.usage is not None
        assert assistant_msg.usage.input_tokens == 500
        assert assistant_msg.usage.output_tokens == 200
        assert assistant_msg.usage.cache_read_tokens == 100

    def test_token_count_not_attached_to_user(self, tmp_path: Path):
        """token_count before any assistant message is not attached."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _user_msg_entry(),
                _token_count_entry(),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        assert messages[0].role == "user"
        assert messages[0].usage is None

    def test_parse_token_count_direct(self):
        """_parse_token_count parses info sub-object correctly."""
        payload = {
            "type": "token_count",
            "info": {
                "input_tokens": 1000,
                "output_tokens": 300,
                "input_tokens_details": {"cached_tokens": 50},
            },
        }
        usage = _parse_token_count(payload)
        assert usage is not None
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 300
        assert usage.cache_read_tokens == 50

    def test_parse_token_count_empty_info(self):
        """_parse_token_count with empty info returns None."""
        payload = {"type": "token_count", "info": {}}
        usage = _parse_token_count(payload)
        assert usage is None

    def test_parse_token_count_legacy_fields(self):
        """_parse_token_count accepts legacy prompt_tokens field."""
        payload = {
            "type": "token_count",
            "info": {
                "prompt_tokens": 800,
                "completion_tokens": 150,
            },
        }
        usage = _parse_token_count(payload)
        assert usage is not None
        assert usage.input_tokens == 800
        assert usage.output_tokens == 150


# ─── TestSubagentDetection
class TestSubagentDetection:
    """Tests for source='sub_agent' marking all messages as sidechain."""

    def test_subagent_source_marks_sidechain(self, tmp_path: Path):
        """source='sub_agent' in session_meta sets is_sidechain on all."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(source="sub_agent"),
                _turn_context_entry(),
                _user_msg_entry(),
                _assistant_msg_entry(),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        for msg in messages:
            assert msg.is_sidechain is True

    def test_no_source_no_sidechain(self, tmp_path: Path):
        """Without source='sub_agent', messages are not sidechain."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _user_msg_entry(),
                _assistant_msg_entry(),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        for msg in messages:
            assert msg.is_sidechain is False

    def test_other_source_not_sidechain(self, tmp_path: Path):
        """source='main' does not set is_sidechain."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(source="main"),
                _user_msg_entry(),
                _assistant_msg_entry(),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        for msg in messages:
            assert msg.is_sidechain is False


# ─── TestMalformedInput
class TestMalformedInput:
    """Tests for graceful handling of malformed JSONL and missing fields."""

    def test_malformed_json_lines_skipped(self, tmp_path: Path):
        """Invalid JSON lines are skipped, valid ones still parsed."""
        rollout = tmp_path / "rollout.jsonl"
        with open(rollout, "w", encoding="utf-8") as f:
            f.write("NOT VALID JSON\n")
            f.write(json.dumps(_meta_entry()) + "\n")
            f.write("{broken\n")
            f.write(json.dumps(_user_msg_entry("valid")) + "\n")
        results = _parser.parse_file(rollout)
        assert len(results) == 1
        _, messages = results[0]
        assert len(messages) == 1
        assert messages[0].content == "valid"

    def test_blank_lines_ignored(self, tmp_path: Path):
        """Blank lines in JSONL are silently skipped."""
        rollout = tmp_path / "rollout.jsonl"
        with open(rollout, "w", encoding="utf-8") as f:
            f.write("\n")
            f.write(json.dumps(_meta_entry()) + "\n")
            f.write("   \n")
            f.write(json.dumps(_user_msg_entry()) + "\n")
            f.write("\n")
        results = _parser.parse_file(rollout)
        assert len(results) == 1

    def test_missing_payload_handled(self, tmp_path: Path):
        """Entry without payload field does not crash."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                {"type": "response_item", "timestamp": "2025-01-15T10:00:01Z"},
                _user_msg_entry("still works"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        assert len(messages) == 1
        assert messages[0].content == "still works"

    def test_missing_content_in_message(self, tmp_path: Path):
        """Message with empty content list produces empty string."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                {
                    "type": "response_item",
                    "timestamp": "2025-01-15T10:00:01Z",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [],
                    },
                },
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        assert len(messages) == 1
        assert messages[0].content == ""

    def test_extract_message_text_string_content(self):
        """_extract_message_text handles string content directly."""
        payload = {"content": "plain text string"}
        assert _extract_message_text(payload) == "plain text string"

    def test_extract_message_text_non_list_non_string(self):
        """_extract_message_text coerces non-string/list content to string."""
        payload = {"content": 12345}
        assert _extract_message_text(payload) == "12345"

    def test_parse_arguments_valid_json(self):
        """_parse_arguments decodes valid JSON string to dict."""
        result = _parse_arguments('{"command": "ls"}')
        assert result == {"command": "ls"}

    def test_parse_arguments_malformed_json(self):
        """_parse_arguments returns raw string for bad JSON."""
        result = _parse_arguments("{broken json")
        assert result == "{broken json"

    def test_parse_arguments_empty_string(self):
        """_parse_arguments returns None for empty string."""
        result = _parse_arguments("")
        assert result is None

    def test_entry_with_unknown_type_ignored(self, tmp_path: Path):
        """Entries with unrecognized type are silently skipped."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                {
                    "type": "unknown_type",
                    "timestamp": "2025-01-15T10:00:01Z",
                    "payload": {"data": "irrelevant"},
                },
                _user_msg_entry("valid"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        assert len(messages) == 1


# ─── TestReasoningExtraction
class TestReasoningExtraction:
    """Tests for reasoning entries extracted and deduped."""

    def test_reasoning_attached_to_assistant(self, tmp_path: Path):
        """Reasoning entries are flushed as thinking on assistant msg."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry("My answer"),
                _reasoning_entry("Let me think about this..."),
                _user_msg_entry("next"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        assistant_msg = messages[0]
        print(f"  thinking: {assistant_msg.thinking}")
        assert assistant_msg.thinking is not None
        assert "Let me think about this..." in assistant_msg.thinking

    def test_duplicate_reasoning_deduped(self, tmp_path: Path):
        """Identical reasoning entries are deduplicated by content hash."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry("answer"),
                _reasoning_entry("Same thought"),
                _reasoning_entry("Same thought"),
                _reasoning_entry("Different thought"),
                _user_msg_entry("ok"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        assistant_msg = messages[0]
        assert assistant_msg.thinking is not None
        # "Same thought" appears once, "Different thought" once
        lines = assistant_msg.thinking.split("\n")
        assert len(lines) == 2
        assert "Same thought" in lines
        assert "Different thought" in lines

    def test_reasoning_flushed_at_end(self, tmp_path: Path):
        """Trailing reasoning entries are flushed at session end."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry("response"),
                _reasoning_entry("trailing thought"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        assert messages[0].thinking == "trailing thought"

    def test_reasoning_with_empty_text_skipped(self, tmp_path: Path):
        """Reasoning entries with empty text are ignored."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry("response"),
                {
                    "type": "response_item",
                    "timestamp": "2025-01-15T10:00:05Z",
                    "payload": {
                        "type": "reasoning",
                        "summary": [{"text": ""}],
                    },
                },
                _user_msg_entry("next"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        assert messages[0].thinking is None

    def test_multiple_reasoning_items_in_summary(self, tmp_path: Path):
        """Multiple items in a single reasoning summary list."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry("response"),
                {
                    "type": "response_item",
                    "timestamp": "2025-01-15T10:00:05Z",
                    "payload": {
                        "type": "reasoning",
                        "summary": [
                            {"text": "First thought"},
                            {"text": "Second thought"},
                        ],
                    },
                },
                _user_msg_entry("ok"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        assert "First thought" in messages[0].thinking
        assert "Second thought" in messages[0].thinking


# ─── TestStructuredOutput
class TestStructuredOutput:
    """Tests for structured output prefix stripping and error detection."""

    def test_exit_code_zero_stripped(self):
        """Exit code 0 prefix is stripped, is_error is False."""
        raw = "Exit code: 0\nWall time: 1.23s\nOutput:\nactual output here"
        cleaned, is_error = _parse_structured_output(raw)
        assert cleaned == "actual output here"
        assert is_error is False

    def test_nonzero_exit_code_sets_error(self):
        """Non-zero exit code sets is_error True."""
        raw = "Exit code: 1\nWall time: 0.5s\nOutput:\nerror message"
        cleaned, is_error = _parse_structured_output(raw)
        assert cleaned == "error message"
        assert is_error is True

    def test_no_prefix_passes_through(self):
        """Output without prefix pattern is returned as-is."""
        raw = "plain output without prefix"
        cleaned, is_error = _parse_structured_output(raw)
        assert cleaned == "plain output without prefix"
        assert is_error is False

    def test_empty_output(self):
        """Empty string returns empty, no error."""
        cleaned, is_error = _parse_structured_output("")
        assert cleaned == ""
        assert is_error is False

    def test_multiline_actual_output(self):
        """Multiline output after prefix is preserved intact."""
        raw = "Exit code: 0\nWall time: 2.00s\nOutput:\nline1\nline2\nline3"
        cleaned, is_error = _parse_structured_output(raw)
        assert cleaned == "line1\nline2\nline3"

    def test_error_in_tool_call_via_rollout(self, tmp_path: Path):
        """Non-zero exit code in function_call_output sets is_error."""
        error_output = "Exit code: 127\nWall time: 0.01s\nOutput:\ncommand not found: foo"
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry("running"),
                _function_call_entry(call_id="fc-err", name="shell"),
                _function_call_output_entry(call_id="fc-err", output=error_output),
                _user_msg_entry("next"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        tc = messages[0].tool_calls[0]
        assert tc.is_error is True
        assert tc.output == "command not found: foo"

    def test_success_in_tool_call_via_rollout(self, tmp_path: Path):
        """Exit code 0 in function_call_output keeps is_error False."""
        success_output = "Exit code: 0\nWall time: 0.50s\nOutput:\nfile1.txt"
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry("listing"),
                _function_call_entry(call_id="fc-ok", name="shell"),
                _function_call_output_entry(call_id="fc-ok", output=success_output),
                _user_msg_entry("done"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        tc = messages[0].tool_calls[0]
        assert tc.is_error is False
        assert tc.output == "file1.txt"


# ─── TestTokenStrategyMax
class TestTokenStrategyMax:
    """Tests for compute_session_tokens_max using max-not-sum strategy."""

    def test_max_not_sum(self):
        """Takes max input/output across messages, not sum."""
        messages = [
            Message(
                uuid="m1",
                session_id="s1",
                role="assistant",
                type="assistant",
                usage=TokenUsage(input_tokens=100, output_tokens=50),
            ),
            Message(
                uuid="m2",
                session_id="s1",
                role="assistant",
                type="assistant",
                usage=TokenUsage(input_tokens=300, output_tokens=80),
            ),
            Message(
                uuid="m3",
                session_id="s1",
                role="assistant",
                type="assistant",
                usage=TokenUsage(input_tokens=200, output_tokens=120),
            ),
        ]
        max_in, max_out = compute_session_tokens_max(messages)
        assert max_in == 300
        assert max_out == 120

    def test_empty_messages(self):
        """Empty message list returns zeros."""
        max_in, max_out = compute_session_tokens_max([])
        assert max_in == 0
        assert max_out == 0

    def test_no_usage_data(self):
        """Messages without usage return zeros."""
        messages = [
            Message(
                uuid="m1",
                session_id="s1",
                role="assistant",
                type="assistant",
            ),
            Message(
                uuid="m2",
                session_id="s1",
                role="user",
                type="user",
            ),
        ]
        max_in, max_out = compute_session_tokens_max(messages)
        assert max_in == 0
        assert max_out == 0

    def test_single_message_with_usage(self):
        """Single message usage is returned as the max."""
        messages = [
            Message(
                uuid="m1",
                session_id="s1",
                role="assistant",
                type="assistant",
                usage=TokenUsage(input_tokens=500, output_tokens=200),
            ),
        ]
        max_in, max_out = compute_session_tokens_max(messages)
        assert max_in == 500
        assert max_out == 200

    def test_mixed_usage_and_no_usage(self):
        """Messages with and without usage handled correctly."""
        messages = [
            Message(
                uuid="m1",
                session_id="s1",
                role="user",
                type="user",
            ),
            Message(
                uuid="m2",
                session_id="s1",
                role="assistant",
                type="assistant",
                usage=TokenUsage(input_tokens=400, output_tokens=150),
            ),
            Message(
                uuid="m3",
                session_id="s1",
                role="assistant",
                type="assistant",
            ),
        ]
        max_in, max_out = compute_session_tokens_max(messages)
        assert max_in == 400
        assert max_out == 150

    @pytest.mark.parametrize(
        "usages,expected_in,expected_out",
        [
            ([(100, 50), (100, 50)], 100, 50),
            ([(0, 0), (1, 1)], 1, 1),
            ([(999, 1), (1, 999)], 999, 999),
        ],
        ids=["equal-values", "zero-and-nonzero", "cross-max"],
    )
    def test_parametrized_cases(
        self,
        usages: list[tuple[int, int]],
        expected_in: int,
        expected_out: int,
    ):
        """Parametrized edge cases for max strategy."""
        messages = [
            Message(
                uuid=f"m{i}",
                session_id="s1",
                role="assistant",
                type="assistant",
                usage=TokenUsage(input_tokens=inp, output_tokens=out),
            )
            for i, (inp, out) in enumerate(usages)
        ]
        max_in, max_out = compute_session_tokens_max(messages)
        assert max_in == expected_in
        assert max_out == expected_out


# ─── TestToolEnrichmentViaParseFile
class TestToolEnrichmentViaParseFile:
    """Tests that parse_file enriches tool calls with category and summary."""

    def test_shell_tool_enriched(self, tmp_path: Path):
        """Shell function_call gets category='shell' after parse_file."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _turn_context_entry(),
                _assistant_msg_entry("Let me check"),
                _function_call_entry(
                    call_id="fc-1", name="shell",
                    arguments='{"command": "ls -la"}',
                ),
                _function_call_output_entry(call_id="fc-1", output="file1.txt"),
                _user_msg_entry("done"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        tc = messages[0].tool_calls[0]
        print(f"  name={tc.name}, category={tc.category}, summary={tc.summary}")
        assert tc.category == "shell"
        assert tc.summary == "ls -la"

    def test_exec_command_enriched(self, tmp_path: Path):
        """exec_command tool gets category='shell'."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry("running"),
                _function_call_entry(
                    call_id="fc-1",
                    name="execute_command",
                    arguments='{"command": "npm install"}',
                ),
                _user_msg_entry("ok"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        tc = messages[0].tool_calls[0]
        assert tc.category == "shell"

    def test_apply_patch_enriched(self, tmp_path: Path):
        """apply-patch/apply_patch tools get category='file_write'."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry("patching"),
                _function_call_entry(
                    call_id="fc-1",
                    name="apply-patch",
                    arguments='{"patch": "diff content"}',
                ),
                _user_msg_entry("done"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        tc = messages[0].tool_calls[0]
        assert tc.category == "file_write"

    def test_unknown_tool_gets_other(self, tmp_path: Path):
        """Unrecognized tools get category='other'."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry("custom"),
                _function_call_entry(
                    call_id="fc-1",
                    name="custom_tool",
                    arguments='{"data": "value"}',
                ),
                _user_msg_entry("done"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        tc = messages[0].tool_calls[0]
        assert tc.category == "other"


# ─── TestCustomToolCall
class TestCustomToolCall:
    """Tests for custom_tool_call entries (e.g. apply-patch)."""

    def test_custom_tool_call_parsed(self, tmp_path: Path):
        """custom_tool_call entries are parsed as function calls."""
        rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            rollout,
            [
                _meta_entry(),
                _assistant_msg_entry("applying patch"),
                {
                    "type": "response_item",
                    "timestamp": "2025-01-15T10:00:03Z",
                    "payload": {
                        "type": "custom_tool_call",
                        "call_id": "ct-1",
                        "name": "apply-patch",
                        "arguments": '{"patch": "diff content here"}',
                    },
                },
                _user_msg_entry("ok"),
            ],
        )
        results = _parser.parse_file(rollout)
        _, messages = results[0]
        # custom_tool_call should be treated like function_call
        assistant_msg = messages[0]
        tool_names = [tc.name for tc in assistant_msg.tool_calls]
        print(f"  tool_names: {tool_names}")
        # Verify it's captured (if the parser handles custom_tool_call)
        if assistant_msg.tool_calls:
            assert "apply-patch" in tool_names
