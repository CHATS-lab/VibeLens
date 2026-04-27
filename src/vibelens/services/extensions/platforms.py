"""Central platform directory configurations and capability matrix.

Single source of truth for all agent platform paths and the set of
extension types each platform supports.
"""

from dataclasses import dataclass, field
from pathlib import Path

from vibelens.models.enums import AgentExtensionType, AgentType


@dataclass(frozen=True)
class AgentPlatform:
    """Directory layout and capabilities for one agent platform.

    Attributes:
        source: Which agent this platform belongs to.
        root: Base directory (e.g. ~/.claude).
        skills_dir: Where multi-file skill directories live.
        commands_dir: Where single-file slash commands (.md) live.
        subagents_dir: Where single-file subagent definitions (.md) live.
        plugins_dir: Where plugin directories live (None for Claude).
        hook_config_path: JSON file that holds hook configuration.
        hook_config_key: Path of JSON keys to traverse to reach hooks dict.
        supported_types: Extension types this agent can install.
        extra_paths: Opaque platform-specific extra paths.
    """

    source: AgentType
    root: Path
    skills_dir: Path
    commands_dir: Path | None = None
    subagents_dir: Path | None = None
    plugins_dir: Path | None = None
    hook_config_path: Path | None = None
    hook_config_key: tuple[str, ...] = ("hooks",)
    supported_types: frozenset[AgentExtensionType] = frozenset()
    extra_paths: dict[str, Path] = field(default_factory=dict)


def _home(*parts: str) -> Path:
    return Path.home().joinpath(*parts)


