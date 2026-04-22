"""Subagent store — CRUD on a directory of flat .md subagent files.

Directory layout:
    <root>/
    ├── my-subagent.md
    ├── another-subagent.md
    └── ...

One file per subagent. Claude-style frontmatter (``name``, ``description``,
``tools``, ``model``) is parsed for metadata.
"""

from pathlib import Path

from vibelens.models.extension.subagent import Subagent
from vibelens.storage.extension.base_store import BaseExtensionStore
from vibelens.utils.content import compute_content_hash, parse_frontmatter
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

SUBAGENT_EXTENSION = ".md"


class SubagentStore(BaseExtensionStore[Subagent]):
    """CRUD on a single directory of flat .md subagent files.

    Each subagent is a single ``{name}.md`` file. All ``.md`` files in the
    root directory are treated as subagents.
    """

    def _item_path(self, name: str) -> Path:
        """Return path to the subagent's .md file."""
        return self._root / f"{name}{SUBAGENT_EXTENSION}"

    def _parse(self, name: str, text: str) -> Subagent:
        """Parse raw .md text into a Subagent."""
        return parse_subagent_md(name, text)

    def _iter_candidate_names(self) -> list[str]:
        """Return stems of .md files in the root directory."""
        return [
            entry.stem
            for entry in self._root.iterdir()
            if entry.is_file() and entry.suffix == SUBAGENT_EXTENSION
        ]


def parse_subagent_md(name: str, text: str) -> Subagent:
    """Parse raw subagent .md text into a Subagent model.

    Args:
        name: Subagent filename stem.
        text: Full .md content.

    Returns:
        Parsed Subagent with metadata from frontmatter.
    """
    frontmatter = parse_frontmatter(text, source=name)
    description = str(frontmatter.pop("description", ""))
    tags = frontmatter.pop("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip() for t in tags if str(t).strip()]
    content_hash = compute_content_hash(text)
    return Subagent(name=name, description=description, tags=tags, content_hash=content_hash)
