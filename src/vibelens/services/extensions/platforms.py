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


# Single source of truth for "which platform field holds the install dir
# for extension type X". Used by deps.py when wiring per-type services and
# by the /agents endpoint to surface dirs_by_type directly to the frontend.
EXTENSION_TYPE_DIR_FIELD: dict[AgentExtensionType, str] = {
    AgentExtensionType.SKILL: "skills_dir",
    AgentExtensionType.COMMAND: "commands_dir",
    AgentExtensionType.SUBAGENT: "subagents_dir",
    AgentExtensionType.PLUGIN: "plugins_dir",
    AgentExtensionType.HOOK: "hook_config_path",
}


def platform_dir_for(platform: AgentPlatform, extension_type: AgentExtensionType) -> Path | None:
    """Return the install directory on ``platform`` for ``extension_type``, or None.

    None when the platform doesn't support this extension type or the
    type-specific field on the platform is unset.
    """
    if extension_type not in platform.supported_types:
        return None
    field_name = EXTENSION_TYPE_DIR_FIELD.get(extension_type)
    if field_name is None:
        return None
    return getattr(platform, field_name)


def _home(*parts: str) -> Path:
    return Path.home().joinpath(*parts)


def _build_platforms() -> dict[AgentType, AgentPlatform]:
    """Build the platform table using the current ``Path.home()``.

    Entries are ordered alphabetically by ``AgentType`` for easy lookup.
    Per-row comments cite the authoritative source for any non-skill
    directory or for any path that overrides skills-manage's ``db.rs``
    convention. Skill-only entries with no upstream filesystem-layout doc
    cite ``db.rs`` directly.

    Tests that patch ``HOME`` or ``Path.home`` should call
    :func:`rebuild_platforms` after the patch is applied so the
    module-level ``PLATFORMS`` dict picks up the new paths.
    """
    return {
        # Skills + Hooks: https://ampcode.com/manual.
        # Amp standardizes on XDG paths under ~/.config/amp/ (overrides
        # skills-manage db.rs:758 which uses ~/.amp/).
        AgentType.AMP: AgentPlatform(
            source=AgentType.AMP,
            root=_home(".config", "amp"),
            skills_dir=_home(".config", "amp", "skills"),
            hook_config_path=_home(".config", "amp", "settings.json"),
            supported_types=frozenset({AgentExtensionType.SKILL, AgentExtensionType.HOOK}),
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
        # Subagents + Hooks: https://docs.augmentcode.com/cli/subagents, /cli/hooks.
        # Commands: https://github.com/augmentcode/auggie/blob/main/README.md.
        # Skills: skills-manage db.rs:711 (Augment docs reference Agent Skills
        # feature but do not pin an exact path).
        AgentType.AUGMENT: AgentPlatform(
            source=AgentType.AUGMENT,
            root=_home(".augment"),
            skills_dir=_home(".augment", "skills"),
            commands_dir=_home(".augment", "commands"),
            subagents_dir=_home(".augment", "agents"),
            hook_config_path=_home(".augment", "settings.json"),
            supported_types=frozenset(
                {
                    AgentExtensionType.SKILL,
                    AgentExtensionType.COMMAND,
                    AgentExtensionType.SUBAGENT,
                    AgentExtensionType.HOOK,
                }
            ),
        ),
        # Skills: skills-manage db.rs:854. AutoClaw is Zhipu AI's one-click
        # OpenClaw installer (Hello-Claw guide documents only
        # ~/.openclaw-autoclaw/workspace, not the skills subdir).
        AgentType.AUTOCLAW: AgentPlatform(
            source=AgentType.AUTOCLAW,
            root=_home(".openclaw-autoclaw"),
            skills_dir=_home(".openclaw-autoclaw", "skills"),
            supported_types=frozenset({AgentExtensionType.SKILL}),
        ),
        AgentType.CLAUDE: AgentPlatform(
            source=AgentType.CLAUDE,
            root=_home(".claude"),
            skills_dir=_home(".claude", "skills"),
            commands_dir=_home(".claude", "commands"),
            subagents_dir=_home(".claude", "agents"),
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
        # Skills: https://staging-codebuddy.tencent.com/docs/cli/skills.
        # Commands: https://www.codebuddy.ai/docs/cli/slash-commands.
        # Subagents: https://www.codebuddy.ai/docs/cli/sub-agents.
        # Hooks: https://www.codebuddy.ai/docs/cli/hooks.
        # Plugins managed via /plugin command + settings.json (no fixed dir).
        AgentType.CODEBUDDY: AgentPlatform(
            source=AgentType.CODEBUDDY,
            root=_home(".codebuddy"),
            skills_dir=_home(".codebuddy", "skills"),
            commands_dir=_home(".codebuddy", "commands"),
            subagents_dir=_home(".codebuddy", "agents"),
            hook_config_path=_home(".codebuddy", "settings.json"),
            supported_types=frozenset(
                {
                    AgentExtensionType.SKILL,
                    AgentExtensionType.COMMAND,
                    AgentExtensionType.SUBAGENT,
                    AgentExtensionType.HOOK,
                }
            ),
        ),
        # Skills: https://developers.openai.com/codex/skills (canonical user path).
        # Codex CLI also reads ~/.codex/skills (legacy, deprecated) and
        # ~/.codex/skills/.system (OpenAI bundled). VibeLens manages only the
        # canonical user path. See openai/codex#11289.
        AgentType.CODEX: AgentPlatform(
            source=AgentType.CODEX,
            root=_home(".codex"),
            skills_dir=_home(".agents", "skills"),
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
        # Skills: skills-manage db.rs:843. EasyClaw is the native OpenClaw
        # desktop app; no ~/.easyclaw filesystem layout is published.
        AgentType.EASYCLAW: AgentPlatform(
            source=AgentType.EASYCLAW,
            root=_home(".easyclaw"),
            skills_dir=_home(".easyclaw", "skills"),
            supported_types=frozenset({AgentExtensionType.SKILL}),
        ),
        # Skills: https://docs.factory.ai/cli/configuration/skills.
        # Commands: https://docs.factory.ai/cli/configuration/custom-slash-commands.
        # Subagents (Factory's "droids"): https://docs.factory.ai/cli/configuration/custom-droids.
        # Hooks: https://docs.factory.ai/cli/configuration/hooks-guide.
        # Plugins dir not pinned in https://docs.factory.ai/cli/configuration/plugins.
        AgentType.FACTORY: AgentPlatform(
            source=AgentType.FACTORY,
            root=_home(".factory"),
            skills_dir=_home(".factory", "skills"),
            commands_dir=_home(".factory", "commands"),
            subagents_dir=_home(".factory", "droids"),
            hook_config_path=_home(".factory", "settings.json"),
            supported_types=frozenset(
                {
                    AgentExtensionType.SKILL,
                    AgentExtensionType.COMMAND,
                    AgentExtensionType.SUBAGENT,
                    AgentExtensionType.HOOK,
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
        # Skills: https://hermes-agent.nousresearch.com/docs/user-guide/features/skills.
        # Plugins: https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins.
        # Hooks: directory-style (~/.hermes/hooks/<name>/HOOK.yaml + handler.py)
        # does not fit HookService's JSON-merge model. Skipped.
        AgentType.HERMES: AgentPlatform(
            source=AgentType.HERMES,
            root=_home(".hermes"),
            skills_dir=_home(".hermes", "skills"),
            plugins_dir=_home(".hermes", "plugins"),
            supported_types=frozenset({AgentExtensionType.SKILL, AgentExtensionType.PLUGIN}),
        ),
        # Skills: https://junie.jetbrains.com/docs/agent-skills.html.
        # Commands: https://junie.jetbrains.com/docs/custom-slash-commands.html.
        # Subagents: https://junie.jetbrains.com/docs/junie-cli-subagents.html.
        # Hooks open feature request: JUNIE-1961.
        AgentType.JUNIE: AgentPlatform(
            source=AgentType.JUNIE,
            root=_home(".junie"),
            skills_dir=_home(".junie", "skills"),
            commands_dir=_home(".junie", "commands"),
            subagents_dir=_home(".junie", "agents"),
            supported_types=frozenset(
                {
                    AgentExtensionType.SKILL,
                    AgentExtensionType.COMMAND,
                    AgentExtensionType.SUBAGENT,
                }
            ),
        ),
        # Skills + Commands: https://kilo.ai/docs/cli (~/.kilocode/skills, ~/.kilocode/commands).
        # Subagents at a different parent: https://kilo.ai/docs/customize/custom-modes
        # (~/.config/kilo/agent — XDG-style, distinct from the legacy ~/.kilocode/).
        # Hooks: open feature request Kilo-Org/kilocode#5827.
        # Enum slug "kilo"; on-disk paths use the legacy ~/.kilocode/ root.
        # ``installed_platforms()`` OR-detects ``root`` and ``extra_paths`` so
        # users with only one of the two parent dirs still register.
        AgentType.KILO: AgentPlatform(
            source=AgentType.KILO,
            root=_home(".kilocode"),
            skills_dir=_home(".kilocode", "skills"),
            commands_dir=_home(".kilocode", "commands"),
            subagents_dir=_home(".config", "kilo", "agent"),
            extra_paths={"xdg_root": _home(".config", "kilo")},
            supported_types=frozenset(
                {
                    AgentExtensionType.SKILL,
                    AgentExtensionType.COMMAND,
                    AgentExtensionType.SUBAGENT,
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
        # Skills + Subagents: https://kiro.dev/docs/cli/custom-agents/configuration-reference/
        # (~/.kiro/skills, ~/.kiro/agents — global).
        # Hooks: workspace-only (.kiro/hooks/*.kiro.hook); global path tracked
        # at kirodotdev/Kiro#5440. Skipped here.
        AgentType.KIRO: AgentPlatform(
            source=AgentType.KIRO,
            root=_home(".kiro"),
            skills_dir=_home(".kiro", "skills"),
            subagents_dir=_home(".kiro", "agents"),
            supported_types=frozenset({AgentExtensionType.SKILL, AgentExtensionType.SUBAGENT}),
        ),
        # Skills: skills-manage db.rs:743. OB-1 is closed-source
        # (https://www.openblocklabs.com/manual); only the slug is public.
        AgentType.OB1: AgentPlatform(
            source=AgentType.OB1,
            root=_home(".ob1"),
            skills_dir=_home(".ob1", "skills"),
            supported_types=frozenset({AgentExtensionType.SKILL}),
        ),
        AgentType.OPENCLAW: AgentPlatform(
            source=AgentType.OPENCLAW,
            root=_home(".openclaw"),
            skills_dir=_home(".openclaw", "skills"),
            supported_types=frozenset({AgentExtensionType.SKILL}),
        ),
        # Skills: https://opencode.ai/docs/skills/. OpenCode reads from three
        # locations (~/.config/opencode/skills, ~/.claude/skills, ~/.agents/skills)
        # but VibeLens manages only the canonical XDG path. Config:
        # https://opencode.ai/docs/config/.
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
        AgentType.OPENHANDS: AgentPlatform(
            source=AgentType.OPENHANDS,
            root=_home(".openhands"),
            skills_dir=_home(".openhands", "skills"),
            supported_types=frozenset({AgentExtensionType.SKILL}),
        ),
        # Skills: skills-manage db.rs:832. QClaw (Tencent's one-click consumer
        # wrapper over OpenClaw) does not publish a ~/.qclaw filesystem layout.
        AgentType.QCLAW: AgentPlatform(
            source=AgentType.QCLAW,
            root=_home(".qclaw"),
            skills_dir=_home(".qclaw", "skills"),
            supported_types=frozenset({AgentExtensionType.SKILL}),
        ),
        # Skills: https://docs.qoder.com/extensions/skills.
        # Commands: https://docs.qoder.com/user-guide/commands.
        # Subagents: https://docs.qoder.com/extensions/subagent.
        # Hooks: https://docs.qoder.com/extensions/hooks.
        AgentType.QODER: AgentPlatform(
            source=AgentType.QODER,
            root=_home(".qoder"),
            skills_dir=_home(".qoder", "skills"),
            commands_dir=_home(".qoder", "commands"),
            subagents_dir=_home(".qoder", "agents"),
            hook_config_path=_home(".qoder", "settings.json"),
            supported_types=frozenset(
                {
                    AgentExtensionType.SKILL,
                    AgentExtensionType.COMMAND,
                    AgentExtensionType.SUBAGENT,
                    AgentExtensionType.HOOK,
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
        # Skills: skills-manage db.rs:637 (no upstream Trae doc pins ~/.trae/skills).
        # docs.trae.ai documents .trae/rules/, .trae/skills/ as project-level only.
        AgentType.TRAE: AgentPlatform(
            source=AgentType.TRAE,
            root=_home(".trae"),
            skills_dir=_home(".trae", "skills"),
            supported_types=frozenset({AgentExtensionType.SKILL}),
        ),
        # Skills: skills-manage db.rs:681. Trae CN is the China-region build of
        # Trae; docs.trae.cn does not publish on-disk paths.
        AgentType.TRAE_CN: AgentPlatform(
            source=AgentType.TRAE_CN,
            root=_home(".trae-cn"),
            skills_dir=_home(".trae-cn", "skills"),
            supported_types=frozenset({AgentExtensionType.SKILL}),
        ),
        # Skills: https://www.xmsumi.com/detail/2691, https://www.jieagi.com/aizixun/116.html
        # both confirm ~/.workbuddy/skills (overriding db.rs:869 which incorrectly
        # uses ~/.workbuddy/skills-marketplace/skills).
        # Hooks + Plugins: https://www.cnblogs.com/aquester/p/19714884
        # — settings.json (enabledPlugins) + plugins/marketplaces/<id>.
        AgentType.WORKBUDDY: AgentPlatform(
            source=AgentType.WORKBUDDY,
            root=_home(".workbuddy"),
            skills_dir=_home(".workbuddy", "skills"),
            hook_config_path=_home(".workbuddy", "settings.json"),
            plugins_dir=_home(".workbuddy", "plugins", "marketplaces"),
            supported_types=frozenset(
                {
                    AgentExtensionType.SKILL,
                    AgentExtensionType.HOOK,
                    AgentExtensionType.PLUGIN,
                }
            ),
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
    """Return platforms whose ``root`` or any ``extra_paths`` value exists on disk.

    OR-detection is needed for agents whose layout splits across multiple
    parent directories (e.g. Kilo: legacy ``~/.kilocode/`` for skills+commands
    plus newer XDG ``~/.config/kilo/`` for subagents). Single-root agents are
    unaffected — their default empty ``extra_paths`` dict contributes nothing.

    Returns:
        Dict mapping ``AgentType.value`` to platform for agents the user
        actually has installed.
    """
    return {
        p.source.value: p
        for p in PLATFORMS.values()
        if any(d.expanduser().is_dir() for d in (p.root, *p.extra_paths.values()))
    }
