"""Tests for upload API routes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vibelens.api.upload import router as upload_router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(upload_router)
    return TestClient(app)


def test_get_upload_agents_returns_user_facing_specs(client):
    res = client.get("/upload/agents")
    assert res.status_code == 200
    payload = res.json()
    assert "agents" in payload
    types = {a["agent_type"] for a in payload["agents"]}
    # User-facing agents must be present.
    assert "claude" in types
    assert "claude_web" in types
    assert "kilo" in types
    assert "cursor" in types
    # Internal-only specs are filtered out.
    assert "parsed" not in types
    assert "aider" not in types
    for agent in payload["agents"]:
        assert agent["user_facing"] is True


def test_get_upload_agents_includes_per_os_commands(client):
    payload = client.get("/upload/agents").json()
    claude = next(a for a in payload["agents"] if a["agent_type"] == "claude")
    assert "macos" in claude["commands"]
    assert "linux" in claude["commands"]
    assert "windows" in claude["commands"]


def test_get_upload_agents_omits_unsupported_os_keys(client):
    payload = client.get("/upload/agents").json()
    kilo = next(a for a in payload["agents"] if a["agent_type"] == "kilo")
    # Kilo doesn't ship for Windows; key omitted.
    assert "windows" not in kilo["commands"]
    assert "macos" in kilo["commands"]
