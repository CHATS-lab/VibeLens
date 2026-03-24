"""Format-specific session parsers.

Each parser normalises a vendor-specific session format into ATIF
Trajectory objects for downstream analytics and storage.
"""

from vibelens.ingest.parsers.base import BaseParser
from vibelens.ingest.parsers.claude_code import ClaudeCodeParser, count_history_entries
from vibelens.ingest.parsers.codex import CodexParser
from vibelens.ingest.parsers.dataclaw import DataclawParser
from vibelens.ingest.parsers.gemini import GeminiParser
from vibelens.ingest.parsers.parsed import ParsedTrajectoryParser

# Parsers that support local agent data directory discovery.
# Used by LocalStore to scan the user's machine for session files.
LOCAL_PARSER_CLASSES: list[type[BaseParser]] = [ClaudeCodeParser, CodexParser, GeminiParser]

__all__ = [
    "BaseParser",
    "ClaudeCodeParser",
    "CodexParser",
    "DataclawParser",
    "GeminiParser",
    "LOCAL_PARSER_CLASSES",
    "ParsedTrajectoryParser",
    "count_history_entries",
]
