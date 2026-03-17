"""Integration tests using real example data files.

Tests the full parse pipeline against the bundled example sessions
to verify project name extraction, metadata population, content
rendering, and token aggregation.
"""

from pathlib import Path

import pytest

from vibelens.ingest.fingerprint import fingerprint_file, parse_auto
from vibelens.ingest.parsers.claude_code import ClaudeCodeParser
from vibelens.ingest.parsers.codex import CodexParser
from vibelens.ingest.parsers.gemini import GeminiParser

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"

CLAUDE_EXAMPLE = EXAMPLES_DIR / "claude-code-example.jsonl"
CODEX_EXAMPLE = EXAMPLES_DIR / "codex-example.jsonl"
GEMINI_EXAMPLE = EXAMPLES_DIR / "gemini-example.json"


def _skip_if_missing(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"Example file not found: {path}")


# ─── Fingerprint detection
class TestFingerprintExamples:
    """Verify auto-detection correctly identifies example files."""

    def test_claude_code_detected(self):
        _skip_if_missing(CLAUDE_EXAMPLE)
        matches = fingerprint_file(CLAUDE_EXAMPLE)
        assert len(matches) > 0
        assert matches[0].format_name == "claude_code"
        assert matches[0].confidence >= 0.5
        print(f"  Claude: {matches[0].format_name} confidence={matches[0].confidence:.2f}")

    def test_codex_detected(self):
        _skip_if_missing(CODEX_EXAMPLE)
        matches = fingerprint_file(CODEX_EXAMPLE)
        assert len(matches) > 0
        assert matches[0].format_name == "codex"
        assert matches[0].confidence >= 0.5
        print(f"  Codex: {matches[0].format_name} confidence={matches[0].confidence:.2f}")

    def test_gemini_detected(self):
        _skip_if_missing(GEMINI_EXAMPLE)
        matches = fingerprint_file(GEMINI_EXAMPLE)
        assert len(matches) > 0
        assert matches[0].format_name == "gemini"
        assert matches[0].confidence >= 0.5
        print(f"  Gemini: {matches[0].format_name} confidence={matches[0].confidence:.2f}")


# ─── Claude Code example parsing
class TestClaudeCodeExample:
    """Parse the Claude Code example and verify metadata fields."""

    @pytest.fixture(autouse=True)
    def _parse(self):
        _skip_if_missing(CLAUDE_EXAMPLE)
        parser = ClaudeCodeParser()
        results = parser.parse_file(CLAUDE_EXAMPLE)
        assert len(results) == 1
        self.summary, self.messages = results[0]

    def test_project_name_extracted(self):
        """Project name derived from cwd field in JSONL entries."""
        assert self.summary.project_name != ""
        assert self.summary.project_id != ""
        print(f"  project_name={self.summary.project_name}")
        print(f"  project_id={self.summary.project_id}")

    def test_timestamp_populated(self):
        """Session timestamp derived from earliest message."""
        assert self.summary.timestamp is not None
        print(f"  timestamp={self.summary.timestamp}")

    def test_duration_positive(self):
        """Session has non-zero duration."""
        assert self.summary.duration > 0
        print(f"  duration={self.summary.duration}s")

    def test_tool_calls_counted(self):
        """Tool call count is non-zero."""
        assert self.summary.tool_call_count > 0
        print(f"  tool_call_count={self.summary.tool_call_count}")

    def test_models_populated(self):
        """At least one model is identified."""
        assert len(self.summary.models) > 0
        print(f"  models={self.summary.models}")

    def test_token_totals_populated(self):
        """Token totals are aggregated from message usage data."""
        total = (
            self.summary.total_input_tokens
            + self.summary.total_output_tokens
            + self.summary.total_cache_read
            + self.summary.total_cache_write
        )
        assert total > 0
        print(
            f"  tokens: in={self.summary.total_input_tokens} "
            f"out={self.summary.total_output_tokens} "
            f"cache_read={self.summary.total_cache_read} "
            f"cache_write={self.summary.total_cache_write}"
        )

    def test_first_message_extracted(self):
        """First user message is captured for display."""
        assert self.summary.first_message != ""
        print(f"  first_message={self.summary.first_message[:80]}...")

    def test_agent_format(self):
        assert self.summary.agent_format == "claude_code"

    def test_messages_have_roles(self):
        """All messages have user or assistant role."""
        roles = {m.role for m in self.messages}
        assert roles <= {"user", "assistant"}
        user_count = sum(1 for m in self.messages if m.role == "user")
        assistant_count = sum(1 for m in self.messages if m.role == "assistant")
        print(f"  messages: {len(self.messages)} total, {user_count} user, {assistant_count} asst")


