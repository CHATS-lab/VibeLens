"""Platform registry and capability matrix tests.

Path assertions use ``str(...).endswith(...)`` rather than ``Path.home() / "..."``
so they're robust to other tests in the suite that monkeypatch ``Path.home`` /
``HOME`` and rebuild PLATFORMS without fully restoring it on teardown.
"""

from dataclasses import replace
from unittest.mock import patch

import pytest

from vibelens.models.enums import AgentExtensionType, AgentType
from vibelens.services.extensions.platforms import (
    PLATFORMS,
    get_platform,
    installed_platforms,
    rebuild_platforms,
)

# ---- Matrix shape & invariants ---------------------------------------------


def test_platforms_count_matches_spec():
    """27 = 11 pre-existing + 16 new (Aider intentionally excluded)."""
    assert len(PLATFORMS) == 27


def test_supported_types_are_consistent():
    """If a directory column is set, the matching extension type must be in
    supported_types."""
    for agent, p in PLATFORMS.items():
        assert AgentExtensionType.SKILL in p.supported_types, agent
        if p.commands_dir is not None:
            assert AgentExtensionType.COMMAND in p.supported_types, agent
        if p.subagents_dir is not None:
            assert AgentExtensionType.SUBAGENT in p.supported_types, agent
        if p.hook_config_path is not None:
            assert AgentExtensionType.HOOK in p.supported_types, agent
        if p.plugins_dir is not None:
            assert AgentExtensionType.PLUGIN in p.supported_types, agent


def test_install_key_removed():
    claude = PLATFORMS[AgentType.CLAUDE]
    assert not hasattr(claude, "install_key")


def test_hook_config_key_is_tuple():
    claude = PLATFORMS[AgentType.CLAUDE]
    assert claude.hook_config_key == ("hooks",)
    assert isinstance(claude.hook_config_key, tuple)


# ---- Per-agent supported_types and path checks -----------------------------


def test_claude_supports_all_five_types():
    claude = PLATFORMS[AgentType.CLAUDE]
    assert claude.supported_types == frozenset(
        {
            AgentExtensionType.SKILL,
            AgentExtensionType.COMMAND,
            AgentExtensionType.SUBAGENT,
            AgentExtensionType.HOOK,
            AgentExtensionType.PLUGIN,
        }
    )


def test_codex_uses_canonical_skills_path():
    """Per https://developers.openai.com/codex/skills, Codex's canonical user
    skills path is ~/.agents/skills (was ~/.codex/skills, deprecated)."""
    codex = PLATFORMS[AgentType.CODEX]
    assert codex.skills_dir.name == "skills"
    assert codex.skills_dir.parent.name == ".agents"


def test_codex_does_not_support_command():
    codex = PLATFORMS[AgentType.CODEX]
    assert AgentExtensionType.COMMAND not in codex.supported_types
    assert AgentExtensionType.SKILL in codex.supported_types
    assert AgentExtensionType.SUBAGENT in codex.supported_types


def test_codex_hook_config_path_is_hooks_json():
    codex = PLATFORMS[AgentType.CODEX]
    assert codex.hook_config_path is not None
    assert codex.hook_config_path.name == "hooks.json"


def test_cursor_hook_config_path_is_hooks_json():
    cursor = PLATFORMS[AgentType.CURSOR]
    assert cursor.hook_config_path is not None
    assert cursor.hook_config_path.name == "hooks.json"


def test_openhands_skill_only():
    openhands = PLATFORMS[AgentType.OPENHANDS]
    assert openhands.supported_types == frozenset({AgentExtensionType.SKILL})


@pytest.mark.parametrize(
    "agent, root_part, droids_subdir, has_hooks",
    [
        (AgentType.FACTORY, ".factory", "droids", True),
        (AgentType.JUNIE, ".junie", "agents", False),
        (AgentType.QODER, ".qoder", "agents", True),
        (AgentType.AUGMENT, ".augment", "agents", True),
        (AgentType.CODEBUDDY, ".codebuddy", "agents", True),
    ],
)
def test_fully_documented_agents_match_spec(agent, root_part, droids_subdir, has_hooks):
    """Spec § 4.2 'fully documented' rows. ``droids_subdir`` is the basename
    of subagents_dir (Factory uses 'droids', everyone else 'agents'). All
    'fully documented' agents have skills + commands + subagents; ``has_hooks``
    captures whether ``settings.json`` is also tracked."""
    p = PLATFORMS[agent]
    assert str(p.root).endswith(root_part)
    assert str(p.skills_dir).endswith(f"{root_part}/skills")
    assert str(p.commands_dir).endswith(f"{root_part}/commands")
    assert str(p.subagents_dir).endswith(f"{root_part}/{droids_subdir}")
    if has_hooks:
        assert str(p.hook_config_path).endswith(f"{root_part}/settings.json")
    else:
        assert p.hook_config_path is None


def test_kilo_paths_match_spec():
    """Kilo's subagents live at ~/.config/kilo/agent (different parent than skills/commands)."""
    p = PLATFORMS[AgentType.KILO]
    assert str(p.root).endswith(".kilocode")
    assert str(p.skills_dir).endswith(".kilocode/skills")
    assert str(p.commands_dir).endswith(".kilocode/commands")
    assert str(p.subagents_dir).endswith(".config/kilo/agent")
    xdg = p.extra_paths.get("xdg_root")
    assert xdg is not None and str(xdg).endswith(".config/kilo")


