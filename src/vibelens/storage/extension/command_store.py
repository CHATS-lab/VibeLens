"""Command store — CRUD on a directory of flat .md command files.

Directory layout:
    <root>/
    ├── my-command.md
    ├── another-command.md
    └── forked-subagent.md   (excluded: has fork: true in frontmatter)

Files with ``fork: true`` in frontmatter are subagents, not commands.
"""

from pathlib import Path

from vibelens.models.extension.command import Command
from vibelens.storage.extension.base_store import BaseExtensionStore
from vibelens.utils.content import compute_content_hash, parse_frontmatter
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

COMMAND_EXTENSION = ".md"


class CommandStore(BaseExtensionStore[Command]):
    """CRUD on a single directory of flat .md command files.

    Each command is a single ``{name}.md`` file with optional YAML frontmatter.
    Files with ``fork: true`` in frontmatter are excluded (those are subagents).
    """

    def _item_path(self, name: str) -> Path:
        """Return path to the command's .md file."""
        return self._root / f"{name}{COMMAND_EXTENSION}"

    def _parse(self, name: str, text: str) -> Command:
        """Parse raw .md text into a Command."""
        return parse_command_md(name, text)

    def _iter_candidate_names(self) -> list[str]:
        """Return stems of .md files in the root directory."""
        return [
            entry.stem
            for entry in self._root.iterdir()
            if entry.is_file() and entry.suffix == COMMAND_EXTENSION
        ]

    def _include(self, name: str, raw: str) -> bool:
        """Exclude files with fork: true (those are subagents)."""
        frontmatter = parse_frontmatter(raw, source=str(self._item_path(name)))
        return not frontmatter.get("fork", False)


def parse_command_md(name: str, text: str) -> Command:
    """Parse raw command .md text into a Command model.

    Args:
        name: Command filename stem.
        text: Full .md content.

    Returns:
        Parsed Command with metadata from frontmatter.
    """
    frontmatter = parse_frontmatter(text, source=name)
    description = str(frontmatter.pop("description", ""))
    tags = frontmatter.pop("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip() for t in tags if str(t).strip()]
    content_hash = compute_content_hash(text)
    return Command(name=name, description=description, tags=tags, content_hash=content_hash)
