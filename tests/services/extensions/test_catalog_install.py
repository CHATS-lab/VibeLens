"""Tests for catalog extension install/uninstall service."""

import json
import shutil
from pathlib import Path
from unittest.mock import patch

from vibelens.models.enums import AgentExtensionType, AgentType, ExtensionSource
from vibelens.models.extension import ExtensionItem
from vibelens.services.extensions.catalog_install import (
    install_catalog_item,
    install_from_source_url,
    uninstall_extension,
)
from vibelens.services.extensions.hook_service import HookService
from vibelens.services.extensions.platforms import AgentPlatform
from vibelens.services.extensions.skill_service import SkillService
from vibelens.services.extensions.subagent_service import SubagentService
from vibelens.storage.extension.hook_store import HookStore
from vibelens.storage.extension.skill_store import SkillStore
from vibelens.storage.extension.subagent_store import SubagentStore

DEFAULT_SKILL_CONTENT = "# Test Skill\nContent"

INSTALL_MODULE = "vibelens.services.extensions.catalog_install"


def _make_platform(tmp_path: Path, name: str = ".claude") -> AgentPlatform:
    """Build an AgentPlatform rooted under tmp_path."""
    root = tmp_path / name
    return AgentPlatform(
        source=ExtensionSource.CLAUDE if name == ".claude" else ExtensionSource.CODEX,
        root=root,
        skills_dir=root / "skills",
        commands_dir=root / "commands",
        subagents_dir=root / "agents",
        settings_path=root / "settings.json",
        install_key="claude_code" if name == ".claude" else "codex",
    )


def _make_platforms(tmp_path: Path) -> dict[str, AgentPlatform]:
    """Build INSTALLABLE_PLATFORMS for claude_code and codex under tmp_path."""
    claude = _make_platform(tmp_path=tmp_path, name=".claude")
    codex = _make_platform(tmp_path=tmp_path, name=".codex")
    return {claude.install_key: claude, codex.install_key: codex}


def _make_skill_item(
    name: str = "test-skill",
    content: str = DEFAULT_SKILL_CONTENT,
) -> ExtensionItem:
    return ExtensionItem(
        extension_id=f"bwc:skill:{name}",
        extension_type=AgentExtensionType.SKILL,
        name=name,
        description="A test skill",
        tags=[],
        category="testing",
        platforms=["claude_code"],
        quality_score=80.0,
        popularity=0.5,
        updated_at="",
        source_url="",
        repo_full_name="",
        install_method="skill_file",
        install_content=content,
    )


def _make_subagent_item(name: str = "test-subagent") -> ExtensionItem:
    return ExtensionItem(
        extension_id=f"bwc:subagent:{name}",
        extension_type=AgentExtensionType.SUBAGENT,
        name=name,
        description="A test subagent",
        tags=[],
        category="testing",
        platforms=["claude_code"],
        quality_score=80.0,
        popularity=0.5,
        updated_at="",
        source_url="",
        repo_full_name="",
        install_method="skill_file",
        install_content="---\ndescription: A test subagent\n---\n# Body\n",
    )


