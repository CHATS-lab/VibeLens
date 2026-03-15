"""Tests for vibelens.ingest.base — BaseParser shared helpers."""

import json
from pathlib import Path

from vibelens.ingest.base import MAX_FIRST_MESSAGE_LENGTH, BaseParser
from vibelens.models.message import ContentBlock, Message, ToolCall


class _ConcreteParser(BaseParser):
    """Minimal concrete parser for testing abstract base class methods."""

    def parse_file(self, file_path):
        return []


_parser = _ConcreteParser()


# ─── find_first_user_text
class TestFindFirstUserText:
    """Tests for BaseParser.find_first_user_text."""

    def test_finds_first_user_string(self):
        messages = [
            Message(uuid="m1", session_id="s1", role="assistant", type="assistant", content="Hi"),
            Message(uuid="m2", session_id="s1", role="user", type="user", content="Fix the bug"),
            Message(uuid="m3", session_id="s1", role="user", type="user", content="Also this"),
        ]
        result = _parser.find_first_user_text(messages)
        print(f"  first_user_text: {result}")
        assert result == "Fix the bug"

    def test_skips_content_block_users(self):
        """User messages with non-string content (e.g. tool_result) are skipped."""
        blocks = [ContentBlock(type="tool_result", content="tool output")]
        messages = [
            Message(uuid="m1", session_id="s1", role="user", type="user", content=blocks),
            Message(uuid="m2", session_id="s1", role="user", type="user", content="Real question"),
        ]
        result = _parser.find_first_user_text(messages)
        assert result == "Real question"

    def test_no_user_messages(self):
        messages = [
            Message(uuid="m1", session_id="s1", role="assistant", type="assistant", content="Hi"),
        ]
        assert _parser.find_first_user_text(messages) == ""

    def test_empty_message_list(self):
        assert _parser.find_first_user_text([]) == ""

    def test_whitespace_user_skipped(self):
        """User messages with whitespace-only content are skipped."""
        messages = [
            Message(uuid="m1", session_id="s1", role="user", type="user", content="   "),
            Message(uuid="m2", session_id="s1", role="user", type="user", content="Valid"),
        ]
        assert _parser.find_first_user_text(messages) == "Valid"

    def test_truncates_long_message(self):
        long_msg = "x" * 500
        messages = [
            Message(uuid="m1", session_id="s1", role="user", type="user", content=long_msg),
        ]
        result = _parser.find_first_user_text(messages)
        assert len(result) == MAX_FIRST_MESSAGE_LENGTH

    def test_empty_string_user_skipped(self):
        messages = [
            Message(uuid="m1", session_id="s1", role="user", type="user", content=""),
            Message(uuid="m2", session_id="s1", role="user", type="user", content="Hello"),
        ]
        assert _parser.find_first_user_text(messages) == "Hello"


