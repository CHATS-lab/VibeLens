"""Disk-based skill storage for agents using SKILL.md format.

Directory layout (shared across all agents):
    <skills_dir>/
    ├── my-skill/
    │   ├── SKILL.md         (YAML frontmatter + markdown body)
    │   ├── scripts/         (optional)
    │   ├── references/      (optional)
    │   └── agents/          (optional)
    └── another-skill/
        └── SKILL.md

Used directly for Claude Code, Codex CLI, Cursor, Gemini CLI, and all
other agents that follow the standard skills/<name>/SKILL.md layout.
Subclassed by CentralExtensionStore (adds source metadata injection).
"""

import shutil
from pathlib import Path

import yaml

from vibelens.models.skill import (
    VALID_EXTENSION_NAME,
    ExtensionInfo,
    ExtensionSource,
    ExtensionSourceInfo,
)
from vibelens.storage.skill.base import BaseExtensionStore
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Required definition file inside each skill directory
SKILL_FILENAME = "SKILL.md"

# Optional subdirectories recognized inside a skill directory
KNOWN_SUBDIRS = ("scripts", "references", "agents", "assets")

# YAML frontmatter opening/closing marker in SKILL.md files
FRONTMATTER_DELIMITER = "---"


class DiskExtensionStore(BaseExtensionStore):
    """Concrete skill store backed by a directory of SKILL.md files.

    Constructor takes both skills_dir and source_type so any agent
    can be represented by a plain DiskExtensionStore instance.
    """

    def __init__(self, skills_dir: Path, source_type: ExtensionSource) -> None:
        super().__init__()
        self._skills_dir = skills_dir.expanduser().resolve()
        self._source_type = source_type

    @property
    def source_type(self) -> ExtensionSource:
        """Return the agent-specific source type."""
        return self._source_type

    @property
    def skills_dir(self) -> Path:
        """Return the root directory for this store's skills."""
        return self._skills_dir

    def list_skills(self) -> list[ExtensionInfo]:
        """Scan skills_dir and return metadata for all valid skill directories."""
        if not self._skills_dir.is_dir():
            logger.debug("Skills directory does not exist: %s", self._skills_dir)
            return []

        skills: list[ExtensionInfo] = []
        for entry in sorted(self._skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            name = entry.name
            if not VALID_EXTENSION_NAME.match(name):
                logger.debug("Skipping non-kebab-case skill dir: %s", name)
                continue
            skill_file = entry / SKILL_FILENAME
            if not skill_file.is_file():
                continue
            info = self._build_skill_info(name, entry, skill_file)
            if info:
                skills.append(info)

        logger.debug("Scanned %d skills from %s", len(skills), self._skills_dir)
        return skills

    def get_skill(self, name: str) -> ExtensionInfo | None:
        """Look up a single skill by directory name."""
        if not VALID_EXTENSION_NAME.match(name):
            return None
        skill_dir = self._skills_dir / name
        skill_file = skill_dir / SKILL_FILENAME
        if not skill_file.is_file():
            return None
        return self._build_skill_info(name, skill_dir, skill_file)

    def read_content(self, name: str) -> str | None:
        """Read the full SKILL.md content for a named skill."""
        skill_file = self._skills_dir / name / SKILL_FILENAME
        if not skill_file.is_file():
            return None
        return skill_file.read_text(encoding="utf-8")

    def write_skill(self, name: str, content: str) -> Path:
        """Create or overwrite a skill's SKILL.md file.

        Args:
            name: Skill name (must be valid kebab-case).
            content: Full SKILL.md content including frontmatter.

        Returns:
            Absolute path to the written SKILL.md file.

        Raises:
            ValueError: If name is not valid kebab-case.
        """
        if not VALID_EXTENSION_NAME.match(name):
            raise ValueError(f"Skill name must be kebab-case: {name!r}")

        skill_dir = self._skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_file = skill_dir / SKILL_FILENAME
        # LLM-generated content often has excessive trailing newlines
        normalized = content.rstrip() + "\n"
        skill_file.write_text(normalized, encoding="utf-8")
        self.invalidate_cache()

        logger.info("Wrote skill %r to %s", name, skill_file)
        return skill_file

    def delete_skill(self, name: str) -> bool:
        """Remove a skill directory entirely."""
        skill_dir = self._skills_dir / name
        if not skill_dir.is_dir():
            return False

        shutil.rmtree(skill_dir)
        self.invalidate_cache()

        logger.info("Deleted skill %r from %s", name, skill_dir)
        return True

    def _build_skill_info(
        self, name: str, skill_dir: Path, skill_file: Path
    ) -> ExtensionInfo | None:
        """Parse a SKILL.md and build ExtensionInfo metadata."""
        try:
            text = skill_file.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", skill_file, exc)
            return None

        frontmatter = parse_frontmatter(text)

        description = str(frontmatter.pop("description", ""))
        allowed_tools = parse_allowed_tools(frontmatter.pop("allowed-tools", None))
        frontmatter.pop("name", None)  # already using directory name

        return ExtensionInfo(
            name=name,
            description=description,
            sources=[ExtensionSourceInfo(source_type=self.source_type, source_path=str(skill_dir))],
            central_path=None,
            content_hash=ExtensionInfo.hash_content(text),
            metadata={
                **frontmatter,
                "allowed_tools": allowed_tools,
                "subdirs": detect_subdirs(skill_dir),
                "store_path": str(skill_dir),
                "line_count": text.count("\n") + 1,
            },
        )


def parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter from a SKILL.md file.

    Expects the file to start with '---' followed by YAML, closed by '---'.
    Returns an empty dict if no valid frontmatter is found.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return {}

    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_DELIMITER:
            end_idx = i
            break

    if end_idx is None:
        return {}

    yaml_text = "\n".join(lines[1:end_idx])
    try:
        parsed = yaml.safe_load(yaml_text)
        return parsed if isinstance(parsed, dict) else {}
    except yaml.YAMLError as exc:
        logger.warning("Failed to parse YAML frontmatter: %s", exc)
        return {}


def parse_allowed_tools(raw: str | list | None) -> list[str]:
    """Normalize allowed-tools from frontmatter into a list of tool names.

    Handles both comma-separated strings and YAML lists.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    return [t.strip() for t in str(raw).split(",") if t.strip()]


def detect_subdirs(skill_dir: Path) -> list[str]:
    """Return which KNOWN_SUBDIRS exist in the skill directory."""
    return [name for name in KNOWN_SUBDIRS if (skill_dir / name).is_dir()]


def extract_body(text: str) -> str:
    """Extract the markdown body after the YAML frontmatter.

    Leading blank lines between the closing ``---`` and the body content
    are stripped to prevent accumulation across repeated metadata injections.
    """
    if not text.startswith(FRONTMATTER_DELIMITER):
        return text
    end_idx = text.find(FRONTMATTER_DELIMITER, len(FRONTMATTER_DELIMITER))
    if end_idx < 0:
        return text
    return text[end_idx + len(FRONTMATTER_DELIMITER) :].lstrip("\n")