def _make_hook_item() -> ExtensionItem:
    hook_entries = [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo test"}]}]
    hook_data = {"description": "Test hook", "hooks": {"PreToolUse": hook_entries}}
    return ExtensionItem(
        extension_id="bwc:hook:test-hook",
        extension_type=AgentExtensionType.HOOK,
        name="test-hook",
        description="A test hook",
        tags=[],
        category="automation",
        platforms=["claude_code"],
        quality_score=70.0,
        popularity=0.0,
        updated_at="",
        source_url="",
        repo_full_name="",
        install_method="hook_config",
        install_content=json.dumps(hook_data),
    )


def _make_mcp_item() -> ExtensionItem:
    mcp_data = {"mcpServers": {"test-mcp": {"command": "npx", "args": ["-y", "test-server"]}}}
    return ExtensionItem(
        extension_id="bwc:mcp:test-mcp",
        extension_type=AgentExtensionType.REPO,
        name="test-mcp",
        description="A test MCP",
        tags=[],
        category="mcp",
        platforms=["claude_code"],
        quality_score=70.0,
        popularity=0.0,
        updated_at="",
        source_url="",
        repo_full_name="",
        install_method="mcp_config",
        install_content=json.dumps(mcp_data),
    )


def _make_github_skill_item(name: str = "algorithmic-art") -> ExtensionItem:
    return ExtensionItem(
        extension_id=f"featured:skill:{name}",
        extension_type=AgentExtensionType.SKILL,
        name=name,
        description="A featured skill from GitHub",
        tags=[],
        category="featured",
        platforms=["claude_code"],
        quality_score=90.0,
        popularity=0.8,
        updated_at="",
        source_url="https://github.com/anthropics/skills/tree/main/skills/algorithmic-art",
        repo_full_name="",
        install_method="skill_file",
        install_content=None,
    )


def _make_brand_guidelines_item() -> ExtensionItem:
    """Create an ExtensionItem matching the brand-guidelines skill."""
    return ExtensionItem(
        extension_id="featured:skill:brand-guidelines",
        extension_type=AgentExtensionType.SKILL,
        name="brand-guidelines",
        description="Applies Anthropic brand colors and typography.",
        tags=["agent-skills"],
        category="ai-assistant",
        platforms=["claude_code", "codex"],
        quality_score=95.0,
        popularity=0.9,
        updated_at="2026-04-14T01:08:15Z",
        source_url="https://github.com/anthropics/skills/tree/main/skills/brand-guidelines",
        repo_full_name="",
        install_method="skill_file",
        install_content=None,
    )


# ---------------------------------------------------------------------------
# install_catalog_item tests
# ---------------------------------------------------------------------------


def test_install_skill_creates_file(tmp_path: Path):
    """Installing a skill writes {name}.md to commands directory."""
    platforms = _make_platforms(tmp_path=tmp_path)
    with patch(f"{INSTALL_MODULE}.INSTALLABLE_PLATFORMS", platforms):
        item = _make_skill_item()
        installed = install_catalog_item(item=item, target_platform="claude_code")
        assert installed.is_file()
        assert installed.read_text() == DEFAULT_SKILL_CONTENT
        assert installed == tmp_path / ".claude" / "commands" / "test-skill.md"
    print(f"Installed skill at: {installed}")


def test_install_subagent_routes_to_agents_dir(tmp_path: Path):
    """Installing a SUBAGENT lands in .claude/agents/{name}.md, not commands/."""
    platforms = _make_platforms(tmp_path=tmp_path)
    central = SubagentStore(root=tmp_path / "central-subagents", create=True)
    agent_store = SubagentStore(root=platforms["claude_code"].subagents_dir, create=True)
    service = SubagentService(central=central, agents={"claude_code": agent_store})
    with (
        patch(f"{INSTALL_MODULE}.INSTALLABLE_PLATFORMS", platforms),
        patch(f"{INSTALL_MODULE}.get_subagent_service", return_value=service),
    ):
        item = _make_subagent_item()
        installed = install_catalog_item(item=item, target_platform="claude_code")
        expected = tmp_path / ".claude" / "agents" / "test-subagent.md"
        assert installed == expected
        assert installed.is_file()
        assert not (tmp_path / ".claude" / "commands" / "test-subagent.md").exists()
    print(f"Installed subagent at: {installed}")


def test_install_skill_rejects_overwrite(tmp_path: Path):
    """Installing a skill to existing path raises FileExistsError."""
    platforms = _make_platforms(tmp_path=tmp_path)
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "test-skill.md").write_text("existing")
    with patch(f"{INSTALL_MODULE}.INSTALLABLE_PLATFORMS", platforms):
        item = _make_skill_item()
        try:
            install_catalog_item(item=item, target_platform="claude_code", overwrite=False)
            raise AssertionError("Expected FileExistsError")
        except FileExistsError:
            pass
    print("Correctly rejected overwrite")


def test_install_skill_allows_overwrite(tmp_path: Path):
    """Installing with overwrite=True replaces existing file."""
    platforms = _make_platforms(tmp_path=tmp_path)
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "test-skill.md").write_text("old content")
    with patch(f"{INSTALL_MODULE}.INSTALLABLE_PLATFORMS", platforms):
        item = _make_skill_item()
        installed = install_catalog_item(item=item, target_platform="claude_code", overwrite=True)
        assert installed.read_text() == DEFAULT_SKILL_CONTENT
    print("Overwrite succeeded")


