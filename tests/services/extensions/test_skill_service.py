"""Tests for SkillService — orchestrator for skill management."""

import pytest

from vibelens.services.extensions.skill_service import SkillService, SyncTarget
from vibelens.storage.extension.skill_store import SkillStore

SAMPLE_SKILL_MD = """\
---
description: A sample skill
tags:
  - testing
---
# Sample Skill

Body content.
"""

UPDATED_SKILL_MD = """\
---
description: Updated skill
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
    return SkillService(central=central, agents=agents)


class TestInstall:
    def test_install_creates_skill(self, service):
        skill = service.install(name="my-skill", content=SAMPLE_SKILL_MD)
        assert skill.name == "my-skill"
        assert skill.description == "A sample skill"
        assert skill.installed_in == []

    def test_install_with_sync(self, service):
        skill = service.install(
            name="my-skill", content=SAMPLE_SKILL_MD, sync_to=["claude"]
        )
        assert "claude" in skill.installed_in

    def test_install_duplicate_raises(self, service):
        service.install(name="my-skill", content=SAMPLE_SKILL_MD)
        with pytest.raises(FileExistsError):
            service.install(name="my-skill", content=SAMPLE_SKILL_MD)

    def test_install_invalid_name_raises(self, service):
        with pytest.raises(ValueError, match="kebab-case"):
            service.install(name="Not Valid", content=SAMPLE_SKILL_MD)

    def test_install_empty_content_raises(self, service):
        with pytest.raises(ValueError, match="empty"):
            service.install(name="my-skill", content="   ")


class TestUninstall:
    def test_uninstall_removes_from_central(self, service):
        service.install(name="my-skill", content=SAMPLE_SKILL_MD)
        removed = service.uninstall("my-skill")
        assert isinstance(removed, list)
        assert not service._central.exists("my-skill")

    def test_uninstall_cascades_to_agents(self, service):
        service.install(
            name="my-skill", content=SAMPLE_SKILL_MD, sync_to=["claude", "codex"]
        )
        removed = service.uninstall("my-skill")
        assert "claude" in removed
        assert "codex" in removed
        assert not service._agents["claude"].exists("my-skill")

    def test_uninstall_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.uninstall("nonexistent")

    def test_uninstall_from_agent(self, service):
        service.install(
            name="my-skill", content=SAMPLE_SKILL_MD, sync_to=["claude"]
        )
        service.uninstall_from_agent("my-skill", "claude")
        assert not service._agents["claude"].exists("my-skill")
        assert service._central.exists("my-skill")

    def test_uninstall_from_unknown_agent_raises(self, service):
        service.install(name="my-skill", content=SAMPLE_SKILL_MD)
        with pytest.raises(KeyError):
            service.uninstall_from_agent("my-skill", "unknown")


class TestQuery:
    def test_list_skills(self, service):
        service.install(name="alpha", content=SAMPLE_SKILL_MD)
        service.install(name="beta", content=SAMPLE_SKILL_MD)
        skills, total = service.list_skills()
        assert total == 2
        assert len(skills) == 2

    def test_list_skills_pagination(self, service):
        for i in range(5):
            service.install(name=f"skill-{i:02d}", content=SAMPLE_SKILL_MD)
        skills, total = service.list_skills(page=2, page_size=2)
        assert total == 5
        assert len(skills) == 2

    def test_list_skills_search(self, service):
        service.install(name="alpha", content=SAMPLE_SKILL_MD)
        service.install(name="beta", content=SAMPLE_SKILL_MD)
        skills, total = service.list_skills(search="alpha")
        assert total == 1
        assert skills[0].name == "alpha"

    def test_list_skills_populates_installed_in(self, service):
        service.install(
            name="my-skill", content=SAMPLE_SKILL_MD, sync_to=["claude"]
        )
        skills, _ = service.list_skills()
        assert "claude" in skills[0].installed_in

    def test_get_skill(self, service):
        service.install(name="my-skill", content=SAMPLE_SKILL_MD)
        skill = service.get_skill("my-skill")
        assert skill.name == "my-skill"

    def test_get_skill_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.get_skill("nonexistent")

    def test_get_skill_content(self, service):
        service.install(name="my-skill", content=SAMPLE_SKILL_MD)
        content = service.get_skill_content("my-skill")
        assert "A sample skill" in content

    def test_get_skill_content_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.get_skill_content("nonexistent")

    def test_find_installed_agents(self, service):
        service.install(
            name="my-skill", content=SAMPLE_SKILL_MD, sync_to=["claude", "codex"]
        )
        agents = service.find_installed_agents("my-skill")
        assert sorted(agents) == ["claude", "codex"]

    def test_list_sync_targets(self, service):
        targets = service.list_sync_targets()
        assert len(targets) == 2
        assert all(isinstance(t, SyncTarget) for t in targets)
        keys = [t.key for t in targets]
        assert "claude" in keys


class TestModify:
    def test_modify_updates_content(self, service):
        service.install(name="my-skill", content=SAMPLE_SKILL_MD)
        skill = service.modify("my-skill", UPDATED_SKILL_MD)
        assert skill.description == "Updated skill"

    def test_modify_auto_syncs(self, service):
        service.install(
            name="my-skill", content=SAMPLE_SKILL_MD, sync_to=["claude"]
        )
        service.modify("my-skill", UPDATED_SKILL_MD)
        agent_skill = service._agents["claude"].read("my-skill")
        assert agent_skill is not None
        assert agent_skill.description == "Updated skill"

    def test_modify_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.modify("nonexistent", UPDATED_SKILL_MD)


class TestSync:
    def test_sync_to_agents(self, service):
        service.install(name="my-skill", content=SAMPLE_SKILL_MD)
        results = service.sync_to_agents("my-skill", ["claude", "codex"])
        assert results == {"claude": True, "codex": True}

    def test_sync_unknown_agent(self, service):
        service.install(name="my-skill", content=SAMPLE_SKILL_MD)
        results = service.sync_to_agents("my-skill", ["unknown"])
        assert results["unknown"] is False

    def test_sync_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.sync_to_agents("nonexistent", ["claude"])


class TestImport:
    def test_import_from_agent(self, service):
        service._agents["claude"].write("agent-skill", SAMPLE_SKILL_MD)
        skill = service.import_from_agent("claude", "agent-skill")
        assert skill.name == "agent-skill"
        assert service._central.exists("agent-skill")

    def test_import_from_unknown_agent_raises(self, service):
        with pytest.raises(KeyError):
            service.import_from_agent("unknown", "some-skill")

    def test_import_missing_skill_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.import_from_agent("claude", "nonexistent")

    def test_import_all_from_agent(self, service):
        service._agents["claude"].write("skill-a", SAMPLE_SKILL_MD)
        service._agents["claude"].write("skill-b", SAMPLE_SKILL_MD)
        imported = service.import_all_from_agent("claude")
        assert sorted(imported) == ["skill-a", "skill-b"]

    def test_import_all_skips_existing(self, service):
        service.install(name="existing", content=SAMPLE_SKILL_MD)
        service._agents["claude"].write("existing", UPDATED_SKILL_MD)
        service._agents["claude"].write("new-one", SAMPLE_SKILL_MD)
        imported = service.import_all_from_agent("claude")
        assert imported == ["new-one"]


class TestCache:
    def test_invalidate_clears_cache(self, service):
        service.install(name="my-skill", content=SAMPLE_SKILL_MD)
        service.list_skills()
        service.invalidate()
        assert service._cache is None
