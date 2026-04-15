"""Registry of third-party agent extension directories.

All supported agents use the same SKILL.md + YAML frontmatter format
and are instantiated as plain DiskExtensionStore instances.

Registry:
    AGENT_EXTENSION_REGISTRY maps each ExtensionSource to its default
    skills directory path. Use create_agent_extension_stores() to
    instantiate stores for all agents installed on disk.
"""

from pathlib import Path

from vibelens.models.skill import ExtensionSource
from vibelens.storage.skill.disk import DiskExtensionStore

AGENT_EXTENSION_REGISTRY: dict[ExtensionSource, Path] = {
    ExtensionSource.CURSOR: Path.home() / ".cursor" / "skills",
    ExtensionSource.OPENCODE: Path.home() / ".config" / "opencode" / "skills",
    ExtensionSource.ANTIGRAVITY: Path.home() / ".gemini" / "antigravity" / "global_skills",
    ExtensionSource.KIMI: Path.home() / ".config" / "agents" / "skills",
    ExtensionSource.OPENCLAW: Path.home() / ".openclaw" / "skills",
    ExtensionSource.OPENHANDS: Path.home() / ".openhands" / "skills",
    ExtensionSource.QWEN: Path.home() / ".qwen" / "skills",
    ExtensionSource.GEMINI: Path.home() / ".gemini" / "skills",
    ExtensionSource.COPILOT: Path.home() / ".copilot" / "skills",
}


def create_agent_extension_stores() -> list[DiskExtensionStore]:
    """Instantiate stores for all registered third-party agents.

    Returns only stores whose skills directories exist on disk,
    so agents the user hasn't installed are silently skipped.
    """
    stores: list[DiskExtensionStore] = []
    for source_type, skills_dir in AGENT_EXTENSION_REGISTRY.items():
        resolved = skills_dir.expanduser().resolve()
        if resolved.is_dir():
            stores.append(DiskExtensionStore(resolved, source_type))
    return stores
