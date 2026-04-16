"""Tests for CommandService — orchestrator for command management."""

import pytest

from vibelens.models.enums import AgentType
from vibelens.services.extensions.command_service import (
    CommandService,
    CommandSyncTarget,
)
from vibelens.storage.extension.command_store import CommandStore

SAMPLE_COMMAND_MD = """\
---
description: A sample command
tags:
  - testing
---
# Sample Command

Body content.
"""

UPDATED_COMMAND_MD = """\
---
description: Updated command
tags:
  - updated
---
# Updated

New body.
"""


@pytest.fixture
def central(tmp_path):
    return CommandStore(root=tmp_path / "central", create=True)


@pytest.fixture
def agents(tmp_path):
    claude = CommandStore(root=tmp_path / "claude", create=True)
    codex = CommandStore(root=tmp_path / "codex", create=True)
    return {AgentType.CLAUDE: claude, AgentType.CODEX: codex}


@pytest.fixture
def service(central, agents):
    return CommandService(central=central, agents=agents)


class TestInstall:
    def test_install_creates_command(self, service):
        command = service.install(name="my-command", content=SAMPLE_COMMAND_MD)
        assert command.name == "my-command"
        assert command.description == "A sample command"
        assert command.installed_in == []

    def test_install_with_sync(self, service):
        command = service.install(name="my-command", content=SAMPLE_COMMAND_MD, sync_to=["claude"])
        assert "claude" in command.installed_in

    def test_install_duplicate_raises(self, service):
        service.install(name="my-command", content=SAMPLE_COMMAND_MD)
        with pytest.raises(FileExistsError):
            service.install(name="my-command", content=SAMPLE_COMMAND_MD)

    def test_install_invalid_name_raises(self, service):
        with pytest.raises(ValueError, match="kebab-case"):
            service.install(name="Not Valid", content=SAMPLE_COMMAND_MD)

    def test_install_empty_content_raises(self, service):
        with pytest.raises(ValueError, match="empty"):
            service.install(name="my-command", content="   ")


class TestUninstall:
    def test_uninstall_removes_from_central(self, service):
        service.install(name="my-command", content=SAMPLE_COMMAND_MD)
        removed = service.uninstall("my-command")
        assert isinstance(removed, list)
        assert not service._central.exists("my-command")

    def test_uninstall_cascades_to_agents(self, service):
        service.install(name="my-command", content=SAMPLE_COMMAND_MD, sync_to=["claude", "codex"])
        removed = service.uninstall("my-command")
        assert "claude" in removed
        assert "codex" in removed
        assert not service._agents["claude"].exists("my-command")

    def test_uninstall_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.uninstall("nonexistent")

    def test_uninstall_from_agent(self, service):
        service.install(name="my-command", content=SAMPLE_COMMAND_MD, sync_to=["claude"])
        service.uninstall_from_agent("my-command", "claude")
        assert not service._agents["claude"].exists("my-command")
        assert service._central.exists("my-command")

    def test_uninstall_from_unknown_agent_raises(self, service):
        service.install(name="my-command", content=SAMPLE_COMMAND_MD)
        with pytest.raises(KeyError):
            service.uninstall_from_agent("my-command", "unknown")


