"""Format-specific session parsers.

Each parser normalises a vendor-specific session format into ATIF
Trajectory objects for downstream analytics and storage.
"""

from vibelens.ingest.parsers.base import BaseParser
from vibelens.ingest.parsers.claude import ClaudeParser
from vibelens.ingest.parsers.claude_web import ClaudeWebParser
from vibelens.ingest.parsers.codebuddy import CodebuddyParser
from vibelens.ingest.parsers.codex import CodexParser
from vibelens.ingest.parsers.copilot import CopilotParser
from vibelens.ingest.parsers.cursor import CursorParser
from vibelens.ingest.parsers.dataclaw import DataclawParser
from vibelens.ingest.parsers.gemini import GeminiParser
from vibelens.ingest.parsers.hermes import HermesParser
from vibelens.ingest.parsers.kilo import KiloParser
from vibelens.ingest.parsers.kiro import KiroParser
from vibelens.ingest.parsers.openclaw import OpenClawParser
from vibelens.ingest.parsers.opencode import OpencodeParser
from vibelens.ingest.parsers.parsed import ParsedTrajectoryParser

# Parsers that support local agent data directory discovery.
# Used by LocalStore to scan the user's machine for session files.
LOCAL_PARSER_CLASSES: list[type[BaseParser]] = [
    ClaudeParser,
    CodebuddyParser,
    CodexParser,
    CopilotParser,
    CursorParser,
    GeminiParser,
    HermesParser,
    KiloParser,
    KiroParser,
    OpenClawParser,
    OpencodeParser,
]

__all__ = [
    "LOCAL_PARSER_CLASSES",
    "BaseParser",
    "ClaudeParser",
    "ClaudeWebParser",
    "CodebuddyParser",
    "CodexParser",
    "CopilotParser",
    "CursorParser",
    "DataclawParser",
    "GeminiParser",
    "HermesParser",
    "KiloParser",
    "KiroParser",
    "OpenClawParser",
    "OpencodeParser",
    "ParsedTrajectoryParser",
]