# ─── enrich_tool_calls
class TestEnrichToolCalls:
    """Tests for BaseParser.enrich_tool_calls populating category and summary."""

    def test_enriches_read_tool(self):
        tc = ToolCall(name="Read", input={"file_path": "/src/main.py"})
        msg = Message(
            uuid="m1", session_id="s1", role="assistant", type="assistant", tool_calls=[tc]
        )
        BaseParser.enrich_tool_calls([msg])
        print(f"  category={tc.category}, summary={tc.summary}")
        assert tc.category == "file_read"
        assert tc.summary == "/src/main.py"

    def test_enriches_bash_tool(self):
        tc = ToolCall(name="Bash", input={"command": "git status"})
        msg = Message(
            uuid="m1", session_id="s1", role="assistant", type="assistant", tool_calls=[tc]
        )
        BaseParser.enrich_tool_calls([msg])
        assert tc.category == "shell"
        assert tc.summary == "git status"

    def test_enriches_grep_tool(self):
        tc = ToolCall(name="Grep", input={"pattern": "TODO"})
        msg = Message(
            uuid="m1", session_id="s1", role="assistant", type="assistant", tool_calls=[tc]
        )
        BaseParser.enrich_tool_calls([msg])
        assert tc.category == "search"
        assert tc.summary == "TODO"

    def test_enriches_unknown_tool(self):
        tc = ToolCall(name="CustomWidget", input={"data": "value"})
        msg = Message(
            uuid="m1", session_id="s1", role="assistant", type="assistant", tool_calls=[tc]
        )
        BaseParser.enrich_tool_calls([msg])
        assert tc.category == "other"
        assert tc.summary == "value"

    def test_does_not_overwrite_existing_category(self):
        """Pre-populated category is not overwritten."""
        tc = ToolCall(name="Read", input={"file_path": "/test.py"}, category="custom")
        msg = Message(
            uuid="m1", session_id="s1", role="assistant", type="assistant", tool_calls=[tc]
        )
        BaseParser.enrich_tool_calls([msg])
        assert tc.category == "custom"

    def test_does_not_overwrite_existing_summary(self):
        """Pre-populated summary is not overwritten."""
        tc = ToolCall(name="Read", input={"file_path": "/test.py"}, summary="custom summary")
        msg = Message(
            uuid="m1", session_id="s1", role="assistant", type="assistant", tool_calls=[tc]
        )
        BaseParser.enrich_tool_calls([msg])
        assert tc.summary == "custom summary"

    def test_no_tool_calls(self):
        """Messages without tool calls are handled gracefully."""
        msg = Message(uuid="m1", session_id="s1", role="user", type="user", content="hi")
        BaseParser.enrich_tool_calls([msg])

    def test_multiple_messages_and_tools(self):
        """Multiple messages with multiple tool calls all enriched."""
        tc1 = ToolCall(name="Read", input={"file_path": "/a.py"})
        tc2 = ToolCall(name="Edit", input={"file_path": "/b.py"})
        tc3 = ToolCall(name="Bash", input={"command": "ls"})
        msg1 = Message(
            uuid="m1", session_id="s1", role="assistant", type="assistant", tool_calls=[tc1, tc2]
        )
        msg2 = Message(
            uuid="m2", session_id="s1", role="assistant", type="assistant", tool_calls=[tc3]
        )
        BaseParser.enrich_tool_calls([msg1, msg2])
        assert tc1.category == "file_read"
        assert tc2.category == "file_write"
        assert tc3.category == "shell"

    def test_tool_with_none_input(self):
        """Tool with None input gets empty summary."""
        tc = ToolCall(name="Agent", input=None)
        msg = Message(
            uuid="m1", session_id="s1", role="assistant", type="assistant", tool_calls=[tc]
        )
        BaseParser.enrich_tool_calls([msg])
        assert tc.category == "agent"
        assert tc.summary == ""

    def test_tool_with_string_input(self):
        """Tool with string input uses the string as summary."""
        tc = ToolCall(name="Bash", input="ls -la")
        msg = Message(
            uuid="m1", session_id="s1", role="assistant", type="assistant", tool_calls=[tc]
        )
        BaseParser.enrich_tool_calls([msg])
        assert tc.summary == "ls -la"

    def test_output_digest_populated(self):
        """enrich_tool_calls populates output_digest from tool output."""
        tc = ToolCall(name="Read", output="line1\nline2\n", is_error=False)
        msg = Message(
            uuid="m1", session_id="s1", role="assistant", type="assistant", tool_calls=[tc]
        )
        BaseParser.enrich_tool_calls([msg])
        assert tc.output_digest != ""
        print(f"  output_digest: {tc.output_digest}")

    def test_output_digest_error(self):
        """Error output produces ERROR: prefix in digest."""
        tc = ToolCall(name="Bash", output="command not found", is_error=True)
        msg = Message(
            uuid="m1", session_id="s1", role="assistant", type="assistant", tool_calls=[tc]
        )
        BaseParser.enrich_tool_calls([msg])
        assert tc.output_digest.startswith("ERROR:")

    def test_output_digest_not_overwritten(self):
        """Pre-existing output_digest is preserved."""
        tc = ToolCall(name="Read", output="data", output_digest="custom")
        msg = Message(
            uuid="m1", session_id="s1", role="assistant", type="assistant", tool_calls=[tc]
        )
        BaseParser.enrich_tool_calls([msg])
        assert tc.output_digest == "custom"

    def test_output_digest_none_output(self):
        """None output produces empty digest."""
        tc = ToolCall(name="Read", output=None)
        msg = Message(
            uuid="m1", session_id="s1", role="assistant", type="assistant", tool_calls=[tc]
        )
        BaseParser.enrich_tool_calls([msg])
        assert tc.output_digest == ""


# ─── iter_jsonl_safe
class TestIterJsonlSafe:
    """Tests for BaseParser.iter_jsonl_safe file reading."""

    def test_valid_jsonl(self, tmp_path: Path):
        f = tmp_path / "data.jsonl"
        f.write_text('{"a": 1}\n{"b": 2}\n')
        entries = list(BaseParser.iter_jsonl_safe(f))
        print(f"  entries: {len(entries)}")
        assert len(entries) == 2
        assert entries[0] == {"a": 1}
        assert entries[1] == {"b": 2}

    def test_skips_malformed_lines(self, tmp_path: Path):
        f = tmp_path / "data.jsonl"
        f.write_text('{"good": 1}\nNOT JSON\n{"also_good": 2}\n')
        entries = list(BaseParser.iter_jsonl_safe(f))
        assert len(entries) == 2
        assert entries[0]["good"] == 1
        assert entries[1]["also_good"] == 2

    def test_skips_blank_lines(self, tmp_path: Path):
        f = tmp_path / "data.jsonl"
        f.write_text('\n{"a": 1}\n   \n{"b": 2}\n\n')
        entries = list(BaseParser.iter_jsonl_safe(f))
        assert len(entries) == 2

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.jsonl"
        f.write_text("")
        entries = list(BaseParser.iter_jsonl_safe(f))
        assert entries == []

    def test_nonexistent_file(self, tmp_path: Path):
        """Non-existent file returns empty iterator without raising."""
        entries = list(BaseParser.iter_jsonl_safe(tmp_path / "missing.jsonl"))
        assert entries == []

    def test_permission_error(self, tmp_path: Path):
        """Unreadable file is caught by OSError handler."""
        f = tmp_path / "noperm.jsonl"
        f.write_text('{"data": 1}\n')
        f.chmod(0o000)
        entries = list(BaseParser.iter_jsonl_safe(f))
        assert entries == []
        f.chmod(0o644)

    def test_large_file_streaming(self, tmp_path: Path):
        """Verify iter_jsonl_safe handles many lines."""
        f = tmp_path / "large.jsonl"
        line_count = 1000
        lines = [json.dumps({"idx": i}) for i in range(line_count)]
        f.write_text("\n".join(lines) + "\n")
        entries = list(BaseParser.iter_jsonl_safe(f))
        assert len(entries) == line_count
        assert entries[0]["idx"] == 0
        assert entries[-1]["idx"] == line_count - 1
