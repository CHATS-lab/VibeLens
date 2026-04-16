"""Tests that catalog install dispatches SUBAGENT/COMMAND/HOOK through typed services.

Verifies parity with skills: each install populates the central store
(``~/.vibelens/{type}/``) in addition to the agent-side destination, and hooks
carry the ``_vibelens_managed`` marker for safe dedup + per-platform uninstall.
"""

import json
from pathlib import Path
from unittest.mock import patch

from vibelens.models.enums import AgentExtensionType, AgentType, ExtensionSource
from vibelens.models.extension import ExtensionItem
from vibelens.services.extensions.catalog_install import install_catalog_item
from vibelens.services.extensions.command_service import CommandService
from vibelens.services.extensions.hook_service import HookService
from vibelens.services.extensions.platforms import AgentPlatform
from vibelens.services.extensions.subagent_service import SubagentService
from vibelens.storage.extension.command_store import CommandStore
from vibelens.storage.extension.hook_store import HookStore
from vibelens.storage.extension.subagent_store import SubagentStore

INSTALL_MODULE = "vibelens.services.extensions.catalog_install"
CLAUDE_KEY = "claude"
CODEX_KEY = "codex"

SUBAGENT_MD = "---\ndescription: A test subagent\n---\n# Body\n"
SUBAGENT_MD_V2 = "---\ndescription: Updated subagent\n---\n# Body v2\n"
COMMAND_MD = "---\ndescription: A test command\n---\n# Command body\n"
COMMAND_MD_V2 = "---\ndescription: Updated command\n---\n# Command v2\n"

HOOK_GROUP = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo first"}]}
HOOK_GROUP_V2 = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo second"}]}


def _make_platform(root: Path, source: ExtensionSource, install_key: str) -> AgentPlatform:
    """Build an AgentPlatform rooted under root."""
    return AgentPlatform(
        source=source,
        root=root,
        skills_dir=root / "skills",
        commands_dir=root / "commands",
        subagents_dir=root / "agents",
        settings_path=root / "settings.json",
        install_key=install_key,
    )


def _make_platforms(tmp_path: Path) -> dict[str, AgentPlatform]:
    claude = _make_platform(
        root=tmp_path / ".claude", source=ExtensionSource.CLAUDE, install_key=CLAUDE_KEY
    )
    codex = _make_platform(
        root=tmp_path / ".codex", source=ExtensionSource.CODEX, install_key=CODEX_KEY
    )
    return {claude.install_key: claude, codex.install_key: codex}


def _make_item(
    extension_type: AgentExtensionType,
    name: str,
    install_content: str,
    install_method: str = "skill_file",
) -> ExtensionItem:
    return ExtensionItem(
        extension_id=f"bwc:{extension_type.value}:{name}",
        extension_type=extension_type,
        name=name,
        description=f"A test {extension_type.value}",
        tags=[],
        category="testing",
        platforms=[CLAUDE_KEY],
        quality_score=80.0,
        popularity=0.5,
        updated_at="",
        source_url="",
        repo_full_name="",
        install_method=install_method,
        install_content=install_content,
    )


def _subagent_service(tmp_path: Path, platforms: dict[str, AgentPlatform]) -> SubagentService:
    """Build a SubagentService whose agents map matches the test platforms."""
    central = SubagentStore(root=tmp_path / "central-subagents", create=True)
    agents = {
        AgentType.CLAUDE: SubagentStore(root=platforms[CLAUDE_KEY].subagents_dir, create=True),
        AgentType.CODEX: SubagentStore(root=platforms[CODEX_KEY].subagents_dir, create=True),
    }
    return SubagentService(central=central, agents=agents)


def _command_service(tmp_path: Path, platforms: dict[str, AgentPlatform]) -> CommandService:
    central = CommandStore(root=tmp_path / "central-commands", create=True)
    agents = {
        AgentType.CLAUDE: CommandStore(root=platforms[CLAUDE_KEY].commands_dir, create=True),
        AgentType.CODEX: CommandStore(root=platforms[CODEX_KEY].commands_dir, create=True),
    }
    return CommandService(central=central, agents=agents)


def _hook_service(tmp_path: Path, platforms: dict[str, AgentPlatform]) -> HookService:
    central = HookStore(root=tmp_path / "central-hooks", create=True)
    agent_settings = {
        AgentType.CLAUDE: platforms[CLAUDE_KEY].settings_path,
        AgentType.CODEX: platforms[CODEX_KEY].settings_path,
    }
    return HookService(central=central, agent_settings=agent_settings)


