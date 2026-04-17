"""Tests for BaseExtensionService — shared extension management logic."""

import pytest

from vibelens.models.extension.skill import Skill
from vibelens.services.extensions.base_service import BaseExtensionService, SyncTarget
from vibelens.storage.extension.skill_store import SkillStore

SAMPLE_MD = """\
---
description: A sample skill
tags:
  - testing
---
# Sample

Body.
"""

UPDATED_MD = """\
---
description: Updated
tags:
  - updated
---
# Updated

New body.
"""


@pytest.fixture
def central(tmp_path):
    return SkillStore(root=tmp_path / "central", create=True)


@pytest.fixture
def agents(tmp_path):
    claude = SkillStore(root=tmp_path / "claude", create=True)
    codex = SkillStore(root=tmp_path / "codex", create=True)
    return {"claude": claude, "codex": codex}


@pytest.fixture
def service(central, agents):
    return BaseExtensionService[Skill](
        central_store=central,
        agent_stores=agents,
    )


class TestInstall:
    def test_creates_item(self, service):
        item = service.install(name="my-skill", content=SAMPLE_MD)
        assert item.name == "my-skill"
        assert item.description == "A sample skill"

    def test_syncs_to_agents(self, service):
        item = service.install(name="my-skill", content=SAMPLE_MD, sync_to=["claude"])
        assert "claude" in item.installed_in

    def test_duplicate_raises(self, service):
        service.install(name="my-skill", content=SAMPLE_MD)
        with pytest.raises(FileExistsError):
            service.install(name="my-skill", content=SAMPLE_MD)

    def test_bad_name_raises(self, service):
        with pytest.raises(ValueError, match="kebab-case"):
            service.install(name="Bad Name", content=SAMPLE_MD)

    def test_empty_content_raises(self, service):
        with pytest.raises(ValueError, match="empty"):
            service.install(name="my-skill", content="   ")


class TestModify:
    def test_updates_content(self, service):
        service.install(name="my-skill", content=SAMPLE_MD)
        updated = service.modify(name="my-skill", content=UPDATED_MD)
        assert updated.description == "Updated"

    def test_auto_syncs(self, service):
        service.install(name="my-skill", content=SAMPLE_MD, sync_to=["claude"])
        updated = service.modify(name="my-skill", content=UPDATED_MD)
        assert "claude" in updated.installed_in

    def test_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.modify(name="nope", content=UPDATED_MD)


class TestUninstall:
    def test_removes_from_central_and_agents(self, service):
        service.install(name="my-skill", content=SAMPLE_MD, sync_to=["claude"])
        removed = service.uninstall(name="my-skill")
        assert "claude" in removed
        with pytest.raises(FileNotFoundError):
            service.get_item(name="my-skill")

    def test_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.uninstall(name="nope")


class TestList:
    def test_empty(self, service):
        items, total = service.list_items(page=1, page_size=50)
        assert items == []
        assert total == 0

    def test_pagination(self, service):
        for i in range(5):
            service.install(name=f"skill-{i:02d}", content=SAMPLE_MD)
        items, total = service.list_items(page=1, page_size=2)
        assert len(items) == 2
        assert total == 5

    def test_search(self, service):
        service.install(name="alpha", content=SAMPLE_MD)
        service.install(name="beta", content=SAMPLE_MD)
        items, total = service.list_items(page=1, page_size=50, search="alpha")
        assert total == 1
        assert items[0].name == "alpha"


class TestSyncTargets:
    def test_returns_unified_targets(self, service):
        service.install(name="my-skill", content=SAMPLE_MD, sync_to=["claude"])
        targets = service.list_sync_targets()
        assert len(targets) == 2
        assert all(isinstance(t, SyncTarget) for t in targets)
        claude_target = next(t for t in targets if t.agent == "claude")
        assert claude_target.count >= 1


class TestSync:
    def test_sync_to_agents(self, service):
        service.install(name="my-skill", content=SAMPLE_MD)
        results = service.sync_to_agents(name="my-skill", agents=["claude", "codex"])
        assert results["claude"] is True
        assert results["codex"] is True

    def test_uninstall_from_agent(self, service):
        service.install(name="my-skill", content=SAMPLE_MD, sync_to=["claude"])
        service.uninstall_from_agent(name="my-skill", agent="claude")
        item = service.get_item(name="my-skill")
        assert "claude" not in item.installed_in


class TestImport:
    def test_import_from_agent(self, service, agents):
        agents["claude"].write("imported-skill", SAMPLE_MD)
        item = service.import_from_agent(agent="claude", name="imported-skill")
        assert item.name == "imported-skill"

    def test_import_all_from_agent(self, service, agents):
        agents["claude"].write("skill-a", SAMPLE_MD)
        agents["claude"].write("skill-b", SAMPLE_MD)
        imported = service.import_all_from_agent(agent="claude")
        assert len(imported) == 2

    def test_import_all_agents(self, service, agents):
        agents["claude"].write("claude-skill", SAMPLE_MD)
        agents["codex"].write("codex-skill", SAMPLE_MD)
        service.import_all_agents()
        assert service._central.exists("claude-skill")
        assert service._central.exists("codex-skill")


class TestGetItem:
    def test_returns_item(self, service):
        service.install(name="my-skill", content=SAMPLE_MD)
        item = service.get_item(name="my-skill")
        assert item.name == "my-skill"

    def test_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.get_item(name="nonexistent")

    def test_get_item_content(self, service):
        service.install(name="my-skill", content=SAMPLE_MD)
        content = service.get_item_content(name="my-skill")
        assert "A sample skill" in content

    def test_get_item_path(self, service):
        service.install(name="my-skill", content=SAMPLE_MD)
        path = service.get_item_path(name="my-skill")
        assert "my-skill" in path


class TestInvalidate:
    def test_invalidate_clears_cache(self, service):
        service.install(name="my-skill", content=SAMPLE_MD)
        service.list_items()
        assert service._cache is not None
        service.invalidate()
        assert service._cache is None
