"""Integration tests for the skill management API."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vibelens.api.skill import router
from vibelens.models.enums import AgentType
from vibelens.services.extensions.skill_service import SkillService
from vibelens.storage.extension.skill_store import SkillStore

SAMPLE_SKILL_MD = """\
---
description: Test skill
tags:
  - test
---
# Test Skill
"""


@pytest.fixture
def skill_service(tmp_path):
    central = SkillStore(root=tmp_path / "central", create=True)
    agents = {
        AgentType.CLAUDE: SkillStore(root=tmp_path / "claude", create=True),
    }
    return SkillService(central=central, agents=agents)


@pytest.fixture
def client(skill_service, monkeypatch):
    import vibelens.api.skill as skill_api
    monkeypatch.setattr(skill_api, "get_skill_service", lambda: skill_service)

    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


class TestListSkills:
    def test_returns_empty_list(self, client):
        res = client.get("/api/skills")
        assert res.status_code == 200
        data = res.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert "sync_targets" in data

    def test_returns_installed_skills(self, client, skill_service):
        skill_service.install(name="my-skill", content=SAMPLE_SKILL_MD)
        res = client.get("/api/skills")
        data = res.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "my-skill"

    def test_search_filters(self, client, skill_service):
        skill_service.install(name="alpha", content=SAMPLE_SKILL_MD)
        skill_service.install(name="beta", content=SAMPLE_SKILL_MD)
        res = client.get("/api/skills?search=alpha")
        data = res.json()
        assert data["total"] == 1

    def test_pagination(self, client, skill_service):
        for i in range(3):
            skill_service.install(name=f"skill-{i:02d}", content=SAMPLE_SKILL_MD)
        res = client.get("/api/skills?page=2&page_size=2")
        data = res.json()
        assert data["total"] == 3
        assert len(data["items"]) == 1


class TestGetSkill:
    def test_returns_skill_with_content(self, client, skill_service):
        skill_service.install(name="my-skill", content=SAMPLE_SKILL_MD)
        res = client.get("/api/skills/my-skill")
        assert res.status_code == 200
        data = res.json()
        assert data["skill"]["name"] == "my-skill"
        assert "Test skill" in data["content"]
        assert "path" in data

    def test_not_found(self, client):
        res = client.get("/api/skills/nonexistent")
        assert res.status_code == 404


class TestInstallSkill:
    def test_installs_new_skill(self, client):
        res = client.post(
            "/api/skills",
            json={"name": "new-skill", "content": SAMPLE_SKILL_MD},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "new-skill"

    def test_rejects_duplicate(self, client, skill_service):
        skill_service.install(name="existing", content=SAMPLE_SKILL_MD)
        res = client.post(
            "/api/skills",
            json={"name": "existing", "content": SAMPLE_SKILL_MD},
        )
        assert res.status_code == 409

    def test_rejects_invalid_name(self, client):
        res = client.post(
            "/api/skills",
            json={"name": "Not Valid", "content": SAMPLE_SKILL_MD},
        )
        assert res.status_code == 422


class TestModifySkill:
    def test_updates_skill(self, client, skill_service):
        skill_service.install(name="my-skill", content=SAMPLE_SKILL_MD)
        res = client.put(
            "/api/skills/my-skill",
            json={"content": "---\ndescription: Updated\n---\nNew body."},
        )
        assert res.status_code == 200
        assert res.json()["description"] == "Updated"

    def test_not_found(self, client):
        res = client.put(
            "/api/skills/nonexistent",
            json={"content": "some content"},
        )
        assert res.status_code == 404


class TestUninstallSkill:
    def test_deletes_skill(self, client, skill_service):
        skill_service.install(name="my-skill", content=SAMPLE_SKILL_MD)
        res = client.delete("/api/skills/my-skill")
        assert res.status_code == 200
        data = res.json()
        assert data["deleted"] == "my-skill"

    def test_not_found(self, client):
        res = client.delete("/api/skills/nonexistent")
        assert res.status_code == 404


class TestSyncSkill:
    def test_syncs_to_agent(self, client, skill_service):
        skill_service.install(name="my-skill", content=SAMPLE_SKILL_MD)
        res = client.post(
            "/api/skills/my-skill/agents",
            json={"agents": ["claude"]},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["results"]["claude"] is True

    def test_not_found(self, client):
        res = client.post(
            "/api/skills/nonexistent/agents",
            json={"agents": ["claude"]},
        )
        assert res.status_code == 404


class TestUnsyncSkill:
    def test_unsyncs_from_agent(self, client, skill_service):
        skill_service.install(
            name="my-skill", content=SAMPLE_SKILL_MD, sync_to=["claude"]
        )
        res = client.delete("/api/skills/my-skill/agents/claude")
        assert res.status_code == 200

    def test_agent_not_found(self, client, skill_service):
        skill_service.install(name="my-skill", content=SAMPLE_SKILL_MD)
        res = client.delete("/api/skills/my-skill/agents/unknown")
        assert res.status_code == 404


class TestImportFromAgent:
    def test_imports_all(self, client, skill_service):
        skill_service._agents["claude"].write("agent-skill", SAMPLE_SKILL_MD)
        res = client.post("/api/skills/import/claude")
        assert res.status_code == 200
        data = res.json()
        assert "agent-skill" in data["imported"]

    def test_unknown_agent(self, client):
        res = client.post("/api/skills/import/unknown")
        assert res.status_code == 404
