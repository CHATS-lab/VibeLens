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
from vibelens.models.enums import AgentType

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

# Every parser, including external-export and internal formats. Used to look
# up a parser by AgentType for upload, donation, and demo-mode pipelines.
ALL_PARSER_CLASSES: list[type[BaseParser]] = [
    *LOCAL_PARSER_CLASSES,
    ClaudeWebParser,
    DataclawParser,
    ParsedTrajectoryParser,
]

PARSERS_BY_AGENT_TYPE: dict[AgentType, type[BaseParser]] = {
    cls.AGENT_TYPE: cls for cls in ALL_PARSER_CLASSES
}


def get_parser(agent_type: AgentType | str) -> BaseParser:
    """Instantiate a parser for the given AgentType.

    Args:
        agent_type: AgentType enum value or its string form.

    Returns:
        A fresh parser instance.

    Raises:
        ValueError: If no parser is registered for that AgentType.
    """
    agent = AgentType(agent_type) if isinstance(agent_type, str) else agent_type
    cls = PARSERS_BY_AGENT_TYPE.get(agent)
    if cls is None:
        raise ValueError(f"No parser registered for agent_type: {agent_type}")
    return cls()


__all__ = [
    "ALL_PARSER_CLASSES",
    "LOCAL_PARSER_CLASSES",
    "PARSERS_BY_AGENT_TYPE",
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
    "get_parser",
]
