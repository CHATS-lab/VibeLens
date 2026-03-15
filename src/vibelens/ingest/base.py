"""Abstract base class for format-specific session parsers."""

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from vibelens.models.message import Message
from vibelens.models.session import SessionSummary

if TYPE_CHECKING:
    from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.utils.paths import encode_project_path as _encode_project_path
from vibelens.utils.paths import extract_project_name as _extract_project_name

logger = logging.getLogger(__name__)

# Keeps session-list previews short enough for UI display while preserving
# enough context for the user to recognise the conversation at a glance.
MAX_FIRST_MESSAGE_LENGTH = 200


class BaseParser(ABC):
    """Abstract base for format-specific session parsers.

    Every concrete parser must implement ``parse_file`` which converts a
    single vendor-specific file into the unified ``(SessionSummary,
    list[Message])`` tuple.  The return type is a *list* of tuples because
    some formats (e.g. dataclaw) pack multiple sessions into one file.

    Shared helpers live here to avoid duplicating project-name and path-
    encoding logic across parsers.
    """

    @abstractmethod
    def parse_file(
        self, file_path: Path
    ) -> list[tuple[SessionSummary, list[Message]]]:
        """Parse a data file into (summary, messages) pairs.

        Args:
            file_path: Path to the data file to parse.

        Returns:
            List of (SessionSummary, messages) tuples.
        """

    # ── Shared helpers ───────────────────────────────────────────────
    # Delegated to vibelens.utils.paths so the logic is reusable outside
    # the parser hierarchy (e.g. API routes, CLI commands).
    @staticmethod
    def extract_project_name(project_path: str) -> str:
        """Extract human-readable project name from a filesystem path.

        Args:
            project_path: Absolute path string.

        Returns:
            Last path component, or "Unknown" if empty.
        """
        return _extract_project_name(project_path)

    @staticmethod
    def encode_project_path(project_path: str) -> str:
        """Encode a project path to a directory name (``/`` → ``-``).

        Args:
            project_path: Absolute path string.

        Returns:
            Encoded path string.
        """
        return _encode_project_path(project_path)

    @staticmethod
    def truncate_first_message(text: str) -> str:
        """Truncate text to MAX_FIRST_MESSAGE_LENGTH characters.

        Args:
            text: Raw message text.

        Returns:
            Truncated string.
        """
        return text[:MAX_FIRST_MESSAGE_LENGTH]

    def find_first_user_text(self, messages: list[Message]) -> str:
        """Extract truncated text of the first user message.

        Args:
            messages: Ordered list of parsed Message objects.

        Returns:
            Truncated first user message, or empty string if none found.
        """
        for msg in messages:
            if msg.role == "user" and isinstance(msg.content, str) and msg.content.strip():
                return self.truncate_first_message(msg.content)
        return ""

    @staticmethod
    def enrich_tool_calls(messages: list[Message]) -> None:
        """Populate summary, category, and output_digest on all ToolCall objects in-place.

        Args:
            messages: Messages whose tool_calls will be enriched.
        """
        from vibelens.ingest.tool_normalizers import (
            categorize_tool,
            summarize_tool_input,
            summarize_tool_output,
        )

        for msg in messages:
            for tc in msg.tool_calls:
                if not tc.category:
                    tc.category = categorize_tool(tc.name)
                if not tc.summary:
                    tc.summary = summarize_tool_input(tc.name, tc.input)
                if not tc.output_digest:
                    tc.output_digest = summarize_tool_output(tc.name, tc.output, tc.is_error)

    @staticmethod
    def iter_jsonl_safe(
        file_path: Path, diagnostics: "DiagnosticsCollector | None" = None
    ) -> Iterator[dict]:
        """Yield parsed JSON dicts from a JSONL file, catching errors.

        Args:
            file_path: Path to the JSONL file.
            diagnostics: Optional collector for tracking skipped lines.

        Yields:
            Parsed JSON dict per non-empty line.
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if diagnostics:
                        diagnostics.total_lines += 1
                    try:
                        parsed = json.loads(stripped)
                        if diagnostics:
                            diagnostics.parsed_lines += 1
                        yield parsed
                    except json.JSONDecodeError:
                        if diagnostics:
                            diagnostics.record_skip("invalid JSON")
                        continue
        except OSError:
            logger.warning("Cannot read file: %s", file_path)
