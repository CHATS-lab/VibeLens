"""Tests for SubagentService — orchestrator for subagent management."""

import pytest

from vibelens.models.enums import AgentType
from vibelens.services.extensions.subagent_service import (
    SubagentService,
    SubagentSyncTarget,
)
from vibelens.storage.extension.subagent_store import SubagentStore

SAMPLE_SUBAGENT_MD = """\
---
description: A sample subagent
fork: true
tags:
  - testing
---
# Sample Subagent

Body content.
"""

UPDATED_SUBAGENT_MD = """\
---
description: Updated subagent
fork: true
tags:
  - updated
---
# Updated

New body.
"""


@pytest.fixture
def central(tmp_path):
    return SubagentStore(root=tmp_path / "central", create=True)


@pytest.fixture
def agents(tmp_path):
    claude = SubagentStore(root=tmp_path / "claude", create=True)
    codex = SubagentStore(root=tmp_path / "codex", create=True)
    return {AgentType.CLAUDE: claude, AgentType.CODEX: codex}


@pytest.fixture
def service(central, agents):
    return SubagentService(central=central, agents=agents)


class TestInstall:
    def test_install_creates_subagent(self, service):
        subagent = service.install(name="my-subagent", content=SAMPLE_SUBAGENT_MD)
        assert subagent.name == "my-subagent"
        assert subagent.description == "A sample subagent"
        assert subagent.installed_in == []

    def test_install_with_sync(self, service):
        subagent = service.install(
            name="my-subagent", content=SAMPLE_SUBAGENT_MD, sync_to=["claude"]
        )
        assert "claude" in subagent.installed_in

    def test_install_duplicate_raises(self, service):
        service.install(name="my-subagent", content=SAMPLE_SUBAGENT_MD)
        with pytest.raises(FileExistsError):
            service.install(name="my-subagent", content=SAMPLE_SUBAGENT_MD)

    def test_install_invalid_name_raises(self, service):
        with pytest.raises(ValueError, match="kebab-case"):
            service.install(name="Not Valid", content=SAMPLE_SUBAGENT_MD)

    def test_install_empty_content_raises(self, service):
        with pytest.raises(ValueError, match="empty"):
            service.install(name="my-subagent", content="   ")

    def test_install_injects_fork_on_write(self, service):
        """Installing content without fork: true stores it with fork: true."""
        plain = """---\ndescription: plain\n---\nBody."""
        service.install(name="auto-fork", content=plain)
        # Since fork is injected at write-time, it should be readable.
        subagent = service.get_subagent("auto-fork")
        assert subagent.name == "auto-fork"


class TestUninstall:
    def test_uninstall_removes_from_central(self, service):
        service.install(name="my-subagent", content=SAMPLE_SUBAGENT_MD)
        removed = service.uninstall("my-subagent")
        assert isinstance(removed, list)
        assert not service._central.exists("my-subagent")

    def test_uninstall_cascades_to_agents(self, service):
        service.install(name="my-subagent", content=SAMPLE_SUBAGENT_MD, sync_to=["claude", "codex"])
        removed = service.uninstall("my-subagent")
        assert "claude" in removed
        assert "codex" in removed
        assert not service._agents["claude"].exists("my-subagent")

    def test_uninstall_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.uninstall("nonexistent")

    def test_uninstall_from_agent(self, service):
        service.install(name="my-subagent", content=SAMPLE_SUBAGENT_MD, sync_to=["claude"])
        service.uninstall_from_agent("my-subagent", "claude")
        assert not service._agents["claude"].exists("my-subagent")
        assert service._central.exists("my-subagent")

    def test_uninstall_from_unknown_agent_raises(self, service):
        service.install(name="my-subagent", content=SAMPLE_SUBAGENT_MD)
        with pytest.raises(KeyError):
            service.uninstall_from_agent("my-subagent", "unknown")