def _patch_all(
    platforms: dict[str, AgentPlatform],
    subagent_svc: SubagentService | None = None,
    command_svc: CommandService | None = None,
    hook_svc: HookService | None = None,
):
    """Helper: layer patches for platforms + relevant service getters."""
    patches = [patch(f"{INSTALL_MODULE}.INSTALLABLE_PLATFORMS", platforms)]
    if subagent_svc is not None:
        patches.append(patch(f"{INSTALL_MODULE}.get_subagent_service", return_value=subagent_svc))
    if command_svc is not None:
        patches.append(patch(f"{INSTALL_MODULE}.get_command_service", return_value=command_svc))
    if hook_svc is not None:
        patches.append(patch(f"{INSTALL_MODULE}.get_hook_service", return_value=hook_svc))
    return patches


def _apply(patches):
    for p in patches:
        p.start()


def _stop(patches):
    for p in patches:
        p.stop()


# ---------------------------------------------------------------------------
# SUBAGENT dispatch
# ---------------------------------------------------------------------------


def test_subagent_install_populates_central_and_agent(tmp_path: Path):
    """Installing a SUBAGENT writes to both the agent directory and the central store."""
    platforms = _make_platforms(tmp_path=tmp_path)
    service = _subagent_service(tmp_path=tmp_path, platforms=platforms)
    item = _make_item(
        extension_type=AgentExtensionType.SUBAGENT, name="my-agent", install_content=SUBAGENT_MD
    )

    patches = _patch_all(platforms=platforms, subagent_svc=service)
    _apply(patches)
    try:
        returned = install_catalog_item(item=item, target_platform=CLAUDE_KEY)
    finally:
        _stop(patches)

    agent_file = platforms[CLAUDE_KEY].subagents_dir / "my-agent.md"
    central_file = tmp_path / "central-subagents" / "my-agent.md"
    assert returned == agent_file, f"Expected return path {agent_file}, got {returned}"
    assert agent_file.is_file(), "Subagent not written to agent dir"
    assert central_file.is_file(), "Subagent not written to central store"
    assert agent_file.read_text() == SUBAGENT_MD
    assert central_file.read_text() == SUBAGENT_MD
    print(f"Subagent install: agent={agent_file}, central={central_file}")


def test_subagent_install_second_platform_reuses_central(tmp_path: Path):
    """Installing the same subagent to a second platform keeps central intact and syncs agent2."""
    platforms = _make_platforms(tmp_path=tmp_path)
    service = _subagent_service(tmp_path=tmp_path, platforms=platforms)
    item = _make_item(
        extension_type=AgentExtensionType.SUBAGENT, name="shared", install_content=SUBAGENT_MD
    )

    patches = _patch_all(platforms=platforms, subagent_svc=service)
    _apply(patches)
    try:
        install_catalog_item(item=item, target_platform=CLAUDE_KEY)
        # Second platform install with overwrite=False — central already populated.
        returned = install_catalog_item(item=item, target_platform=CODEX_KEY, overwrite=False)
    finally:
        _stop(patches)

    claude_file = platforms[CLAUDE_KEY].subagents_dir / "shared.md"
    codex_file = platforms[CODEX_KEY].subagents_dir / "shared.md"
    central_file = tmp_path / "central-subagents" / "shared.md"
    assert returned == codex_file
    assert claude_file.is_file(), "Claude agent copy missing"
    assert codex_file.is_file(), "Codex agent copy missing"
    assert central_file.read_text() == SUBAGENT_MD, "Central must remain unchanged"
    print(f"Second platform install: codex={codex_file}")


def test_subagent_install_overwrite_true_replaces_central(tmp_path: Path):
    """overwrite=True on an existing central subagent updates its contents."""
    platforms = _make_platforms(tmp_path=tmp_path)
    service = _subagent_service(tmp_path=tmp_path, platforms=platforms)
    item_v1 = _make_item(
        extension_type=AgentExtensionType.SUBAGENT, name="swap", install_content=SUBAGENT_MD
    )
    item_v2 = _make_item(
        extension_type=AgentExtensionType.SUBAGENT, name="swap", install_content=SUBAGENT_MD_V2
    )

    patches = _patch_all(platforms=platforms, subagent_svc=service)
    _apply(patches)
    try:
        install_catalog_item(item=item_v1, target_platform=CLAUDE_KEY)
        install_catalog_item(item=item_v2, target_platform=CLAUDE_KEY, overwrite=True)
    finally:
        _stop(patches)

    central_file = tmp_path / "central-subagents" / "swap.md"
    agent_file = platforms[CLAUDE_KEY].subagents_dir / "swap.md"
    assert central_file.read_text() == SUBAGENT_MD_V2
    assert agent_file.read_text() == SUBAGENT_MD_V2
    print(f"Overwrite replaced central: {central_file}")


