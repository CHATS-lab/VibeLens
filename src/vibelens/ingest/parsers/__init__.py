"""Format-specific session parsers.

Each parser normalises a vendor-specific session format into ATIF
Trajectory objects for downstream analytics and storage.
"""

from vibelens.ingest.parsers.base import BaseParser
from vibelens.ingest.parsers.claude import ClaudeParser, count_history_entries
from vibelens.ingest.parsers.claude_web import ClaudeWebParser
from vibelens.ingest.parsers.codex import CodexParser
from vibelens.ingest.parsers.dataclaw import DataclawParser
from vibelens.ingest.parsers.gemini import GeminiParser
from vibelens.ingest.parsers.hermes import HermesParser
from vibelens.ingest.parsers.openclaw import OpenClawParser
from vibelens.ingest.parsers.parsed import ParsedTrajectoryParser

# Parsers that support local agent data directory discovery.
# Used by LocalStore to scan the user's machine for session files.
LOCAL_PARSER_CLASSES: list[type[BaseParser]] = [
    ClaudeParser,
    CodexParser,
    GeminiParser,
    HermesParser,
    OpenClawParser,
]

__all__ = [
    "LOCAL_PARSER_CLASSES",
    "BaseParser",
    "ClaudeParser",
    "ClaudeWebParser",
    "CodexParser",
    "DataclawParser",
    "GeminiParser",
    "HermesParser",
    "OpenClawParser",
    "ParsedTrajectoryParser",
    "count_history_entries",
]
