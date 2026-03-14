"""Abstract base class for format-specific session parsers."""

from abc import ABC, abstractmethod
from pathlib import Path

from vibelens.models.message import Message
from vibelens.models.session import SessionSummary
from vibelens.utils.paths import encode_project_path as _encode_project_path
from vibelens.utils.paths import extract_project_name as _extract_project_name

MAX_FIRST_MESSAGE_LENGTH = 200


class BaseParser(ABC):
    """Abstract base for format-specific session parsers.

    Provides shared constants and helpers used by all ingest formats:
    project name extraction, project path encoding, and first-message
    truncation.
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
