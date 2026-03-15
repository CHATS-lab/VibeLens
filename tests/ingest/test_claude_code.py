"""Unit tests for vibelens.ingest.claude_code parser."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vibelens.ingest.base import MAX_FIRST_MESSAGE_LENGTH, BaseParser
from vibelens.ingest.claude_code import (
    ClaudeCodeParser,
    _extract_tool_calls,
    _extract_tool_result_text,
    _parse_content_blocks,
    _parse_usage,
    count_history_entries,
)
from vibelens.models.message import ContentBlock, Message, TokenUsage, ToolCall

_parser = ClaudeCodeParser()


# ─── Fixtures
@pytest.fixture
def claude_dir(tmp_path: Path) -> Path:
    """Create a minimal ~/.claude directory structure."""
    d = tmp_path / ".claude"
    d.mkdir()
    (d / "projects").mkdir()
    return d


@pytest.fixture
def project_dir(claude_dir: Path) -> Path:
    """Create a project subdirectory."""
    p = claude_dir / "projects" / "-Users-Test-MyProject"
    p.mkdir(parents=True)
    return p


def _write_history(claude_dir: Path, entries: list[dict]) -> None:
    """Write entries to history.jsonl."""
    with open(claude_dir / "history.jsonl", "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _write_session(path: Path, entries: list[dict]) -> None:
    """Write entries to a session .jsonl file."""
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


# ─── BaseParser shared methods
class TestBaseParserExtractProjectName:
    def test_normal_path(self):
        assert BaseParser.extract_project_name("/Users/Test/MyProject") == "MyProject"

    def test_nested_path(self):
        assert BaseParser.extract_project_name("/a/b/c/deep") == "deep"

    def test_empty_string(self):
        assert BaseParser.extract_project_name("") == "Unknown"

    def test_root_path(self):
        assert BaseParser.extract_project_name("/") == "Unknown"

    def test_single_component(self):
        assert BaseParser.extract_project_name("project") == "project"


class TestBaseParserEncodeProjectPath:
    def test_normal_path(self):
        assert BaseParser.encode_project_path("/Users/Test/MyProject") == "Users-Test-MyProject"

    def test_empty_string(self):
        assert BaseParser.encode_project_path("") == ""

    def test_no_leading_dash(self):
        result = BaseParser.encode_project_path("/a/b")
        assert not result.startswith("-")

    def test_multiple_slashes(self):
        assert BaseParser.encode_project_path("/a/b/c/d") == "a-b-c-d"


class TestBaseParserTruncateFirstMessage:
    def test_short_message(self):
        assert BaseParser.truncate_first_message("hello") == "hello"

    def test_long_message(self):
        long = "x" * 500
        result = BaseParser.truncate_first_message(long)
        assert len(result) == MAX_FIRST_MESSAGE_LENGTH


# ─── _parse_usage
class TestParseUsage:
    def test_none_input(self):
        assert _parse_usage(None) is None

    def test_empty_dict(self):
        assert _parse_usage({}) is None

    def test_full_usage(self):
        usage = _parse_usage(
            {
                "input_tokens": 1000,
                "output_tokens": 500,
                "cache_creation_input_tokens": 200,
                "cache_read_input_tokens": 800,
            }
        )
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 500
        assert usage.cache_creation_tokens == 200
        assert usage.cache_read_tokens == 800

    def test_partial_usage(self):
        usage = _parse_usage({"input_tokens": 100})
        assert usage.input_tokens == 100
        assert usage.output_tokens == 0
        assert usage.cache_creation_tokens == 0
        assert usage.cache_read_tokens == 0


# ─── _extract_tool_result_text
class TestExtractToolResultText:
    def test_none_content(self):
        assert _extract_tool_result_text(None) == ""

    def test_string_content(self):
        assert _extract_tool_result_text("output text") == "output text"

    def test_list_with_text_blocks(self):
        content = [
            {"type": "text", "text": "line 1"},
            {"type": "text", "text": "line 2"},
        ]
        assert _extract_tool_result_text(content) == "line 1\nline 2"

    def test_list_with_string_items(self):
        content = ["item 1", "item 2"]
        assert _extract_tool_result_text(content) == "item 1\nitem 2"

    def test_list_with_mixed_types(self):
        content = [{"type": "text", "text": "a"}, "b", {"type": "image"}]
        assert _extract_tool_result_text(content) == "a\nb"

    def test_non_standard_type(self):
        assert _extract_tool_result_text(12345) == "12345"

    def test_empty_list(self):
        assert _extract_tool_result_text([]) == ""


# ─── _parse_content_blocks
class TestParseContentBlocks:
    def test_plain_string(self):
        blocks = _parse_content_blocks("Hello world")
        assert len(blocks) == 1
        assert blocks[0].type == "text"
        assert blocks[0].text == "Hello world"

    def test_empty_string(self):
        assert _parse_content_blocks("") == []

    def test_whitespace_string(self):
        assert _parse_content_blocks("   ") == []

    def test_text_block(self):
        blocks = _parse_content_blocks([{"type": "text", "text": "Hello"}])
        assert len(blocks) == 1
        assert blocks[0].text == "Hello"

    def test_thinking_block(self):
        blocks = _parse_content_blocks([{"type": "thinking", "thinking": "hmm"}])
        assert blocks[0].type == "thinking"
        assert blocks[0].thinking == "hmm"

    def test_tool_use_block(self):
        blocks = _parse_content_blocks(
            [
                {
                    "type": "tool_use",
                    "id": "tu-1",
                    "name": "Bash",
                    "input": {"command": "ls"},
                }
            ]
        )
        assert blocks[0].type == "tool_use"
        assert blocks[0].name == "Bash"
        assert blocks[0].id == "tu-1"
        assert blocks[0].input == {"command": "ls"}

    def test_tool_result_block(self):
        blocks = _parse_content_blocks(
            [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu-1",
                    "content": "file contents",
                    "is_error": False,
                }
            ]
        )
        assert blocks[0].tool_use_id == "tu-1"
        assert blocks[0].is_error is False

    def test_multiple_blocks(self):
        blocks = _parse_content_blocks(
            [
                {"type": "thinking", "thinking": "Let me think"},
                {"type": "text", "text": "Here is my answer"},
                {"type": "tool_use", "id": "tu-1", "name": "Read", "input": {}},
            ]
        )
        assert len(blocks) == 3

    def test_non_dict_items_skipped(self):
        blocks = _parse_content_blocks(["not a dict", 42, None])
        assert len(blocks) == 0

    def test_empty_list(self):
        assert _parse_content_blocks([]) == []


# ─── _extract_tool_calls
class TestExtractToolCalls:
    def test_no_tool_use_blocks(self):
        blocks = [ContentBlock(type="text", text="hello")]
        assert _extract_tool_calls(blocks, {}) == []

    def test_tool_use_without_result(self):
        blocks = [ContentBlock(type="tool_use", id="tu-1", name="Bash", input={"command": "ls"})]
        calls = _extract_tool_calls(blocks, {})
        assert len(calls) == 1
        assert calls[0].name == "Bash"
        assert calls[0].output is None
        assert calls[0].is_error is False

    def test_tool_use_with_matching_result(self):
        blocks = [ContentBlock(type="tool_use", id="tu-1", name="Read", input={})]
        results = {"tu-1": {"output": "file content", "is_error": False}}
        calls = _extract_tool_calls(blocks, results)
        assert calls[0].output == "file content"
        assert calls[0].is_error is False

    def test_tool_use_with_error_result(self):
        blocks = [ContentBlock(type="tool_use", id="tu-1", name="Bash", input={})]
        results = {"tu-1": {"output": "command not found", "is_error": True}}
        calls = _extract_tool_calls(blocks, results)
        assert calls[0].is_error is True

    def test_multiple_tool_calls(self):
        blocks = [
            ContentBlock(type="tool_use", id="tu-1", name="Read", input={}),
            ContentBlock(type="text", text="intermediate"),
            ContentBlock(type="tool_use", id="tu-2", name="Edit", input={}),
        ]
        results = {
            "tu-1": {"output": "content", "is_error": False},
            "tu-2": {"output": "edited", "is_error": False},
        }
        calls = _extract_tool_calls(blocks, results)
        assert len(calls) == 2
        assert calls[0].name == "Read"
        assert calls[1].name == "Edit"

    def test_missing_id_defaults_empty(self):
        blocks = [ContentBlock(type="tool_use", name="Bash")]
        calls = _extract_tool_calls(blocks, {})
        assert calls[0].id == ""

    def test_missing_name_defaults_unknown(self):
        blocks = [ContentBlock(type="tool_use", id="tu-1")]
        calls = _extract_tool_calls(blocks, {})
        assert calls[0].name == "unknown"


# ─── parse_history_index (now a method on ClaudeCodeParser)
class TestParseHistoryIndex:
    def test_no_history_file(self, claude_dir: Path):
        result = _parser.parse_history_index(claude_dir)
        assert result == []

    def test_empty_history_file(self, claude_dir: Path):
        (claude_dir / "history.jsonl").write_text("")
        result = _parser.parse_history_index(claude_dir)
        assert result == []

    def test_single_session(self, claude_dir: Path):
        _write_history(
            claude_dir,
            [
                {
                    "sessionId": "s1",
                    "display": "Hello world",
                    "timestamp": 1707734674932,
                    "project": "/Users/Test/MyProject",
                }
            ],
        )
        result = _parser.parse_history_index(claude_dir)
        assert len(result) == 1
        assert result[0].session_id == "s1"
        assert result[0].project_name == "MyProject"
        assert result[0].first_message == "Hello world"
        assert result[0].message_count == 1

    def test_multiple_entries_same_session(self, claude_dir: Path):
        _write_history(
            claude_dir,
            [
                {
                    "sessionId": "s1",
                    "display": "First message",
                    "timestamp": 1000000,
                    "project": "/Users/Test/Proj",
                },
                {
                    "sessionId": "s1",
                    "display": "Second message",
                    "timestamp": 2000000,
                    "project": "/Users/Test/Proj",
                },
            ],
        )
        result = _parser.parse_history_index(claude_dir)
        assert len(result) == 1
        assert result[0].message_count == 2
        assert result[0].first_message == "First message"

    def test_multiple_sessions_sorted_by_timestamp(self, claude_dir: Path):
        _write_history(
            claude_dir,
            [
                {
                    "sessionId": "old",
                    "display": "Old",
                    "timestamp": 1000000,
                    "project": "/p",
                },
                {
                    "sessionId": "new",
                    "display": "New",
                    "timestamp": 9000000,
                    "project": "/p",
                },
            ],
        )
        result = _parser.parse_history_index(claude_dir)
        assert result[0].session_id == "new"
        assert result[1].session_id == "old"

    def test_malformed_json_lines_skipped(self, claude_dir: Path):
        with open(claude_dir / "history.jsonl", "w") as f:
            f.write("NOT VALID JSON\n")
            f.write(
                json.dumps(
                    {
                        "sessionId": "s1",
                        "display": "Valid",
                        "timestamp": 1000000,
                        "project": "/p",
                    }
                )
                + "\n"
            )
        result = _parser.parse_history_index(claude_dir)
        assert len(result) == 1

    def test_entries_without_session_id_skipped(self, claude_dir: Path):
        _write_history(
            claude_dir,
            [
                {"display": "No session id", "timestamp": 1000000, "project": "/p"},
                {
                    "sessionId": "s1",
                    "display": "Has id",
                    "timestamp": 1000000,
                    "project": "/p",
                },
            ],
        )
        result = _parser.parse_history_index(claude_dir)
        assert len(result) == 1

    def test_blank_lines_ignored(self, claude_dir: Path):
        with open(claude_dir / "history.jsonl", "w") as f:
            f.write("\n")
            f.write(
                json.dumps(
                    {
                        "sessionId": "s1",
                        "display": "x",
                        "timestamp": 1000000,
                        "project": "/p",
                    }
                )
                + "\n"
            )
            f.write("\n")
        result = _parser.parse_history_index(claude_dir)
        assert len(result) == 1

    def test_first_message_truncated(self, claude_dir: Path):
        long_message = "x" * 500
        _write_history(
            claude_dir,
            [
                {
                    "sessionId": "s1",
                    "display": long_message,
                    "timestamp": 1000000,
                    "project": "/p",
                }
            ],
        )
        result = _parser.parse_history_index(claude_dir)
        assert len(result[0].first_message) == MAX_FIRST_MESSAGE_LENGTH

    def test_project_id_encoded(self, claude_dir: Path):
        _write_history(
            claude_dir,
            [
                {
                    "sessionId": "s1",
                    "display": "x",
                    "timestamp": 1000000,
                    "project": "/Users/Test/Proj",
                }
            ],
        )
        result = _parser.parse_history_index(claude_dir)
        assert result[0].project_id == "Users-Test-Proj"


# ─── parse_session_jsonl (now a method on ClaudeCodeParser)
class TestParseSessionJsonl:
    def test_nonexistent_file(self, tmp_path: Path):
        result = _parser.parse_session_jsonl(tmp_path / "missing.jsonl")
        assert result == []

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.jsonl"
        f.write_text("")
        result = _parser.parse_session_jsonl(f)
        assert result == []

    def test_single_user_message(self, tmp_path: Path):
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "user",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {"role": "user", "content": "Hello"},
                }
            ],
        )
        result = _parser.parse_session_jsonl(f)
        assert len(result) == 1
        assert result[0].role == "user"
        assert result[0].content == "Hello"

    def test_assistant_with_text_content(self, tmp_path: Path):
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Hi there"}],
                        "model": "claude-sonnet-4-6",
                    },
                }
            ],
        )
        result = _parser.parse_session_jsonl(f)
        assert len(result) == 1
        assert result[0].model == "claude-sonnet-4-6"
        assert isinstance(result[0].content, list)

    def test_non_relevant_types_filtered(self, tmp_path: Path):
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {"type": "system", "uuid": "m0", "message": {"role": "system", "content": "sys"}},
                {
                    "type": "user",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {"role": "user", "content": "hi"},
                },
            ],
        )
        result = _parser.parse_session_jsonl(f)
        assert len(result) == 1
        assert result[0].role == "user"

    def test_tool_use_and_result_paired(self, tmp_path: Path):
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "Let me read that."},
                            {
                                "type": "tool_use",
                                "id": "tu-1",
                                "name": "Read",
                                "input": {"file_path": "/tmp/test.py"},
                            },
                        ],
                    },
                },
                {
                    "type": "user",
                    "uuid": "m2",
                    "sessionId": "s1",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tu-1",
                                "content": "print('hello')",
                            }
                        ],
                    },
                },
            ],
        )
        result = _parser.parse_session_jsonl(f)
        assistant_msg = [m for m in result if m.role == "assistant"][0]
        assert len(assistant_msg.tool_calls) == 1
        assert assistant_msg.tool_calls[0].name == "Read"
        assert assistant_msg.tool_calls[0].output == "print('hello')"

    def test_tool_result_with_error(self, tmp_path: Path):
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tu-1",
                                "name": "Bash",
                                "input": {"command": "bad"},
                            },
                        ],
                    },
                },
                {
                    "type": "user",
                    "uuid": "m2",
                    "sessionId": "s1",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tu-1",
                                "content": "command not found",
                                "is_error": True,
                            }
                        ],
                    },
                },
            ],
        )
        result = _parser.parse_session_jsonl(f)
        assistant_msg = [m for m in result if m.role == "assistant"][0]
        assert assistant_msg.tool_calls[0].is_error is True

    def test_usage_parsed(self, tmp_path: Path):
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {
                        "role": "assistant",
                        "content": "response",
                        "usage": {
                            "input_tokens": 500,
                            "output_tokens": 200,
                            "cache_read_input_tokens": 100,
                        },
                    },
                }
            ],
        )
        result = _parser.parse_session_jsonl(f)
        assert result[0].usage is not None
        assert result[0].usage.input_tokens == 500
        assert result[0].usage.cache_read_tokens == 100

    def test_malformed_lines_skipped(self, tmp_path: Path):
        f = tmp_path / "session.jsonl"
        with open(f, "w") as fh:
            fh.write("INVALID\n")
            fh.write(
                json.dumps(
                    {
                        "type": "user",
                        "uuid": "m1",
                        "sessionId": "s1",
                        "message": {"role": "user", "content": "valid"},
                    }
                )
                + "\n"
            )
        result = _parser.parse_session_jsonl(f)
        assert len(result) == 1

    def test_timestamp_parsed(self, tmp_path: Path):
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "user",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "timestamp": 1707734674932,
                    "message": {"role": "user", "content": "hi"},
                }
            ],
        )
        result = _parser.parse_session_jsonl(f)
        assert result[0].timestamp is not None
        assert result[0].timestamp.tzinfo == UTC

    def test_sidechain_flag(self, tmp_path: Path):
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "isSidechain": True,
                    "message": {"role": "assistant", "content": "sub-agent response"},
                }
            ],
        )
        result = _parser.parse_session_jsonl(f)
        assert result[0].is_sidechain is True

    def test_parent_uuid(self, tmp_path: Path):
        f = tmp_path / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m2",
                    "sessionId": "s1",
                    "parentUuid": "m1",
                    "message": {"role": "assistant", "content": "reply"},
                }
            ],
        )
        result = _parser.parse_session_jsonl(f)
        assert result[0].parent_uuid == "m1"


# ─── compute_session_metadata (now a method on ClaudeCodeParser)
class TestComputeSessionMetadata:
    def test_empty_messages(self):
        meta = _parser.compute_session_metadata([])
        assert meta.message_count == 0
        assert meta.duration == 0

    def test_message_count(self):
        msgs = [
            Message(uuid="m1", session_id="s1", role="user", type="user", content="hi"),
            Message(
                uuid="m2",
                session_id="s1",
                role="assistant",
                type="assistant",
                content="hello",
            ),
        ]
        meta = _parser.compute_session_metadata(msgs)
        assert meta.message_count == 2

    def test_model_collection(self):
        msgs = [
            Message(
                uuid="m1",
                session_id="s1",
                role="assistant",
                type="assistant",
                model="claude-sonnet-4-6",
            ),
            Message(
                uuid="m2",
                session_id="s1",
                role="assistant",
                type="assistant",
                model="claude-haiku-4-5",
            ),
            Message(
                uuid="m3",
                session_id="s1",
                role="assistant",
                type="assistant",
                model="claude-sonnet-4-6",
            ),
        ]
        meta = _parser.compute_session_metadata(msgs)
        assert sorted(meta.models) == ["claude-haiku-4-5", "claude-sonnet-4-6"]

    def test_token_aggregation(self):
        msgs = [
            Message(
                uuid="m1",
                session_id="s1",
                role="assistant",
                type="assistant",
                usage=TokenUsage(
                    input_tokens=100,
                    output_tokens=50,
                    cache_read_tokens=30,
                    cache_creation_tokens=20,
                ),
            ),
            Message(
                uuid="m2",
                session_id="s1",
                role="assistant",
                type="assistant",
                usage=TokenUsage(
                    input_tokens=200,
                    output_tokens=100,
                    cache_read_tokens=70,
                    cache_creation_tokens=10,
                ),
            ),
        ]
        meta = _parser.compute_session_metadata(msgs)
        assert meta.total_input_tokens == 300
        assert meta.total_output_tokens == 150
        assert meta.total_cache_read == 100
        assert meta.total_cache_write == 30

    def test_tool_call_count(self):
        msgs = [
            Message(
                uuid="m1",
                session_id="s1",
                role="assistant",
                type="assistant",
                tool_calls=[ToolCall(name="Read"), ToolCall(name="Edit")],
            ),
            Message(
                uuid="m2",
                session_id="s1",
                role="assistant",
                type="assistant",
                tool_calls=[ToolCall(name="Bash")],
            ),
        ]
        meta = _parser.compute_session_metadata(msgs)
        assert meta.tool_call_count == 3

    def test_first_message_from_user(self):
        msgs = [
            Message(
                uuid="m1",
                session_id="s1",
                role="assistant",
                type="assistant",
                content="I'll help",
            ),
            Message(uuid="m2", session_id="s1", role="user", type="user", content="Fix the bug"),
        ]
        meta = _parser.compute_session_metadata(msgs)
        assert meta.first_message == "Fix the bug"

    def test_first_message_ignores_content_blocks(self):
        blocks = [ContentBlock(type="tool_result", content="tool output")]
        msgs = [
            Message(uuid="m1", session_id="s1", role="user", type="user", content=blocks),
            Message(uuid="m2", session_id="s1", role="user", type="user", content="Real question"),
        ]
        meta = _parser.compute_session_metadata(msgs)
        assert meta.first_message == "Real question"

    def test_first_message_truncated(self):
        long = "x" * 500
        msgs = [
            Message(uuid="m1", session_id="s1", role="user", type="user", content=long),
        ]
        meta = _parser.compute_session_metadata(msgs)
        assert len(meta.first_message) == MAX_FIRST_MESSAGE_LENGTH

    def test_duration_from_timestamps(self):
        t1 = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2025, 1, 1, 10, 5, 0, tzinfo=UTC)
        msgs = [
            Message(uuid="m1", session_id="s1", role="user", type="user", timestamp=t1),
            Message(uuid="m2", session_id="s1", role="assistant", type="assistant", timestamp=t2),
        ]
        meta = _parser.compute_session_metadata(msgs)
        assert meta.duration == 300

    def test_duration_single_message(self):
        t1 = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        msgs = [
            Message(uuid="m1", session_id="s1", role="user", type="user", timestamp=t1),
        ]
        meta = _parser.compute_session_metadata(msgs)
        assert meta.duration == 0

    def test_messages_without_timestamps(self):
        msgs = [
            Message(uuid="m1", session_id="s1", role="user", type="user"),
            Message(uuid="m2", session_id="s1", role="assistant", type="assistant"),
        ]
        meta = _parser.compute_session_metadata(msgs)
        assert meta.duration == 0

    def test_messages_without_usage(self):
        msgs = [
            Message(uuid="m1", session_id="s1", role="user", type="user"),
        ]
        meta = _parser.compute_session_metadata(msgs)
        assert meta.total_input_tokens == 0


# ─── Subagent parsing (separated, not merged)
class TestSubagentParsing:
    def test_main_session_excludes_subagent_messages(self, tmp_path: Path):
        """parse_session_jsonl returns only main-session messages."""
        main_file = tmp_path / "session-abc.jsonl"
        _write_session(
            main_file,
            [
                {
                    "type": "user",
                    "uuid": "m1",
                    "sessionId": "session-abc",
                    "message": {"role": "user", "content": "Main session message"},
                }
            ],
        )

        subagent_dir = tmp_path / "session-abc" / "subagents"
        subagent_dir.mkdir(parents=True)
        _write_session(
            subagent_dir / "agent-001.jsonl",
            [
                {
                    "type": "assistant",
                    "uuid": "sa-1",
                    "sessionId": "session-abc",
                    "message": {"role": "assistant", "content": "Subagent response"},
                }
            ],
        )

        result = _parser.parse_session_jsonl(main_file)
        print(f"  main messages: {len(result)}")
        print(f"  content: {[m.content for m in result]}")
        assert len(result) == 1
        assert result[0].content == "Main session message"

    def test_subagents_returned_separately(self, tmp_path: Path):
        """parse_session_with_subagents returns sub-sessions as separate objects."""
        main_file = tmp_path / "session-abc.jsonl"
        _write_session(
            main_file,
            [
                {
                    "type": "user",
                    "uuid": "m1",
                    "sessionId": "session-abc",
                    "message": {"role": "user", "content": "Main message"},
                },
                {
                    "type": "assistant",
                    "uuid": "m2",
                    "sessionId": "session-abc",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tu-agent-1",
                                "name": "Agent",
                                "input": {"prompt": "do something"},
                            }
                        ],
                    },
                },
            ],
        )

        subagent_dir = tmp_path / "session-abc" / "subagents"
        subagent_dir.mkdir(parents=True)
        _write_session(
            subagent_dir / "agent-001.jsonl",
            [
                {
                    "type": "assistant",
                    "uuid": "sa-1",
                    "sessionId": "session-abc",
                    "message": {"role": "assistant", "content": "Subagent response"},
                }
            ],
        )

        messages, sub_sessions = _parser.parse_session_with_subagents(main_file)
        print(f"  main messages: {len(messages)}")
        print(f"  sub_sessions: {len(sub_sessions)}")
        for sub in sub_sessions:
            print(f"    agent_id={sub.agent_id}, spawn_index={sub.spawn_index}")
            print(f"    spawn_tool_call_id={sub.spawn_tool_call_id}")
            print(f"    messages: {len(sub.messages)}")
            for m in sub.messages:
                print(f"      role={m.role}, sidechain={m.is_sidechain}, content={m.content[:50]}")

        assert len(messages) == 2
        assert len(sub_sessions) == 1
        assert sub_sessions[0].agent_id == "agent-001"
        assert sub_sessions[0].spawn_index == 1
        assert sub_sessions[0].spawn_tool_call_id == "tu-agent-1"
        assert sub_sessions[0].messages[0].is_sidechain is True

    def test_multiple_subagent_files_separate(self, tmp_path: Path):
        """Multiple subagent files produce separate SubAgentSession objects."""
        main_file = tmp_path / "sess.jsonl"
        _write_session(
            main_file,
            [
                {
                    "type": "user",
                    "uuid": "m1",
                    "sessionId": "sess",
                    "message": {"role": "user", "content": "start"},
                }
            ],
        )

        subagent_dir = tmp_path / "sess" / "subagents"
        subagent_dir.mkdir(parents=True)

        for agent_id in ["agent-aaa", "agent-bbb"]:
            _write_session(
                subagent_dir / f"{agent_id}.jsonl",
                [
                    {
                        "type": "assistant",
                        "uuid": f"sa-{agent_id}",
                        "sessionId": "sess",
                        "message": {"role": "assistant", "content": f"from {agent_id}"},
                    }
                ],
            )

        messages, sub_sessions = _parser.parse_session_with_subagents(main_file)
        print(f"  main messages: {len(messages)}")
        print(f"  sub_sessions: {len(sub_sessions)}")
        for sub in sub_sessions:
            print(f"    agent_id={sub.agent_id}, msgs={len(sub.messages)}")

        assert len(messages) == 1
        assert len(sub_sessions) == 2
        agent_ids = {sub.agent_id for sub in sub_sessions}
        assert agent_ids == {"agent-aaa", "agent-bbb"}

    def test_no_subagent_dir(self, tmp_path: Path):
        """No error when subagent directory does not exist."""
        main_file = tmp_path / "session.jsonl"
        _write_session(
            main_file,
            [
                {
                    "type": "user",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {"role": "user", "content": "solo"},
                }
            ],
        )
        messages, sub_sessions = _parser.parse_session_with_subagents(main_file)
        print(f"  main messages: {len(messages)}, sub_sessions: {len(sub_sessions)}")
        assert len(messages) == 1
        assert len(sub_sessions) == 0

    def test_empty_subagent_dir(self, tmp_path: Path):
        """Empty subagent directory produces no sub-sessions."""
        main_file = tmp_path / "session.jsonl"
        _write_session(
            main_file,
            [
                {
                    "type": "user",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {"role": "user", "content": "solo"},
                }
            ],
        )
        subagent_dir = tmp_path / "session" / "subagents"
        subagent_dir.mkdir(parents=True)

        messages, sub_sessions = _parser.parse_session_with_subagents(main_file)
        assert len(messages) == 1
        assert len(sub_sessions) == 0


# ─── Tool enrichment via parse_file
class TestToolEnrichmentViaParseFile:
    """Tests that parse_file populates tool category and summary."""

    def test_read_tool_enriched(self, tmp_path: Path, project_dir: Path):
        f = project_dir / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tu-1",
                                "name": "Read",
                                "input": {"file_path": "/src/main.py"},
                            }
                        ],
                    },
                },
                {
                    "type": "user",
                    "uuid": "m2",
                    "sessionId": "s1",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tu-1",
                                "content": "print('hello')",
                            }
                        ],
                    },
                },
            ],
        )
        results = _parser.parse_file(f)
        _, messages = results[0]
        tc = messages[0].tool_calls[0]
        print(f"  name={tc.name}, category={tc.category}, summary={tc.summary}")
        assert tc.category == "file_read"
        assert tc.summary == "/src/main.py"

    def test_bash_tool_enriched(self, tmp_path: Path, project_dir: Path):
        f = project_dir / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tu-1",
                                "name": "Bash",
                                "input": {"command": "npm test"},
                            }
                        ],
                    },
                },
            ],
        )
        results = _parser.parse_file(f)
        _, messages = results[0]
        tc = messages[0].tool_calls[0]
        assert tc.category == "shell"
        assert tc.summary == "npm test"

    def test_agent_tool_enriched(self, tmp_path: Path, project_dir: Path):
        f = project_dir / "session.jsonl"
        _write_session(
            f,
            [
                {
                    "type": "assistant",
                    "uuid": "m1",
                    "sessionId": "s1",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tu-1",
                                "name": "Agent",
                                "input": {"description": "Search codebase", "prompt": "find bugs"},
                            }
                        ],
                    },
                },
            ],
        )
        results = _parser.parse_file(f)
        _, messages = results[0]
        tc = messages[0].tool_calls[0]
        assert tc.category == "agent"
        assert tc.summary == "Search codebase"


# ─── Discover subagent-only sessions
class TestDiscoverSubagentOnlySessions:
    """Tests for ClaudeCodeParser.discover_subagent_only_sessions."""

    def test_finds_subagent_dirs_without_root_jsonl(self, tmp_path: Path):
        """Session dir with only subagent files and no root JSONL is discovered."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Session with root JSONL — should NOT be returned
        (project_dir / "has-root.jsonl").write_text("{}\n")
        sa_dir = project_dir / "has-root" / "subagents"
        sa_dir.mkdir(parents=True)
        (sa_dir / "agent-a1.jsonl").write_text("{}\n")

        # Session with only subagent data — SHOULD be returned
        sa_dir2 = project_dir / "subagent-only" / "subagents"
        sa_dir2.mkdir(parents=True)
        (sa_dir2 / "agent-b1.jsonl").write_text("{}\n")

        result = _parser.discover_subagent_only_sessions(project_dir)
        print(f"  discovered: {[p.name for p in result]}")
        assert len(result) == 1
        # Returns the subagents/ dir, parent is the session dir
        assert result[0].parent.name == "subagent-only"

    def test_ignores_dirs_without_subagents(self, tmp_path: Path):
        """Directories with only tool-results are ignored."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "tool-only" / "tool-results").mkdir(parents=True)

        result = _parser.discover_subagent_only_sessions(project_dir)
        assert result == []

    def test_ignores_empty_subagent_dirs(self, tmp_path: Path):
        """Empty subagent directories are ignored."""
        project_dir = tmp_path / "project"
        (project_dir / "empty-sa" / "subagents").mkdir(parents=True)

        result = _parser.discover_subagent_only_sessions(project_dir)
        assert result == []

    def test_returns_empty_for_no_dirs(self, tmp_path: Path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "session.jsonl").write_text("{}\n")

        result = _parser.discover_subagent_only_sessions(project_dir)
        assert result == []

    def test_nonexistent_project_dir(self, tmp_path: Path):
        result = _parser.discover_subagent_only_sessions(tmp_path / "nonexistent")
        assert result == []


# ─── parse_history_index with since/limit
class TestParseHistoryIndexFiltering:
    def test_since_filters_old_sessions(self, claude_dir: Path):
        """Sessions before `since` are excluded."""
        _write_history(
            claude_dir,
            [
                {"sessionId": "old", "display": "Old", "timestamp": 1700000000000, "project": "/p"},
                {"sessionId": "new", "display": "New", "timestamp": 1710000000000, "project": "/p"},
            ],
        )
        since = datetime(2024, 3, 1, tzinfo=UTC)
        result = _parser.parse_history_index(claude_dir, since=since)
        assert len(result) == 1
        assert result[0].session_id == "new"
        print(f"  filtered: kept {len(result)} of 2 sessions")

    def test_since_none_returns_all(self, claude_dir: Path):
        _write_history(
            claude_dir,
            [
                {"sessionId": "s1", "display": "A", "timestamp": 1700000000000, "project": "/p"},
                {"sessionId": "s2", "display": "B", "timestamp": 1710000000000, "project": "/p"},
            ],
        )
        result = _parser.parse_history_index(claude_dir, since=None)
        assert len(result) == 2

    def test_limit_truncates_results(self, claude_dir: Path):
        entries = [
            {
                "sessionId": f"s{i}", "display": f"msg{i}",
                "timestamp": 1700000000000 + i * 1000000,
                "project": "/p",
            }
            for i in range(10)
        ]
        _write_history(claude_dir, entries)
        result = _parser.parse_history_index(claude_dir, limit=3)
        assert len(result) == 3
        print(f"  limited to {len(result)} sessions")

    def test_limit_none_returns_all(self, claude_dir: Path):
        entries = [
            {
                "sessionId": f"s{i}", "display": f"msg{i}",
                "timestamp": 1700000000000 + i * 1000000,
                "project": "/p",
            }
            for i in range(5)
        ]
        _write_history(claude_dir, entries)
        result = _parser.parse_history_index(claude_dir, limit=None)
        assert len(result) == 5

    def test_since_and_limit_combined(self, claude_dir: Path):
        _write_history(
            claude_dir,
            [
                {"sessionId": "old", "display": "Old",
                 "timestamp": 1700000000000, "project": "/p"},
                {"sessionId": "mid", "display": "Mid",
                 "timestamp": 1710000000000, "project": "/p"},
                {"sessionId": "new1", "display": "New1",
                 "timestamp": 1720000000000, "project": "/p"},
                {"sessionId": "new2", "display": "New2",
                 "timestamp": 1730000000000, "project": "/p"},
            ],
        )
        since = datetime(2024, 3, 1, tzinfo=UTC)
        result = _parser.parse_history_index(claude_dir, since=since, limit=1)
        assert len(result) == 1

    def test_backward_compatible(self, claude_dir: Path):
        """No args behaves the same as before."""
        _write_history(
            claude_dir,
            [{"sessionId": "s1", "display": "x", "timestamp": 1707734674932, "project": "/p"}],
        )
        result = _parser.parse_history_index(claude_dir)
        assert len(result) == 1


# ─── count_history_entries
class TestCountHistoryEntries:
    def test_counts_lines(self, claude_dir: Path):
        _write_history(
            claude_dir,
            [
                {"sessionId": "s1", "display": "A", "timestamp": 1700000000000, "project": "/p"},
                {"sessionId": "s2", "display": "B", "timestamp": 1700000001000, "project": "/p"},
                {"sessionId": "s3", "display": "C", "timestamp": 1700000002000, "project": "/p"},
            ],
        )
        count = count_history_entries(claude_dir)
        assert count == 3
        print(f"  counted {count} entries")

    def test_missing_file_returns_zero(self, claude_dir: Path):
        assert count_history_entries(claude_dir) == 0

    def test_empty_file(self, claude_dir: Path):
        (claude_dir / "history.jsonl").write_text("")
        assert count_history_entries(claude_dir) == 0