def test_kiro_skill_and_subagent_only():
    """Kiro: SKILL + SUBAGENT supported; no global hooks (workspace-only per Kiro#5440)."""
    p = PLATFORMS[AgentType.KIRO]
    assert str(p.skills_dir).endswith(".kiro/skills")
    assert str(p.subagents_dir).endswith(".kiro/agents")
    assert p.commands_dir is None
    assert p.hook_config_path is None
    assert p.plugins_dir is None
    assert p.supported_types == frozenset(
        {AgentExtensionType.SKILL, AgentExtensionType.SUBAGENT}
    )


def test_hermes_skill_and_plugin_only():
    """Hermes: directory-style hooks don't fit JSON-merge; ship SKILL + PLUGIN only."""
    p = PLATFORMS[AgentType.HERMES]
    assert str(p.skills_dir).endswith(".hermes/skills")
    assert str(p.plugins_dir).endswith(".hermes/plugins")
    assert p.hook_config_path is None
    assert p.supported_types == frozenset(
        {AgentExtensionType.SKILL, AgentExtensionType.PLUGIN}
    )


def test_amp_uses_xdg_paths():
    """Amp's official manual standardizes on XDG (~/.config/amp/), not ~/.amp/."""
    p = PLATFORMS[AgentType.AMP]
    assert str(p.root).endswith(".config/amp")
    assert str(p.skills_dir).endswith(".config/amp/skills")
    assert str(p.hook_config_path).endswith(".config/amp/settings.json")
    assert p.supported_types == frozenset(
        {AgentExtensionType.SKILL, AgentExtensionType.HOOK}
    )


@pytest.mark.parametrize(
    "agent, root_part",
    [
        (AgentType.TRAE, ".trae"),
        (AgentType.TRAE_CN, ".trae-cn"),
        (AgentType.OB1, ".ob1"),
        (AgentType.QCLAW, ".qclaw"),
        (AgentType.EASYCLAW, ".easyclaw"),
        (AgentType.AUTOCLAW, ".openclaw-autoclaw"),
    ],
)
def test_skill_only_agents_match_spec(agent, root_part):
    """Spec § 4.2 'skill-only' rows: paths cite skills-manage db.rs convention."""
    p = PLATFORMS[agent]
    assert str(p.root).endswith(root_part)
    assert str(p.skills_dir).endswith(f"{root_part}/skills")
    assert p.commands_dir is None
    assert p.subagents_dir is None
    assert p.hook_config_path is None
    assert p.plugins_dir is None
    assert p.supported_types == frozenset({AgentExtensionType.SKILL})


def test_workbuddy_full_coverage():
    """WorkBuddy: skill + hook + plugin per authoritative tutorials, overriding
    db.rs's incorrect ~/.workbuddy/skills-marketplace/skills path."""
    p = PLATFORMS[AgentType.WORKBUDDY]
    assert str(p.root).endswith(".workbuddy")
    assert str(p.skills_dir).endswith(".workbuddy/skills")
    assert str(p.hook_config_path).endswith(".workbuddy/settings.json")
    assert str(p.plugins_dir).endswith(".workbuddy/plugins/marketplaces")
    assert p.supported_types == frozenset(
        {
            AgentExtensionType.SKILL,
            AgentExtensionType.HOOK,
            AgentExtensionType.PLUGIN,
        }
    )


# ---- get_platform lookup ---------------------------------------------------


def test_get_platform_returns_claude():
    claude = get_platform("claude")
    assert claude.source == AgentType.CLAUDE


def test_get_platform_unknown_raises():
    with pytest.raises(ValueError, match="Unknown agent"):
        get_platform("does-not-exist")


# ---- installed_platforms detection -----------------------------------------


@pytest.fixture
def patched_home(tmp_path, monkeypatch, request):
    """Patch HOME and rebuild PLATFORMS for the test. The finalizer rebuilds
    again *after* monkeypatch restores HOME so subsequent tests see real-HOME
    paths instead of the leftover tmp_path."""
    monkeypatch.setenv("HOME", str(tmp_path))
    rebuild_platforms()
    request.addfinalizer(rebuild_platforms)
    return tmp_path


def test_installed_platforms_filters_by_root_exists(tmp_path):
    fake_claude_root = tmp_path / "claude_root"
    fake_claude_root.mkdir()
    fake_cursor_root = tmp_path / "cursor_root"  # intentionally not created

    fake_claude = replace(PLATFORMS[AgentType.CLAUDE], root=fake_claude_root)
    fake_cursor = replace(PLATFORMS[AgentType.CURSOR], root=fake_cursor_root)

    override = {
        AgentType.CLAUDE: fake_claude,
        AgentType.CURSOR: fake_cursor,
    }
    with patch.dict(PLATFORMS, override):
        installed = installed_platforms()
        assert "claude" in installed
        assert "cursor" not in installed


def test_kilo_detects_with_legacy_dir_only(patched_home):
    """Users with only the legacy ~/.kilocode/ install must register as installed."""
    (patched_home / ".kilocode").mkdir()
    assert "kilo" in installed_platforms()


def test_kilo_detects_with_xdg_dir_only(patched_home):
    """Users with only the new XDG ~/.config/kilo/ install must register as installed."""
    (patched_home / ".config" / "kilo").mkdir(parents=True)
    assert "kilo" in installed_platforms()


def test_kilo_not_detected_when_neither_dir_exists(patched_home):
    """Negative case: neither legacy nor XDG dir present."""
    assert "kilo" not in installed_platforms()
