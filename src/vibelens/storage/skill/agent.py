"""Registry of third-party agent skill directories.

All supported agents use the same SKILL.md + YAML frontmatter format
and are instantiated as plain DiskSkillStore instances.

Registry:
    AGENT_SKILL_REGISTRY maps each SkillSourceType to its default
    skills directory path. Use create_agent_skill_stores() to
    instantiate stores for all agents installed on disk.
"""

from pathlib import Path

from vibelens.models.skill import SkillSourceType
from vibelens.storage.skill.disk import DiskSkillStore

AGENT_SKILL_REGISTRY: dict[SkillSourceType, Path] = {
    SkillSourceType.CURSOR: Path.home() / ".cursor" / "skills",
    SkillSourceType.OPENCODE: Path.home() / ".config" / "opencode" / "skills",
    SkillSourceType.ANTIGRAVITY: Path.home() / ".gemini" / "antigravity" / "global_skills",
    SkillSourceType.KIMI_CLI: Path.home() / ".config" / "agents" / "skills",
    SkillSourceType.OPENCLAW: Path.home() / ".openclaw" / "skills",
    SkillSourceType.OPENHANDS: Path.home() / ".openhands" / "skills",
    SkillSourceType.QWEN_CODE: Path.home() / ".qwen" / "skills",
    SkillSourceType.GEMINI_CLI: Path.home() / ".gemini" / "skills",
    SkillSourceType.COPILOT: Path.home() / ".copilot" / "skills",
}


def create_agent_skill_stores() -> list[DiskSkillStore]:
    """Instantiate stores for all registered third-party agents.

    Returns only stores whose skills directories exist on disk,
    so agents the user hasn't installed are silently skipped.
    """
    stores: list[DiskSkillStore] = []
    for source_type, skills_dir in AGENT_SKILL_REGISTRY.items():
        resolved = skills_dir.expanduser().resolve()
        if resolved.is_dir():
            stores.append(DiskSkillStore(resolved, source_type))
    return stores
