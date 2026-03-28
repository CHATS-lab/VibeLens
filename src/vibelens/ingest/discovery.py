"""Session file discovery for extracted archives and local directories.

Walks directory trees and returns parseable session file paths,
filtering by agent-specific naming conventions.
"""

from pathlib import Path

from vibelens.ingest.parsers.base import BaseParser
from vibelens.ingest.parsers.claude_code import ClaudeCodeParser
from vibelens.ingest.parsers.codex import CodexParser
from vibelens.ingest.parsers.gemini import GeminiParser
from vibelens.ingest.parsers.openclaw import OpenClawParser
from vibelens.models.enums import AgentType

# Claude Code session discovery constants
HISTORY_INDEX_FILENAME = "history.jsonl"
SUBAGENTS_DIR_NAME = "subagents"

# Directories to skip during recursive discovery
_SKIP_DIR_NAMES = {SUBAGENTS_DIR_NAME, "parsed"}

PARSEABLE_EXTENSIONS = {".json", ".jsonl"}

_PARSERS_BY_TYPE: dict[AgentType, type[BaseParser]] = {
    AgentType.CLAUDE_CODE: ClaudeCodeParser,
    AgentType.CODEX: CodexParser,
    AgentType.GEMINI: GeminiParser,
    AgentType.OPENCLAW: OpenClawParser,
}


def get_parser(agent_type: str) -> BaseParser:
    """Instantiate a parser for the given agent type.

    Args:
        agent_type: One of AgentType values.

    Returns:
        Parser instance.

    Raises:
        ValueError: If agent_type is unsupported.
    """
    agent = AgentType(agent_type)
    parser_cls = _PARSERS_BY_TYPE.get(agent)
    if not parser_cls:
        raise ValueError(f"Unsupported agent_type: {agent_type}")
    return parser_cls()


def discover_session_files(extracted_dir: Path, agent_type: str) -> list[Path]:
    """Walk directory and return parseable session file paths for a given agent.

    Delegates to the parser's ``discover_session_files`` method for
    agent-specific filename filtering.

    Args:
        extracted_dir: Root of the extracted zip contents.
        agent_type: One of AgentType values.

    Returns:
        List of paths to parseable session files.

    Raises:
        ValueError: If agent_type is unsupported.
    """
    agent = AgentType(agent_type)
    parser_cls = _PARSERS_BY_TYPE.get(agent)
    if not parser_cls:
        raise ValueError(f"Unsupported agent_type: {agent_type}")
    return parser_cls().discover_session_files(extracted_dir)


def discover_all_session_files(directory: Path) -> list[Path]:
    """Walk directory and return all potential session files regardless of agent type.

    Excludes sub-agent files and history index files. Useful for
    demo mode loading where the agent type is unknown.

    Args:
        directory: Root directory to scan.

    Returns:
        Sorted list of parseable file paths.
    """
    files: list[Path] = []
    for ext in sorted(PARSEABLE_EXTENSIONS):
        for filepath in directory.rglob(f"*{ext}"):
            if _SKIP_DIR_NAMES.intersection(filepath.parts):
                continue
            if filepath.name == HISTORY_INDEX_FILENAME:
                continue
            files.append(filepath)
    return sorted(files)