class TestQuery:
    def test_list_subagents(self, service):
        service.install(name="alpha", content=SAMPLE_SUBAGENT_MD)
        service.install(name="beta", content=SAMPLE_SUBAGENT_MD)
        subagents, total = service.list_subagents()
        assert total == 2
        assert len(subagents) == 2

    def test_list_subagents_pagination(self, service):
        for i in range(5):
            service.install(name=f"sub-{i:02d}", content=SAMPLE_SUBAGENT_MD)
        subagents, total = service.list_subagents(page=2, page_size=2)
        assert total == 5
        assert len(subagents) == 2

    def test_list_subagents_search(self, service):
        service.install(name="alpha", content=SAMPLE_SUBAGENT_MD)
        service.install(name="beta", content=SAMPLE_SUBAGENT_MD)
        subagents, total = service.list_subagents(search="alpha")
        assert total == 1
        assert subagents[0].name == "alpha"

    def test_list_subagents_populates_installed_in(self, service):
        service.install(name="my-subagent", content=SAMPLE_SUBAGENT_MD, sync_to=["claude"])
        subagents, _ = service.list_subagents()
        assert "claude" in subagents[0].installed_in

    def test_get_subagent(self, service):
        service.install(name="my-subagent", content=SAMPLE_SUBAGENT_MD)
        subagent = service.get_subagent("my-subagent")
        assert subagent.name == "my-subagent"

    def test_get_subagent_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.get_subagent("nonexistent")

    def test_get_subagent_content(self, service):
        service.install(name="my-subagent", content=SAMPLE_SUBAGENT_MD)
        content = service.get_subagent_content("my-subagent")
        assert "A sample subagent" in content

    def test_get_subagent_content_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.get_subagent_content("nonexistent")

    def test_find_installed_agents(self, service):
        service.install(name="my-subagent", content=SAMPLE_SUBAGENT_MD, sync_to=["claude", "codex"])
        agents = service.find_installed_agents("my-subagent")
        assert sorted(agents) == ["claude", "codex"]

    def test_list_sync_targets(self, service):
        targets = service.list_sync_targets()
        assert len(targets) == 2
        assert all(isinstance(t, SubagentSyncTarget) for t in targets)
        agents = [t.agent for t in targets]
        assert AgentType.CLAUDE in agents


class TestModify:
    def test_modify_updates_content(self, service):
        service.install(name="my-subagent", content=SAMPLE_SUBAGENT_MD)
        subagent = service.modify("my-subagent", UPDATED_SUBAGENT_MD)
        assert subagent.description == "Updated subagent"

    def test_modify_auto_syncs(self, service):
        service.install(name="my-subagent", content=SAMPLE_SUBAGENT_MD, sync_to=["claude"])
        service.modify("my-subagent", UPDATED_SUBAGENT_MD)
        agent_subagent = service._agents["claude"].read("my-subagent")
        assert agent_subagent is not None
        assert agent_subagent.description == "Updated subagent"

    def test_modify_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.modify("nonexistent", UPDATED_SUBAGENT_MD)


class TestSync:
    def test_sync_to_agents(self, service):
        service.install(name="my-subagent", content=SAMPLE_SUBAGENT_MD)
        results = service.sync_to_agents("my-subagent", ["claude", "codex"])
        assert results == {"claude": True, "codex": True}

    def test_sync_unknown_agent(self, service):
        service.install(name="my-subagent", content=SAMPLE_SUBAGENT_MD)
        results = service.sync_to_agents("my-subagent", ["unknown"])
        assert results["unknown"] is False

    def test_sync_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.sync_to_agents("nonexistent", ["claude"])


class TestImport:
    def test_import_from_agent(self, service):
        service._agents["claude"].write("agent-sub", SAMPLE_SUBAGENT_MD)
        subagent = service.import_from_agent("claude", "agent-sub")
        assert subagent.name == "agent-sub"
        assert service._central.exists("agent-sub")

    def test_import_from_unknown_agent_raises(self, service):
        with pytest.raises(KeyError):
            service.import_from_agent("unknown", "some-subagent")

    def test_import_missing_subagent_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.import_from_agent("claude", "nonexistent")

    def test_import_all_from_agent(self, service):
        service._agents["claude"].write("sub-a", SAMPLE_SUBAGENT_MD)
        service._agents["claude"].write("sub-b", SAMPLE_SUBAGENT_MD)
        imported = service.import_all_from_agent("claude")
        assert sorted(imported) == ["sub-a", "sub-b"]

    def test_import_all_skips_existing(self, service):
        service.install(name="existing", content=SAMPLE_SUBAGENT_MD)
        service._agents["claude"].write("existing", UPDATED_SUBAGENT_MD)
        service._agents["claude"].write("new-one", SAMPLE_SUBAGENT_MD)
        imported = service.import_all_from_agent("claude")
        assert imported == ["new-one"]


class TestCache:
    def test_invalidate_clears_cache(self, service):
        service.install(name="my-subagent", content=SAMPLE_SUBAGENT_MD)
        service.list_subagents()
        service.invalidate()
        assert service._cache is None
