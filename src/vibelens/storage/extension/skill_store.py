"""Skill store — CRUD on a directory of SKILL.md folders.

Directory layout:
    <root>/
    ├── my-skill/
    │   ├── SKILL.md         (YAML frontmatter + markdown body)
    │   ├── scripts/         (optional)
    │   └── references/      (optional)
    └── another-skill/
        └── SKILL.md
"""

import shutil
from pathlib import Path

from vibelens.models.extension.skill import Skill
from vibelens.storage.extension.base_store import BaseExtensionStore
from vibelens.utils.content import compute_content_hash, parse_frontmatter
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

SKILL_FILENAME = "SKILL.md"


class SkillStore(BaseExtensionStore[Skill]):
    """CRUD on a single directory of skill subdirectories.

    Each skill lives in a subdirectory named after the skill (kebab-case)
    and contains a SKILL.md file with YAML frontmatter. Optional ``scripts/``
    and ``references/`` subdirectories are copied along with the SKILL.md.
    """

    def _item_path(self, name: str) -> Path:
        """Return path to the skill's SKILL.md inside its named subdirectory."""
        return self._root / name / SKILL_FILENAME

    def _item_root(self, name: str) -> Path:
        """Return the skill's on-disk directory (containing SKILL.md + assets)."""
        return self._root / name

    def _parse(self, name: str, text: str) -> Skill:
        """Parse raw SKILL.md text into a Skill."""
        return parse_skill_md(name, text)

    def _iter_candidate_names(self) -> list[str]:
        """Return names of subdirectories that contain a SKILL.md file."""
        return [
            entry.name
            for entry in self._root.iterdir()
            if entry.is_dir() and (entry / SKILL_FILENAME).is_file()
        ]

    def _delete_impl(self, name: str) -> bool:
        """Remove the skill's entire subdirectory tree."""
        skill_dir = self._root / name
        if not skill_dir.is_dir():
            return False
        shutil.rmtree(skill_dir)
        return True

    def _copy_impl(self, source: BaseExtensionStore[Skill], name: str) -> bool:
        """Copy the full skill subdirectory tree (including scripts, references)."""
        source_dir = source.root / name
        if not (source_dir / SKILL_FILENAME).is_file():
            return False
        target_dir = self._root / name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, target_dir)
        return True


def parse_skill_md(name: str, text: str) -> Skill:
    """Parse raw SKILL.md text into a Skill model.

    Args:
        name: Skill directory name.
        text: Full SKILL.md content.

    Returns:
        Parsed Skill with metadata from frontmatter.
    """
    frontmatter = parse_frontmatter(text, source=f"{name}/SKILL.md")
    description = str(frontmatter.pop("description", ""))
    tags = frontmatter.pop("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip() for t in tags if str(t).strip()]

    raw_tools = frontmatter.pop("allowed-tools", None)
    allowed_tools = _parse_allowed_tools(raw_tools)

    content_hash = compute_content_hash(text)

    return Skill(
        name=name,
        description=description,
        tags=tags,
        allowed_tools=allowed_tools,
        content_hash=content_hash,
    )


def _parse_allowed_tools(raw: str | list | None) -> list[str]:
    """Normalize allowed-tools from frontmatter into a list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    return [t.strip() for t in str(raw).split(",") if t.strip()]
