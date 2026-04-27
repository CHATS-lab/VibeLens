"""Tests for catalog_resolver install/uninstall dispatch.

Install paths download from GitHub: directory-shaped items via
``download_directory``, single-file items (subagent / command whose
``source_url`` ends in ``.md``) via ``download_file``. HOOK and
MCP_SERVER are gated upstream by services/extensions/catalog.py; this
module tests the resolver's direct entry points.
"""

from pathlib import Path

import pytest

from vibelens.models.enums import AgentExtensionType, AgentType
from vibelens.models.extension import AgentExtensionItem
from vibelens.services.extensions import catalog_resolver
from vibelens.services.extensions.catalog_resolver import (
    install_catalog_item,
    install_from_source_url,
    uninstall_extension,
)
from vibelens.services.extensions.platforms import AgentPlatform


def _make_item(
    *,
    extension_type: AgentExtensionType,
    name: str = "demo",
    source_url: str = "https://github.com/acme/widget/tree/main/skills/demo",
) -> AgentExtensionItem:
    return AgentExtensionItem(
        extension_id=f"tree:acme/widget:{extension_type.value}/{name}",
        extension_type=extension_type,
        name=name,
        source_url=source_url,
        repo_full_name="acme/widget",
        discovery_source="seed",
        topics=[],
        quality_score=70.0,
        popularity=0.5,
        stars=10,
        forks=0,
    )


def _stub_platform(monkeypatch, tmp_path: Path) -> AgentPlatform:
    """Install a fake platform with all dirs populated under tmp_path."""
    root = tmp_path / "agent-root"
    root.mkdir(parents=True)
    skills_dir = root / "skills"
    subagents_dir = root / "agents"
    commands_dir = root / "commands"

    platform = AgentPlatform(
        source=AgentType.CLAUDE,
        root=root,
        skills_dir=skills_dir,
        subagents_dir=subagents_dir,
        commands_dir=commands_dir,
        plugins_dir=root / "plugins",
        hook_config_path=root / "settings.json",
        supported_types=frozenset(
            {
                AgentExtensionType.SKILL,
                AgentExtensionType.SUBAGENT,
                AgentExtensionType.COMMAND,
                AgentExtensionType.PLUGIN,
            }
        ),
    )
    monkeypatch.setattr(catalog_resolver, "get_platform", lambda key: platform)
    return platform


def test_install_skill_routes_to_skills_dir(monkeypatch, tmp_path: Path):
    platform = _stub_platform(monkeypatch, tmp_path)
    captured: dict = {}

    def fake_download(*, source_url: str, target_dir: Path) -> bool:
        captured["url"] = source_url
        captured["dir"] = target_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "SKILL.md").write_text("---\nname: demo\n---\nbody")
        return True

    monkeypatch.setattr(catalog_resolver, "download_directory", fake_download)
    monkeypatch.setattr(
        catalog_resolver, "_mirror_skill_to_central", lambda *, name, target_dir: None
    )

    item = _make_item(extension_type=AgentExtensionType.SKILL)
    installed = install_catalog_item(item=item, target_platform="claude", overwrite=False)
    assert installed == platform.skills_dir / "demo"
    assert captured["dir"] == platform.skills_dir / "demo"
    print(f"skill installed at {installed}")


def test_install_subagent_single_file_routes_to_md(monkeypatch, tmp_path: Path):
    """Tree URL ending in .md installs as {name}.md, matching uninstall layout."""
    platform = _stub_platform(monkeypatch, tmp_path)
    captured: dict = {}

    def fake_download_file(*, source_url: str, target_path: Path) -> bool:
        captured["url"] = source_url
        captured["path"] = target_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("---\nname: reviewer\n---\nbody")
        return True

    monkeypatch.setattr(catalog_resolver, "download_file", fake_download_file)
    item = _make_item(
        extension_type=AgentExtensionType.SUBAGENT,
        name="reviewer",
        source_url="https://github.com/acme/widget/tree/main/agents/reviewer.md",
    )
    installed = install_catalog_item(item=item, target_platform="claude", overwrite=False)
    assert installed == platform.subagents_dir / "reviewer.md"
    assert captured["path"] == platform.subagents_dir / "reviewer.md"


def test_install_subagent_directory_routes_to_dir(monkeypatch, tmp_path: Path):
    """Tree URL to a directory installs as {name}/ with downloaded contents."""
    platform = _stub_platform(monkeypatch, tmp_path)

    def fake_download(*, source_url: str, target_dir: Path) -> bool:
        target_dir.mkdir(parents=True, exist_ok=True)
        return True

    monkeypatch.setattr(catalog_resolver, "download_directory", fake_download)
    item = _make_item(
        extension_type=AgentExtensionType.SUBAGENT,
        name="reviewer",
        source_url="https://github.com/acme/widget/tree/main/agents/reviewer",
    )
    installed = install_catalog_item(item=item, target_platform="claude", overwrite=False)
    assert installed == platform.subagents_dir / "reviewer"


