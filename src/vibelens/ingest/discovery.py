"""Session file discovery for extracted archives and local directories.

Walks directory trees and returns parseable session file paths,
filtering by agent-specific naming conventions.
"""

from pathlib import Path

from vibelens.models.enums import AgentType

# Claude Code session discovery constants
HISTORY_INDEX_FILENAME = "history.jsonl"
SUBAGENTS_DIR_NAME = "subagents"

# Directories to skip during recursive discovery
_SKIP_DIR_NAMES = {SUBAGENTS_DIR_NAME, "parsed"}

PARSEABLE_EXTENSIONS = {".json", ".jsonl"}


def discover_session_files(extracted_dir: Path, agent_type: str) -> list[Path]:
    """Walk directory and return parseable session file paths for a given agent.

    Filters files based on agent-specific naming conventions.
    Sub-agent files are excluded since parsers discover them
    from the directory layout.

    Args:
        extracted_dir: Root of the extracted zip contents.
        agent_type: One of AgentType values.

    Returns:
        List of paths to parseable session files.

    Raises:
        ValueError: If agent_type is unsupported.
    """
    agent = AgentType(agent_type)

    if agent == AgentType.CLAUDE_CODE:
        return _discover_claude_code(extracted_dir)
    if agent == AgentType.CODEX:
        return _discover_codex(extracted_dir)
    if agent == AgentType.GEMINI:
        return _discover_gemini(extracted_dir)

    raise ValueError(f"Unsupported agent_type: {agent_type}")


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


def _discover_claude_code(extracted_dir: Path) -> list[Path]:
    """Find Claude Code session files, excluding sub-agents and history index."""
    files = sorted(extracted_dir.rglob("*.jsonl"))
    return [
        f
        for f in files
        if not _SKIP_DIR_NAMES.intersection(f.parts) and f.name != HISTORY_INDEX_FILENAME
    ]


def _discover_codex(extracted_dir: Path) -> list[Path]:
    """Find Codex rollout session files."""
    return sorted(f for f in extracted_dir.rglob("*.jsonl") if f.stem.startswith("rollout-"))


def _discover_gemini(extracted_dir: Path) -> list[Path]:
    """Find Gemini session files inside chats/ directories."""
    return sorted(f for f in extracted_dir.rglob("session-*.json") if "chats" in f.parts)