class TestQuery:
    def test_list_commands(self, service):
        service.install(name="alpha", content=SAMPLE_COMMAND_MD)
        service.install(name="beta", content=SAMPLE_COMMAND_MD)
        commands, total = service.list_commands()
        assert total == 2
        assert len(commands) == 2

    def test_list_commands_pagination(self, service):
        for i in range(5):
            service.install(name=f"cmd-{i:02d}", content=SAMPLE_COMMAND_MD)
        commands, total = service.list_commands(page=2, page_size=2)
        assert total == 5
        assert len(commands) == 2

    def test_list_commands_search(self, service):
        service.install(name="alpha", content=SAMPLE_COMMAND_MD)
        service.install(name="beta", content=SAMPLE_COMMAND_MD)
        commands, total = service.list_commands(search="alpha")
        assert total == 1
        assert commands[0].name == "alpha"

    def test_list_commands_populates_installed_in(self, service):
        service.install(name="my-command", content=SAMPLE_COMMAND_MD, sync_to=["claude"])
        commands, _ = service.list_commands()
        assert "claude" in commands[0].installed_in

    def test_get_command(self, service):
        service.install(name="my-command", content=SAMPLE_COMMAND_MD)
        command = service.get_command("my-command")
        assert command.name == "my-command"

    def test_get_command_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.get_command("nonexistent")

    def test_get_command_content(self, service):
        service.install(name="my-command", content=SAMPLE_COMMAND_MD)
        content = service.get_command_content("my-command")
        assert "A sample command" in content

    def test_get_command_content_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.get_command_content("nonexistent")

    def test_find_installed_agents(self, service):
        service.install(name="my-command", content=SAMPLE_COMMAND_MD, sync_to=["claude", "codex"])
        agents = service.find_installed_agents("my-command")
        assert sorted(agents) == ["claude", "codex"]

    def test_list_sync_targets(self, service):
        targets = service.list_sync_targets()
        assert len(targets) == 2
        assert all(isinstance(t, CommandSyncTarget) for t in targets)
        agents = [t.agent for t in targets]
        assert AgentType.CLAUDE in agents


class TestModify:
    def test_modify_updates_content(self, service):
        service.install(name="my-command", content=SAMPLE_COMMAND_MD)
        command = service.modify("my-command", UPDATED_COMMAND_MD)
        assert command.description == "Updated command"

    def test_modify_auto_syncs(self, service):
        service.install(name="my-command", content=SAMPLE_COMMAND_MD, sync_to=["claude"])
        service.modify("my-command", UPDATED_COMMAND_MD)
        agent_command = service._agents["claude"].read("my-command")
        assert agent_command is not None
        assert agent_command.description == "Updated command"

    def test_modify_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.modify("nonexistent", UPDATED_COMMAND_MD)


class TestSync:
    def test_sync_to_agents(self, service):
        service.install(name="my-command", content=SAMPLE_COMMAND_MD)
        results = service.sync_to_agents("my-command", ["claude", "codex"])
        assert results == {"claude": True, "codex": True}

    def test_sync_unknown_agent(self, service):
        service.install(name="my-command", content=SAMPLE_COMMAND_MD)
        results = service.sync_to_agents("my-command", ["unknown"])
        assert results["unknown"] is False

    def test_sync_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.sync_to_agents("nonexistent", ["claude"])


class TestImport:
    def test_import_from_agent(self, service):
        service._agents["claude"].write("agent-cmd", SAMPLE_COMMAND_MD)
        command = service.import_from_agent("claude", "agent-cmd")
        assert command.name == "agent-cmd"
        assert service._central.exists("agent-cmd")

    def test_import_from_unknown_agent_raises(self, service):
        with pytest.raises(KeyError):
            service.import_from_agent("unknown", "some-command")

    def test_import_missing_command_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.import_from_agent("claude", "nonexistent")

    def test_import_all_from_agent(self, service):
        service._agents["claude"].write("cmd-a", SAMPLE_COMMAND_MD)
        service._agents["claude"].write("cmd-b", SAMPLE_COMMAND_MD)
        imported = service.import_all_from_agent("claude")
        assert sorted(imported) == ["cmd-a", "cmd-b"]

    def test_import_all_skips_existing(self, service):
        service.install(name="existing", content=SAMPLE_COMMAND_MD)
        service._agents["claude"].write("existing", UPDATED_COMMAND_MD)
        service._agents["claude"].write("new-one", SAMPLE_COMMAND_MD)
        imported = service.import_all_from_agent("claude")
        assert imported == ["new-one"]


class TestCache:
    def test_invalidate_clears_cache(self, service):
        service.install(name="my-command", content=SAMPLE_COMMAND_MD)
        service.list_commands()
        service.invalidate()
        assert service._cache is None