def test_install_hook_appends_to_settings(tmp_path: Path):
    """Installing a hook appends to settings.json hooks."""
    platforms = _make_platforms(tmp_path=tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    settings_path = claude_dir / "settings.json"
    settings_path.write_text(json.dumps({"hooks": {}}))
    central = HookStore(root=tmp_path / "central-hooks", create=True)
    service = HookService(central=central, agent_settings={"claude_code": settings_path})
    with (
        patch(f"{INSTALL_MODULE}.INSTALLABLE_PLATFORMS", platforms),
        patch(f"{INSTALL_MODULE}.get_hook_service", return_value=service),
    ):
        item = _make_hook_item()
        install_catalog_item(item=item, target_platform="claude_code")
        settings = json.loads(settings_path.read_text())
        assert "PreToolUse" in settings["hooks"]
    print(f"Hook installed, settings: {json.dumps(settings, indent=2)}")


def test_install_mcp_merges_to_settings(tmp_path: Path):
    """Installing an MCP server merges into settings.json mcpServers."""
    platforms = _make_platforms(tmp_path=tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    settings_path = claude_dir / "settings.json"
    settings_path.write_text(json.dumps({"mcpServers": {}}))
    with patch(f"{INSTALL_MODULE}.INSTALLABLE_PLATFORMS", platforms):
        item = _make_mcp_item()
        install_catalog_item(item=item, target_platform="claude_code")
        settings = json.loads(settings_path.read_text())
        assert "test-mcp" in settings["mcpServers"]
    print(f"MCP installed: {list(settings['mcpServers'].keys())}")


def test_install_unknown_platform_raises():
    """Installing to unknown platform raises ValueError."""
    item = _make_skill_item()
    try:
        install_catalog_item(item=item, target_platform="unknown_agent")
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert "unknown_agent" in str(exc)
    print("Correctly rejected unknown platform")


# ---------------------------------------------------------------------------
# install_from_source_url tests
# ---------------------------------------------------------------------------


def test_install_from_source_url_downloads_to_skills_dir(tmp_path: Path):
    """Installing a featured skill downloads to skills/ directory."""
    platforms = _make_platforms(tmp_path=tmp_path)
    item = _make_github_skill_item()

    with (
        patch(f"{INSTALL_MODULE}.INSTALLABLE_PLATFORMS", platforms),
        patch(f"{INSTALL_MODULE}.download_directory", return_value=True) as mock_dl,
    ):
        installed = install_from_source_url(item=item, target_platform="claude_code")
        expected = tmp_path / ".claude" / "skills" / "algorithmic-art"
        assert installed == expected
        mock_dl.assert_called_once_with(source_url=item.source_url, target_dir=expected)
    print(f"Installed featured skill to: {installed}")


def test_install_from_source_url_rejects_existing_dir(tmp_path: Path):
    """Installing from source URL raises FileExistsError if directory exists."""
    platforms = _make_platforms(tmp_path=tmp_path)
    skill_dir = tmp_path / ".claude" / "skills" / "algorithmic-art"
    skill_dir.mkdir(parents=True)
    item = _make_github_skill_item()

    with patch(f"{INSTALL_MODULE}.INSTALLABLE_PLATFORMS", platforms):
        try:
            install_from_source_url(item=item, target_platform="claude_code", overwrite=False)
            raise AssertionError("Expected FileExistsError")
        except FileExistsError:
            pass
    print("Correctly rejected existing directory")


def test_install_from_source_url_raises_on_no_source():
    """Installing without source_url raises ValueError."""
    item = _make_skill_item()
    item.install_content = None
    item.source_url = ""
    try:
        install_from_source_url(item=item, target_platform="claude")
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert "no installable content" in str(exc)
    print("Correctly rejected missing source URL")


# ---------------------------------------------------------------------------
# Brand-guidelines multi-platform tests
# ---------------------------------------------------------------------------


def test_install_brand_guidelines_to_claude(tmp_path: Path):
    """Installing brand-guidelines to claude_code lands in ~/.claude/skills/."""
    platforms = _make_platforms(tmp_path=tmp_path)
    item = _make_brand_guidelines_item()

    with (
        patch(f"{INSTALL_MODULE}.INSTALLABLE_PLATFORMS", platforms),
        patch(f"{INSTALL_MODULE}.download_directory", return_value=True) as mock_dl,
    ):
        installed = install_from_source_url(item=item, target_platform="claude_code")
        expected = tmp_path / ".claude" / "skills" / "brand-guidelines"
        assert installed == expected, f"Expected {expected}, got {installed}"
        mock_dl.assert_called_once_with(source_url=item.source_url, target_dir=expected)
    print(f"brand-guidelines installed to claude: {installed}")


def test_install_brand_guidelines_to_codex(tmp_path: Path):
    """Installing brand-guidelines to codex lands in ~/.codex/skills/."""
    platforms = _make_platforms(tmp_path=tmp_path)
    item = _make_brand_guidelines_item()

    with (
        patch(f"{INSTALL_MODULE}.INSTALLABLE_PLATFORMS", platforms),
        patch(f"{INSTALL_MODULE}.download_directory", return_value=True) as mock_dl,
    ):
        installed = install_from_source_url(item=item, target_platform="codex")
        expected = tmp_path / ".codex" / "skills" / "brand-guidelines"
        assert installed == expected, f"Expected {expected}, got {installed}"
        mock_dl.assert_called_once_with(source_url=item.source_url, target_dir=expected)
    print(f"brand-guidelines installed to codex: {installed}")


# ---------------------------------------------------------------------------
# uninstall_extension tests
# ---------------------------------------------------------------------------


def test_uninstall_skill_directory(tmp_path: Path):
    """Uninstalling a directory-based skill removes the entire directory."""
    platforms = _make_platforms(tmp_path=tmp_path)
    skill_dir = tmp_path / ".claude" / "skills" / "brand-guidelines"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Brand Guidelines")
    item = _make_brand_guidelines_item()

    with patch(f"{INSTALL_MODULE}.INSTALLABLE_PLATFORMS", platforms):
        removed = uninstall_extension(item=item, target_platform="claude_code")
        assert removed == skill_dir
        assert not skill_dir.exists()
    print(f"Uninstalled directory skill from: {removed}")


def test_uninstall_command_file(tmp_path: Path):
    """Uninstalling a single-file skill removes the .md file."""
    platforms = _make_platforms(tmp_path=tmp_path)
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    command_file = commands_dir / "test-skill.md"
    command_file.write_text(DEFAULT_SKILL_CONTENT)
    item = _make_skill_item()

    with patch(f"{INSTALL_MODULE}.INSTALLABLE_PLATFORMS", platforms):
        removed = uninstall_extension(item=item, target_platform="claude_code")
        assert removed == command_file
        assert not command_file.exists()
    print(f"Uninstalled command file from: {removed}")


def test_uninstall_not_found_raises(tmp_path: Path):
    """Uninstalling a non-existent extension raises FileNotFoundError."""
    platforms = _make_platforms(tmp_path=tmp_path)
    item = _make_skill_item()

    with patch(f"{INSTALL_MODULE}.INSTALLABLE_PLATFORMS", platforms):
        try:
            uninstall_extension(item=item, target_platform="claude_code")
            raise AssertionError("Expected FileNotFoundError")
        except FileNotFoundError:
            pass
    print("Correctly raised FileNotFoundError for missing extension")


# ---------------------------------------------------------------------------
# Central store multi-file persistence tests
# ---------------------------------------------------------------------------


def _fake_download_source(source_dir: Path):
    """Return a download_directory stub that copies a prepared tree."""

    def _fake(source_url: str, target_dir: Path) -> bool:
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source_dir, target_dir)
        return True

    return _fake


def _build_multi_file_source(root: Path) -> Path:
    """Create a fake downloaded skill tree with SKILL.md + scripts/ + references/."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(
        "---\ndescription: Claude API helpers\n---\n# Claude API\nBody text.\n",
        encoding="utf-8",
    )
    scripts_dir = root / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "tool.py").write_text("print('hi')\n", encoding="utf-8")
    refs_dir = root / "references"
    refs_dir.mkdir()
    (refs_dir / "note.md").write_text("# Note\n", encoding="utf-8")
    return root


def test_install_from_source_copies_full_tree_to_central(tmp_path: Path):
    """Catalog install copies SKILL.md + scripts/ + references/ into the central store."""
    platforms = _make_platforms(tmp_path=tmp_path)
    source_tree = _build_multi_file_source(root=tmp_path / "source" / "claude-api")

    central_root = tmp_path / "central"
    codex_root = tmp_path / "codex-central-skills"
    central = SkillStore(root=central_root, create=True)
    codex_store = SkillStore(root=codex_root, create=True)
    service = SkillService(central=central, agents={AgentType.CODEX: codex_store})

    item = ExtensionItem(
        extension_id="featured:skill:claude-api",
        extension_type=AgentExtensionType.SKILL,
        name="claude-api",
        description="Claude API helpers",
        tags=[],
        category="featured",
        platforms=["claude_code"],
        quality_score=90.0,
        popularity=0.8,
        updated_at="",
        source_url="https://github.com/anthropics/skills/tree/main/skills/claude-api",
        repo_full_name="",
        install_method="skill_file",
        install_content=None,
    )

    with (
        patch(f"{INSTALL_MODULE}.INSTALLABLE_PLATFORMS", platforms),
        patch(f"{INSTALL_MODULE}.get_skill_service", return_value=service),
        patch(
            f"{INSTALL_MODULE}.download_directory",
            side_effect=_fake_download_source(source_dir=source_tree),
        ),
    ):
        install_from_source_url(item=item, target_platform="claude_code")

    central_skill_dir = central_root / "claude-api"
    assert (central_skill_dir / "SKILL.md").is_file()
    assert (central_skill_dir / "scripts" / "tool.py").is_file()
    assert (central_skill_dir / "references" / "note.md").is_file()
    central_entries = sorted(p.name for p in central_skill_dir.iterdir())
    print(f"Central store contents for claude-api: {central_entries}")

    # End-to-end: syncing from central to codex must carry auxiliary files too.
    service.sync_to_agents(name="claude-api", agents=["codex"])
    codex_skill_dir = codex_root / "claude-api"
    assert (codex_skill_dir / "SKILL.md").is_file()
    assert (codex_skill_dir / "scripts" / "tool.py").is_file()
    assert (codex_skill_dir / "references" / "note.md").is_file()
    print(f"Codex skill contents after sync: {sorted(p.name for p in codex_skill_dir.iterdir())}")