# ---------------------------------------------------------------------------
# COMMAND dispatch
# ---------------------------------------------------------------------------


def test_command_install_populates_central_and_agent(tmp_path: Path):
    """Installing a COMMAND writes to both the agent commands dir and the central store."""
    platforms = _make_platforms(tmp_path=tmp_path)
    service = _command_service(tmp_path=tmp_path, platforms=platforms)
    item = _make_item(
        extension_type=AgentExtensionType.COMMAND, name="run-task", install_content=COMMAND_MD
    )

    patches = _patch_all(platforms=platforms, command_svc=service)
    _apply(patches)
    try:
        returned = install_catalog_item(item=item, target_platform=CLAUDE_KEY)
    finally:
        _stop(patches)

    agent_file = platforms[CLAUDE_KEY].commands_dir / "run-task.md"
    central_file = tmp_path / "central-commands" / "run-task.md"
    assert returned == agent_file
    assert agent_file.is_file()
    assert central_file.is_file()
    assert central_file.read_text() == COMMAND_MD
    print(f"Command install: agent={agent_file}, central={central_file}")


def test_command_install_overwrite_true_replaces_central(tmp_path: Path):
    """overwrite=True on an existing central command updates its contents."""
    platforms = _make_platforms(tmp_path=tmp_path)
    service = _command_service(tmp_path=tmp_path, platforms=platforms)
    item_v1 = _make_item(
        extension_type=AgentExtensionType.COMMAND, name="swap-cmd", install_content=COMMAND_MD
    )
    item_v2 = _make_item(
        extension_type=AgentExtensionType.COMMAND, name="swap-cmd", install_content=COMMAND_MD_V2
    )

    patches = _patch_all(platforms=platforms, command_svc=service)
    _apply(patches)
    try:
        install_catalog_item(item=item_v1, target_platform=CLAUDE_KEY)
        install_catalog_item(item=item_v2, target_platform=CLAUDE_KEY, overwrite=True)
    finally:
        _stop(patches)

    central_file = tmp_path / "central-commands" / "swap-cmd.md"
    agent_file = platforms[CLAUDE_KEY].commands_dir / "swap-cmd.md"
    assert central_file.read_text() == COMMAND_MD_V2
    assert agent_file.read_text() == COMMAND_MD_V2


# ---------------------------------------------------------------------------
# HOOK dispatch
# ---------------------------------------------------------------------------


def _hook_payload(groups_by_event: dict[str, list[dict]]) -> str:
    return json.dumps({"description": "Test hook", "hooks": groups_by_event})


def test_hook_install_populates_central_and_tags_agent_settings(tmp_path: Path):
    """Installing a HOOK writes a central .json and tags merged groups in settings.json."""
    platforms = _make_platforms(tmp_path=tmp_path)
    service = _hook_service(tmp_path=tmp_path, platforms=platforms)
    item = _make_item(
        extension_type=AgentExtensionType.HOOK,
        name="test-hook",
        install_content=_hook_payload({"PreToolUse": [HOOK_GROUP]}),
        install_method="hook_config",
    )

    patches = _patch_all(platforms=platforms, hook_svc=service)
    _apply(patches)
    try:
        install_catalog_item(item=item, target_platform=CLAUDE_KEY)
    finally:
        _stop(patches)

    central_file = tmp_path / "central-hooks" / "test-hook.json"
    assert central_file.is_file(), "Hook JSON not written to central store"
    central_data = json.loads(central_file.read_text())
    assert "PreToolUse" in central_data["hook_config"]

    settings_path = platforms[CLAUDE_KEY].settings_path
    settings = json.loads(settings_path.read_text())
    groups = settings["hooks"]["PreToolUse"]
    assert len(groups) == 1
    assert groups[0]["_vibelens_managed"] == "test-hook"
    assert groups[0]["matcher"] == "Bash"
    print(f"Hook marker present: {groups[0]['_vibelens_managed']}")