def _build_platforms() -> dict[AgentType, AgentPlatform]:
    """Build the platform table using the current ``Path.home()``.

    Tests that patch ``HOME`` or ``Path.home`` should call
    :func:`rebuild_platforms` after the patch is applied so the
    module-level ``PLATFORMS`` dict picks up the new paths.
    """
    return {
        AgentType.CLAUDE: AgentPlatform(
            source=AgentType.CLAUDE,
            root=_home(".claude"),
            skills_dir=_home(".claude", "skills"),
            commands_dir=_home(".claude", "commands"),
            subagents_dir=_home(".claude", "agents"),
            plugins_dir=None,
            hook_config_path=_home(".claude", "settings.json"),
            supported_types=frozenset(
                {
                    AgentExtensionType.SKILL,
                    AgentExtensionType.COMMAND,
                    AgentExtensionType.SUBAGENT,
                    AgentExtensionType.HOOK,
                    AgentExtensionType.PLUGIN,
                }
            ),
            extra_paths={"claude_json": _home(".claude.json")},
        ),
        AgentType.CODEX: AgentPlatform(
            source=AgentType.CODEX,
            root=_home(".codex"),
            skills_dir=_home(".codex", "skills"),
            subagents_dir=_home(".codex", "agents"),
            plugins_dir=_home(".codex", "plugins"),
            hook_config_path=_home(".codex", "hooks.json"),
            supported_types=frozenset(
                {
                    AgentExtensionType.SKILL,
                    AgentExtensionType.SUBAGENT,
                    AgentExtensionType.HOOK,
                    AgentExtensionType.PLUGIN,
                }
            ),
        ),
        AgentType.CURSOR: AgentPlatform(
            source=AgentType.CURSOR,
            root=_home(".cursor"),
            skills_dir=_home(".cursor", "skills"),
            commands_dir=_home(".cursor", "commands"),
            subagents_dir=_home(".cursor", "agents"),
            plugins_dir=_home(".cursor", "plugins"),
            hook_config_path=_home(".cursor", "hooks.json"),
            supported_types=frozenset(
                {
                    AgentExtensionType.SKILL,
                    AgentExtensionType.COMMAND,
                    AgentExtensionType.SUBAGENT,
                    AgentExtensionType.HOOK,
                    AgentExtensionType.PLUGIN,
                }
            ),
        ),
        AgentType.OPENCODE: AgentPlatform(
            source=AgentType.OPENCODE,
            root=_home(".config", "opencode"),
            skills_dir=_home(".config", "opencode", "skills"),
            commands_dir=_home(".config", "opencode", "commands"),
            subagents_dir=_home(".config", "opencode", "agents"),
            supported_types=frozenset(
                {
                    AgentExtensionType.SKILL,
                    AgentExtensionType.COMMAND,
                    AgentExtensionType.SUBAGENT,
                }
            ),
        ),
        AgentType.GEMINI: AgentPlatform(
            source=AgentType.GEMINI,
            root=_home(".gemini"),
            skills_dir=_home(".gemini", "skills"),
            subagents_dir=_home(".gemini", "subagents"),
            plugins_dir=_home(".gemini", "extensions"),
            hook_config_path=_home(".gemini", "settings.json"),
            supported_types=frozenset(
                {
                    AgentExtensionType.SKILL,
                    AgentExtensionType.SUBAGENT,
                    AgentExtensionType.HOOK,
                    AgentExtensionType.PLUGIN,
                }
            ),
        ),
        AgentType.COPILOT: AgentPlatform(
            source=AgentType.COPILOT,
            root=_home(".copilot"),
            skills_dir=_home(".copilot", "skills"),
            plugins_dir=_home(".copilot", "plugins"),
            hook_config_path=_home(".copilot", "config.json"),
            supported_types=frozenset(
                {
                    AgentExtensionType.SKILL,
                    AgentExtensionType.HOOK,
                    AgentExtensionType.PLUGIN,
                }
            ),
        ),
        AgentType.ANTIGRAVITY: AgentPlatform(
            source=AgentType.ANTIGRAVITY,
            root=_home(".gemini", "antigravity"),
            skills_dir=_home(".gemini", "antigravity", "global_skills"),
            commands_dir=_home(".gemini", "antigravity", "commands"),
            subagents_dir=_home(".gemini", "antigravity", "agents"),
            supported_types=frozenset(
                {
                    AgentExtensionType.SKILL,
                    AgentExtensionType.COMMAND,
                    AgentExtensionType.SUBAGENT,
                }
            ),
        ),
        AgentType.QWEN: AgentPlatform(
            source=AgentType.QWEN,
            root=_home(".qwen"),
            skills_dir=_home(".qwen", "skills"),
            subagents_dir=_home(".qwen", "agents"),
            hook_config_path=_home(".qwen", "settings.json"),
            supported_types=frozenset(
                {
                    AgentExtensionType.SKILL,
                    AgentExtensionType.SUBAGENT,
                    AgentExtensionType.HOOK,
                }
            ),
        ),
        AgentType.KIMI: AgentPlatform(
            source=AgentType.KIMI,
            root=_home(".config", "agents"),
            skills_dir=_home(".config", "agents", "skills"),
            subagents_dir=_home(".config", "agents", "agents"),
            supported_types=frozenset({AgentExtensionType.SKILL, AgentExtensionType.SUBAGENT}),
        ),
        AgentType.OPENCLAW: AgentPlatform(
            source=AgentType.OPENCLAW,
            root=_home(".openclaw"),
            skills_dir=_home(".openclaw", "skills"),
            supported_types=frozenset({AgentExtensionType.SKILL}),
        ),
        AgentType.OPENHANDS: AgentPlatform(
            source=AgentType.OPENHANDS,
            root=_home(".openhands"),
            skills_dir=_home(".openhands", "skills"),
            supported_types=frozenset({AgentExtensionType.SKILL}),
        ),
    }


PLATFORMS: dict[AgentType, AgentPlatform] = _build_platforms()


def rebuild_platforms() -> None:
    """Rebuild the module-level ``PLATFORMS`` dict from the current ``Path.home()``.

    Production code never calls this; ``Path.home()`` is stable within a
    process. Tests that monkeypatch ``HOME`` or ``Path.home`` call it
    after the patch so ``PLATFORMS`` reflects the test's fake home.
    Keeps ``PLATFORMS`` a real module-level dict (so existing
    ``patch.dict`` tests continue to work).
    """
    PLATFORMS.clear()
    PLATFORMS.update(_build_platforms())


def get_platform(key: str) -> AgentPlatform:
    """Look up a platform by AgentType value.

    Args:
        key: Platform key matching ``AgentType.value`` (e.g. "claude").

    Returns:
        Matching AgentPlatform.

    Raises:
        ValueError: If key does not match any known source.
    """
    try:
        source = AgentType(key)
    except ValueError as exc:
        raise ValueError(f"Unknown agent: {key!r}") from exc
    if source not in PLATFORMS:
        raise ValueError(f"Unknown agent: {key!r}")
    return PLATFORMS[source]


def installed_platforms() -> dict[str, AgentPlatform]:
    """Return platforms whose root directory exists on disk.

    Returns:
        Dict mapping ``AgentType.value`` to platform for agents the
        user actually has installed.
    """
    return {p.source.value: p for p in PLATFORMS.values() if p.root.expanduser().is_dir()}
