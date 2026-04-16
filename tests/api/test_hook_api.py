"""Integration tests for the hook management API."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vibelens.api.hook import router
from vibelens.models.enums import AgentType
from vibelens.services.extensions.hook_service import HookService
from vibelens.storage.extension.hook_store import HookStore

SAMPLE_CONFIG = {
    "PreToolUse": [
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": "/bin/echo sample"}],
        }
    ]
}


@pytest.fixture
def hook_service(tmp_path):
    central = HookStore(root=tmp_path / "central", create=True)
    agent_settings = {
        AgentType.CLAUDE: tmp_path / "claude" / "settings.json",
    }
    return HookService(central=central, agent_settings=agent_settings)


@pytest.fixture
def client(hook_service, monkeypatch):
    import vibelens.api.hook as hook_api

    monkeypatch.setattr(hook_api, "get_hook_service", lambda: hook_service)

    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


class TestListHooks:
    def test_returns_empty_list(self, client):
        res = client.get("/api/hooks")
        assert res.status_code == 200
        data = res.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert "sync_targets" in data

    def test_returns_installed_hooks(self, client, hook_service):
        hook_service.install(name="my-hook", description="d", tags=[], hook_config=SAMPLE_CONFIG)
        res = client.get("/api/hooks")
        data = res.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "my-hook"

    def test_search_filters(self, client, hook_service):
        hook_service.install(name="alpha", description="", tags=[], hook_config=SAMPLE_CONFIG)
        hook_service.install(name="beta", description="", tags=[], hook_config=SAMPLE_CONFIG)
        res = client.get("/api/hooks?search=alpha")
        assert res.json()["total"] == 1


class TestGetHook:
    def test_returns_hook_with_content(self, client, hook_service):
        hook_service.install(name="my-hook", description="desc", tags=[], hook_config=SAMPLE_CONFIG)
        res = client.get("/api/hooks/my-hook")
        assert res.status_code == 200
        data = res.json()
        assert data["hook"]["name"] == "my-hook"
        assert "desc" in data["content"]
        assert "path" in data

    def test_not_found(self, client):
        res = client.get("/api/hooks/nonexistent")
        assert res.status_code == 404


class TestInstallHook:
    def test_installs_new_hook(self, client):
        res = client.post(
            "/api/hooks",
            json={"name": "new-hook", "description": "d", "tags": [], "hook_config": SAMPLE_CONFIG},
        )
        assert res.status_code == 200
        assert res.json()["name"] == "new-hook"

    def test_rejects_duplicate(self, client, hook_service):
        hook_service.install(name="existing", description="", tags=[], hook_config=SAMPLE_CONFIG)
        res = client.post(
            "/api/hooks",
            json={"name": "existing", "description": "", "tags": [], "hook_config": SAMPLE_CONFIG},
        )
        assert res.status_code == 409

    def test_rejects_invalid_name(self, client):
        res = client.post(
            "/api/hooks",
            json={
                "name": "Not Valid",
                "description": "",
                "tags": [],
                "hook_config": SAMPLE_CONFIG,
            },
        )
        assert res.status_code == 422


class TestModifyHook:
    def test_updates_description(self, client, hook_service):
        hook_service.install(name="my-hook", description="old", tags=[], hook_config=SAMPLE_CONFIG)
        res = client.put("/api/hooks/my-hook", json={"description": "new"})
        assert res.status_code == 200
        assert res.json()["description"] == "new"

    def test_not_found(self, client):
        res = client.put("/api/hooks/nonexistent", json={"description": "x"})
        assert res.status_code == 404


class TestUninstallHook:
    def test_deletes_hook(self, client, hook_service):
        hook_service.install(name="my-hook", description="", tags=[], hook_config=SAMPLE_CONFIG)
        res = client.delete("/api/hooks/my-hook")
        assert res.status_code == 200
        assert res.json()["deleted"] == "my-hook"

    def test_not_found(self, client):
        res = client.delete("/api/hooks/nonexistent")
        assert res.status_code == 404


class TestSyncHook:
    def test_syncs_to_agent(self, client, hook_service):
        hook_service.install(name="my-hook", description="", tags=[], hook_config=SAMPLE_CONFIG)
        res = client.post("/api/hooks/my-hook/agents", json={"agents": ["claude"]})
        assert res.status_code == 200
        data = res.json()
        assert data["results"]["claude"] is True

    def test_not_found(self, client):
        res = client.post("/api/hooks/nonexistent/agents", json={"agents": ["claude"]})
        assert res.status_code == 404


class TestUnsyncHook:
    def test_unsyncs_from_agent(self, client, hook_service):
        hook_service.install(
            name="my-hook", description="", tags=[], hook_config=SAMPLE_CONFIG, sync_to=["claude"]
        )
        res = client.delete("/api/hooks/my-hook/agents/claude")
        assert res.status_code == 200

    def test_agent_unknown(self, client, hook_service):
        hook_service.install(name="my-hook", description="", tags=[], hook_config=SAMPLE_CONFIG)
        res = client.delete("/api/hooks/my-hook/agents/unknown")
        assert res.status_code == 404


class TestImportFromAgent:
    def test_imports_from_agent(self, client, hook_service, tmp_path):
        claude_settings = tmp_path / "claude" / "settings.json"
        claude_settings.parent.mkdir(parents=True, exist_ok=True)
        claude_settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "Bash",
                                "hooks": [{"type": "command", "command": "/bin/echo"}],
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        res = client.post(
            "/api/hooks/import/claude",
            params={"name": "imported", "event_name": "PreToolUse", "matcher": "Bash"},
        )
        assert res.status_code == 200
        assert res.json()["name"] == "imported"

    def test_unknown_agent(self, client):
        res = client.post(
            "/api/hooks/import/unknown",
            params={"name": "imported", "event_name": "PreToolUse", "matcher": "Bash"},
        )
        assert res.status_code == 404
