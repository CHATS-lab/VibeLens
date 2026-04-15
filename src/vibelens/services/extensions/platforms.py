"""Central platform directory configurations for extension management.

Single source of truth for all agent platform paths. Used by:
- storage/extension/agent.py — reading existing skills from agent dirs
- services/extensions/install.py — installing catalog items to agent dirs
"""

from dataclasses import dataclass, field
from pathlib import Path

from vibelens.models.enums import ExtensionSource


@dataclass(frozen=True)
class AgentPlatform:
    """Directory layout for one agent platform.

    Attributes:
        source: Which agent this platform belongs to.
        root: Base directory (e.g. ~/.claude).
        skills_dir: Where multi-file skill directories live.
        commands_dir: Where single-file slash commands (.md) live.
        settings_path: JSON settings file for hooks/MCP config.
        install_key: Key used in API install requests (e.g. "claude_code").
    """

    source: ExtensionSource
    root: Path
    skills_dir: Path
    commands_dir: Path | None = None
    settings_path: Path | None = None
    install_key: str = ""
    extra_paths: dict[str, Path] = field(default_factory=dict)


def _home(*parts: str) -> Path:
    return Path.home().joinpath(*parts)


# All known agent platforms with their directory layouts.
# Only platforms with install_key are valid targets for catalog installation.
PLATFORMS: dict[ExtensionSource, AgentPlatform] = {
    ExtensionSource.CLAUDE: AgentPlatform(
        source=ExtensionSource.CLAUDE,
        root=_home(".claude"),
        skills_dir=_home(".claude", "skills"),
        commands_dir=_home(".claude", "commands"),
        settings_path=_home(".claude", "settings.json"),
        install_key="claude_code",
        extra_paths={"claude_json": _home(".claude.json")},
    ),
    ExtensionSource.CODEX: AgentPlatform(
        source=ExtensionSource.CODEX,
        root=_home(".codex"),
        skills_dir=_home(".codex", "skills"),
        commands_dir=_home(".codex", "commands"),
        settings_path=_home(".codex", "settings.json"),
        install_key="codex",
    ),
    ExtensionSource.CURSOR: AgentPlatform(
        source=ExtensionSource.CURSOR,
        root=_home(".cursor"),
        skills_dir=_home(".cursor", "skills"),
    ),
    ExtensionSource.OPENCODE: AgentPlatform(
        source=ExtensionSource.OPENCODE,
        root=_home(".config", "opencode"),
        skills_dir=_home(".config", "opencode", "skills"),
    ),
    ExtensionSource.ANTIGRAVITY: AgentPlatform(
        source=ExtensionSource.ANTIGRAVITY,
        root=_home(".gemini", "antigravity"),
        skills_dir=_home(".gemini", "antigravity", "global_skills"),
    ),
    ExtensionSource.KIMI: AgentPlatform(
        source=ExtensionSource.KIMI,
        root=_home(".config", "agents"),
        skills_dir=_home(".config", "agents", "skills"),
    ),
    ExtensionSource.OPENCLAW: AgentPlatform(
        source=ExtensionSource.OPENCLAW,
        root=_home(".openclaw"),
        skills_dir=_home(".openclaw", "skills"),
    ),
    ExtensionSource.OPENHANDS: AgentPlatform(
        source=ExtensionSource.OPENHANDS,
        root=_home(".openhands"),
        skills_dir=_home(".openhands", "skills"),
    ),
    ExtensionSource.QWEN: AgentPlatform(
        source=ExtensionSource.QWEN,
        root=_home(".qwen"),
        skills_dir=_home(".qwen", "skills"),
    ),
    ExtensionSource.GEMINI: AgentPlatform(
        source=ExtensionSource.GEMINI,
        root=_home(".gemini"),
        skills_dir=_home(".gemini", "skills"),
    ),
    ExtensionSource.COPILOT: AgentPlatform(
        source=ExtensionSource.COPILOT,
        root=_home(".copilot"),
        skills_dir=_home(".copilot", "skills"),
    ),
}

# Lookup from install_key → AgentPlatform (only platforms with install support)
INSTALLABLE_PLATFORMS: dict[str, AgentPlatform] = {
    p.install_key: p for p in PLATFORMS.values() if p.install_key
}