# ─── Codex example parsing
class TestCodexExample:
    """Parse the Codex example and verify metadata fields."""

    @pytest.fixture(autouse=True)
    def _parse(self):
        _skip_if_missing(CODEX_EXAMPLE)
        parser = CodexParser()
        results = parser.parse_file(CODEX_EXAMPLE)
        assert len(results) == 1
        self.summary, self.messages = results[0]

    def test_project_name_extracted(self):
        """Codex extracts project name from session_meta cwd."""
        assert self.summary.project_name != ""
        print(f"  project_name={self.summary.project_name}")

    def test_timestamp_populated(self):
        assert self.summary.timestamp is not None
        print(f"  timestamp={self.summary.timestamp}")

    def test_tool_calls_counted(self):
        assert self.summary.tool_call_count > 0
        print(f"  tool_call_count={self.summary.tool_call_count}")

    def test_models_populated(self):
        assert len(self.summary.models) > 0
        print(f"  models={self.summary.models}")

    def test_agent_format(self):
        assert self.summary.agent_format == "codex"


# ─── Gemini example parsing
class TestGeminiExample:
    """Parse the Gemini example and verify metadata and content fixes."""

    @pytest.fixture(autouse=True)
    def _parse(self):
        _skip_if_missing(GEMINI_EXAMPLE)
        parser = GeminiParser()
        results = parser.parse_file(GEMINI_EXAMPLE)
        assert len(results) == 1
        self.summary, self.messages = results[0]

    def test_timestamp_populated(self):
        assert self.summary.timestamp is not None
        print(f"  timestamp={self.summary.timestamp}")

    def test_duration_positive(self):
        assert self.summary.duration > 0
        print(f"  duration={self.summary.duration}s")

    def test_models_populated(self):
        assert len(self.summary.models) > 0
        print(f"  models={self.summary.models}")

    def test_token_totals_aggregated(self):
        """Token totals are aggregated from per-message Gemini token data."""
        assert self.summary.total_input_tokens > 0
        assert self.summary.total_output_tokens > 0
        print(
            f"  tokens: in={self.summary.total_input_tokens} "
            f"out={self.summary.total_output_tokens} "
            f"cache_read={self.summary.total_cache_read}"
        )

    def test_assistant_messages_have_content(self):
        """Gemini messages with only thoughts have thinking as content."""
        assistant_msgs = [m for m in self.messages if m.role == "assistant"]
        assert len(assistant_msgs) > 0
        # At least some assistant messages should have non-empty content
        non_empty = [m for m in assistant_msgs if m.content]
        print(f"  assistant msgs: {len(assistant_msgs)} total, {len(non_empty)} with content")
        assert len(non_empty) > 0

    def test_thinking_preserved(self):
        """Thinking text is extracted from thoughts array."""
        thinking_msgs = [m for m in self.messages if m.thinking]
        assert len(thinking_msgs) > 0
        print(f"  messages with thinking: {len(thinking_msgs)}")
        # Verify thinking has the [Subject] format
        first_thinking = thinking_msgs[0].thinking
        assert "[" in first_thinking
        print(f"  first thinking: {first_thinking[:80]}...")

    def test_agent_format(self):
        assert self.summary.agent_format == "gemini"

    def test_user_messages_have_content(self):
        """User messages have non-empty content."""
        user_msgs = [m for m in self.messages if m.role == "user"]
        assert len(user_msgs) > 0
        for msg in user_msgs:
            assert msg.content, f"User message {msg.uuid} has empty content"


# ─── parse_auto integration
class TestParseAutoExamples:
    """Verify parse_auto correctly auto-detects and parses all examples."""

    def test_claude_auto(self):
        _skip_if_missing(CLAUDE_EXAMPLE)
        results = parse_auto(CLAUDE_EXAMPLE)
        assert len(results) == 1
        summary, messages = results[0]
        assert summary.agent_format == "claude_code"
        assert len(messages) > 0
        print(f"  Claude: {len(messages)} messages, format={summary.agent_format}")

    def test_codex_auto(self):
        _skip_if_missing(CODEX_EXAMPLE)
        results = parse_auto(CODEX_EXAMPLE)
        assert len(results) == 1
        summary, messages = results[0]
        assert summary.agent_format == "codex"
        assert len(messages) > 0
        print(f"  Codex: {len(messages)} messages, format={summary.agent_format}")

    def test_gemini_auto(self):
        _skip_if_missing(GEMINI_EXAMPLE)
        results = parse_auto(GEMINI_EXAMPLE)
        assert len(results) == 1
        summary, messages = results[0]
        assert summary.agent_format == "gemini"
        assert len(messages) > 0
        print(f"  Gemini: {len(messages)} messages, format={summary.agent_format}")