def test_install_command_single_file_routes_to_md(monkeypatch, tmp_path: Path):
    platform = _stub_platform(monkeypatch, tmp_path)

    def fake_download_file(*, source_url: str, target_path: Path) -> bool:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("x")
        return True

    monkeypatch.setattr(catalog_resolver, "download_file", fake_download_file)
    item = _make_item(
        extension_type=AgentExtensionType.COMMAND,
        name="sync",
        source_url="https://github.com/acme/widget/tree/main/commands/sync.md",
    )
    installed = install_catalog_item(item=item, target_platform="claude", overwrite=False)
    assert installed == platform.commands_dir / "sync.md"


def test_install_unsupported_type_for_platform_raises(monkeypatch, tmp_path: Path):
    """Installing a SKILL onto a platform that doesn't support skills fails."""
    root = tmp_path / "agent-root"
    root.mkdir()
    platform = AgentPlatform(
        source=AgentType.CODEX,
        root=root,
        skills_dir=None,
        subagents_dir=None,
        commands_dir=None,
        plugins_dir=None,
        hook_config_path=None,
        supported_types=frozenset({AgentExtensionType.COMMAND}),
    )
    monkeypatch.setattr(catalog_resolver, "get_platform", lambda key: platform)

    item = _make_item(extension_type=AgentExtensionType.SKILL)
    with pytest.raises(ValueError, match="does not support"):
        install_catalog_item(item=item, target_platform="codex", overwrite=False)


def test_install_existing_dir_without_overwrite_raises(monkeypatch, tmp_path: Path):
    platform = _stub_platform(monkeypatch, tmp_path)
    (platform.skills_dir / "demo").mkdir(parents=True)

    monkeypatch.setattr(catalog_resolver, "download_directory", lambda **_: True)
    item = _make_item(extension_type=AgentExtensionType.SKILL)
    with pytest.raises(FileExistsError):
        install_catalog_item(item=item, target_platform="claude", overwrite=False)


def test_install_with_overwrite_proceeds(monkeypatch, tmp_path: Path):
    platform = _stub_platform(monkeypatch, tmp_path)
    target = platform.skills_dir / "demo"
    target.mkdir(parents=True)

    def fake_download(*, source_url: str, target_dir: Path) -> bool:
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "SKILL.md").write_text("new")
        return True

    monkeypatch.setattr(catalog_resolver, "download_directory", fake_download)
    monkeypatch.setattr(
        catalog_resolver, "_mirror_skill_to_central", lambda *, name, target_dir: None
    )
    item = _make_item(extension_type=AgentExtensionType.SKILL)
    installed = install_catalog_item(item=item, target_platform="claude", overwrite=True)
    assert installed == target


def test_install_from_source_url_invalid_url_raises(monkeypatch, tmp_path: Path):
    _stub_platform(monkeypatch, tmp_path)
    item = AgentExtensionItem(
        extension_id="bogus:1",
        extension_type=AgentExtensionType.SKILL,
        name="bogus",
        source_url="https://example.com/not-github",
        repo_full_name="acme/widget",
        discovery_source="seed",
        topics=[],
        quality_score=0.0,
        popularity=0.0,
        stars=0,
        forks=0,
    )
    with pytest.raises(ValueError, match="no installable content"):
        install_from_source_url(item=item, target_platform="claude", overwrite=False)


def test_install_download_failure_raises(monkeypatch, tmp_path: Path):
    _stub_platform(monkeypatch, tmp_path)
    monkeypatch.setattr(catalog_resolver, "download_directory", lambda **_: False)
    item = _make_item(extension_type=AgentExtensionType.SKILL)
    with pytest.raises(ValueError, match="Failed to download"):
        install_catalog_item(item=item, target_platform="claude", overwrite=False)


def test_uninstall_skill_directory(monkeypatch, tmp_path: Path):
    platform = _stub_platform(monkeypatch, tmp_path)
    target = platform.skills_dir / "demo"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("x")

    item = _make_item(extension_type=AgentExtensionType.SKILL)
    removed = uninstall_extension(item=item, target_platform="claude")
    assert removed == target
    assert not target.exists()


def test_uninstall_command_file(monkeypatch, tmp_path: Path):
    platform = _stub_platform(monkeypatch, tmp_path)
    platform.commands_dir.mkdir(parents=True, exist_ok=True)
    f = platform.commands_dir / "sync.md"
    f.write_text("---\nname: sync\n---")

    item = _make_item(extension_type=AgentExtensionType.COMMAND, name="sync")
    removed = uninstall_extension(item=item, target_platform="claude")
    assert removed == f
    assert not f.exists()


def test_uninstall_not_found_raises(monkeypatch, tmp_path: Path):
    _stub_platform(monkeypatch, tmp_path)
    item = _make_item(extension_type=AgentExtensionType.SKILL, name="missing")
    with pytest.raises(FileNotFoundError):
        uninstall_extension(item=item, target_platform="claude")
