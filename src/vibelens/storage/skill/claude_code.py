"""Claude Code skill storage backend (~/.claude/skills/).

Directory layout:
    ~/.claude/skills/
    ├── my-skill/
    │   ├── SKILL.md         (YAML frontmatter + markdown body)
    │   ├── scripts/         (optional)
    │   ├── references/      (optional)
    │   └── agents/          (optional)
    └── another-skill/
        └── SKILL.md
"""

import shutil
from pathlib import Path

import yaml

from vibelens.models.enums import AgentType
from vibelens.models.skill import VALID_SKILL_NAME, SkillInfo
from vibelens.storage.skill.base import SkillStore
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

SKILL_FILENAME = "SKILL.md"
KNOWN_SUBDIRS = ("scripts", "references", "agents", "assets")
FRONTMATTER_DELIMITER = "---"


def _parse_frontmatter(text: str) -> dict:
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


def _parse_allowed_tools(raw: str | list | None) -> list[str]:
    """Normalize allowed-tools from frontmatter into a list of tool names.

    Handles both comma-separated strings and lists.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    return [t.strip() for t in str(raw).split(",") if t.strip()]


def _detect_subdirs(skill_dir: Path) -> list[str]:
    """Return which KNOWN_SUBDIRS exist in the skill directory."""
    return [name for name in KNOWN_SUBDIRS if (skill_dir / name).is_dir()]


class ClaudeCodeSkillStore(SkillStore):
    """Skill storage for Claude Code (~/.claude/skills/).

    Scans skill directories, parses YAML frontmatter from SKILL.md,
    and detects optional subdirectories (scripts, references, agents, assets).
    """

    def __init__(self, skills_dir: Path) -> None:
        super().__init__()
        self._skills_dir = skills_dir.expanduser().resolve()

    @property
    def agent_type(self) -> AgentType:
        """Return the agent type identifier."""
        return AgentType.CLAUDE_CODE

    @property
    def skills_dir(self) -> Path:
        """Return the root directory for Claude Code skills."""
        return self._skills_dir

    def list_skills(self) -> list[SkillInfo]:
        """Scan skills_dir and return metadata for all valid skill directories."""
        if not self._skills_dir.is_dir():
            logger.debug("Skills directory does not exist: %s", self._skills_dir)
            return []

        skills: list[SkillInfo] = []
        for entry in sorted(self._skills_dir.iterdir()):
            if not entry.is_dir():
                continue

            skill_file = entry / SKILL_FILENAME
            if not skill_file.is_file():
                continue

            name = entry.name
            if not VALID_SKILL_NAME.match(name):
                logger.debug("Skipping non-kebab-case skill dir: %s", name)
                continue

            info = self._build_skill_info(name, entry, skill_file)
            if info:
                skills.append(info)

        logger.debug("Scanned %d skills from %s", len(skills), self._skills_dir)
        return skills

    def get_skill(self, name: str) -> SkillInfo | None:
        """Look up a single skill by name."""
        skill_dir = self._skills_dir / name
        skill_file = skill_dir / SKILL_FILENAME
        if not skill_file.is_file():
            return None
        return self._build_skill_info(name, skill_dir, skill_file)

    def read_content(self, name: str) -> str | None:
        """Read the full SKILL.md content."""
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
        if not VALID_SKILL_NAME.match(name):
            raise ValueError(f"Skill name must be kebab-case: {name!r}")

        skill_dir = self._skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_file = skill_dir / SKILL_FILENAME
        skill_file.write_text(content, encoding="utf-8")
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

    def _build_skill_info(self, name: str, skill_dir: Path, skill_file: Path) -> SkillInfo | None:
        """Parse a SKILL.md and build SkillInfo metadata."""
        try:
            text = skill_file.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", skill_file, exc)
            return None

        frontmatter = _parse_frontmatter(text)

        # Extract known fields, put the rest in metadata
        description = str(frontmatter.pop("description", ""))
        allowed_tools = _parse_allowed_tools(frontmatter.pop("allowed-tools", None))
        frontmatter.pop("name", None)  # already using directory name

        return SkillInfo(
            name=name,
            description=description,
            agent_type=self.agent_type,
            path=skill_dir,
            allowed_tools=allowed_tools,
            subdirs=_detect_subdirs(skill_dir),
            metadata=frontmatter,
            line_count=text.count("\n") + 1,
        )