def test_hook_install_dedups_via_marker(tmp_path: Path):
    """Repeating a hook install does not duplicate groups in settings.json."""
    platforms = _make_platforms(tmp_path=tmp_path)
    service = _hook_service(tmp_path=tmp_path, platforms=platforms)
    item = _make_item(
        extension_type=AgentExtensionType.HOOK,
        name="dedup-hook",
        install_content=_hook_payload({"PreToolUse": [HOOK_GROUP]}),
        install_method="hook_config",
    )

    patches = _patch_all(platforms=platforms, hook_svc=service)
    _apply(patches)
    try:
        install_catalog_item(item=item, target_platform=CLAUDE_KEY)
        install_catalog_item(item=item, target_platform=CLAUDE_KEY, overwrite=False)
    finally:
        _stop(patches)

    settings = json.loads(platforms[CLAUDE_KEY].settings_path.read_text())
    groups = settings["hooks"]["PreToolUse"]
    managed = [g for g in groups if g.get("_vibelens_managed") == "dedup-hook"]
    assert len(managed) == 1, f"Expected single managed group, got {len(managed)}"
    print(f"Dedup verified: {len(managed)} managed group(s)")


def test_hook_install_overwrite_updates_central_and_agent(tmp_path: Path):
    """overwrite=True replaces central hook_config and re-syncs tagged groups."""
    platforms = _make_platforms(tmp_path=tmp_path)
    service = _hook_service(tmp_path=tmp_path, platforms=platforms)
    item_v1 = _make_item(
        extension_type=AgentExtensionType.HOOK,
        name="swap-hook",
        install_content=_hook_payload({"PreToolUse": [HOOK_GROUP]}),
        install_method="hook_config",
    )
    item_v2 = _make_item(
        extension_type=AgentExtensionType.HOOK,
        name="swap-hook",
        install_content=_hook_payload({"PreToolUse": [HOOK_GROUP_V2]}),
        install_method="hook_config",
    )

    patches = _patch_all(platforms=platforms, hook_svc=service)
    _apply(patches)
    try:
        install_catalog_item(item=item_v1, target_platform=CLAUDE_KEY)
        install_catalog_item(item=item_v2, target_platform=CLAUDE_KEY, overwrite=True)
    finally:
        _stop(patches)

    settings = json.loads(platforms[CLAUDE_KEY].settings_path.read_text())
    groups = settings["hooks"]["PreToolUse"]
    managed = [g for g in groups if g.get("_vibelens_managed") == "swap-hook"]
    assert len(managed) == 1
    cmds = managed[0]["hooks"]
    assert cmds[0]["command"] == "echo second", f"Expected updated command, got {cmds}"
    print(f"Overwrite updated hook command: {cmds[0]['command']}")


def test_hook_uninstall_from_agent_removes_only_managed(tmp_path: Path):
    """HookService.uninstall_from_agent strips the marker group without touching others."""
    platforms = _make_platforms(tmp_path=tmp_path)
    service = _hook_service(tmp_path=tmp_path, platforms=platforms)

    # Seed an unmanaged group so we can verify it survives uninstall.
    settings_path = platforms[CLAUDE_KEY].settings_path
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    unmanaged = {
        "hooks": {
            "PreToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "ls"}]}]
        }
    }
    settings_path.write_text(json.dumps(unmanaged, indent=2))

    item = _make_item(
        extension_type=AgentExtensionType.HOOK,
        name="solo-hook",
        install_content=_hook_payload({"PreToolUse": [HOOK_GROUP]}),
        install_method="hook_config",
    )

    patches = _patch_all(platforms=platforms, hook_svc=service)
    _apply(patches)
    try:
        install_catalog_item(item=item, target_platform=CLAUDE_KEY)
        service.uninstall_from_agent(name="solo-hook", agent=AgentType.CLAUDE)
    finally:
        _stop(patches)

    settings = json.loads(settings_path.read_text())
    groups = settings["hooks"]["PreToolUse"]
    assert all(g.get("_vibelens_managed") != "solo-hook" for g in groups)
    unmanaged = [g for g in groups if g.get("matcher") == "Write"]
    assert len(unmanaged) == 1, "Unmanaged group should survive uninstall"
    print(f"Unmanaged survived: {unmanaged[0]['matcher']}")
