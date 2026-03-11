"""Local Claude Code JSONL data source."""

from pathlib import Path


class LocalSource:
    """Read sessions from local ~/.claude/ directory.

    Not yet implemented.
    """

    def __init__(self, claude_dir: Path) -> None:
        self._claude_dir = claude_dir

    @property
    def source_type(self) -> str:
        return "local"

    @property
    def display_name(self) -> str:
        return f"Local ({self._claude_dir})"
