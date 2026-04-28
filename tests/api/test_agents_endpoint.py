"""Tests for GET /extensions/agents."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibelens.app import create_app
from vibelens.services.extensions.platforms import rebuild_platforms


@pytest.fixture
def client_with_fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / ".claude").mkdir()
    # Rebuild the platform table against the patched home so ``PLATFORMS``
    # reflects ``tmp_path`` instead of the real user dir.
    rebuild_platforms()
    try:
        yield TestClient(create_app())
    finally:
        rebuild_platforms()


def test_agents_endpoint_returns_list(client_with_fake_home: TestClient):
    resp = client_with_fake_home.get("/api/extensions/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert "agents" in body

    claude = next((a for a in body["agents"] if a["key"] == "claude"), None)
    assert claude is not None
    assert claude["installed"] is True
    assert "skill" in claude["supported_types"]
    assert "plugin" in claude["supported_types"]

    cursor = next((a for a in body["agents"] if a["key"] == "cursor"), None)
    assert cursor is not None
    assert cursor["installed"] is False


def test_agents_endpoint_includes_all_known_platforms(client_with_fake_home: TestClient):
    resp = client_with_fake_home.get("/api/extensions/agents")
    body = resp.json()
    keys = {a["key"] for a in body["agents"]}
    assert {"claude", "codex", "cursor", "opencode", "gemini", "copilot"}.issubset(keys)


def test_agents_endpoint_carries_dirs_by_type(client_with_fake_home: TestClient):
    """``dirs_by_type`` is the SoT for the frontend's syncTargets cache: every
    type in supported_types whose specific platform field is non-None must
    have a corresponding absolute path here."""
    resp = client_with_fake_home.get("/api/extensions/agents")
    body = resp.json()
    claude = next(a for a in body["agents"] if a["key"] == "claude")
    assert "dirs_by_type" in claude
    assert claude["dirs_by_type"]["skill"].endswith("/.claude/skills")
    assert claude["dirs_by_type"]["command"].endswith("/.claude/commands")
    assert claude["dirs_by_type"]["subagent"].endswith("/.claude/agents")
    # Claude declares plugin support but plugins_dir is None on the
    # AgentPlatform itself (the plugin store is special-cased) — so this
    # type doesn't surface in dirs_by_type.
    assert "plugin" not in claude["dirs_by_type"]


def test_agents_endpoint_counts_default_to_zero(client_with_fake_home: TestClient):
    """A fresh fake-home has nothing installed; counts must be 0 for every
    declared type."""
    resp = client_with_fake_home.get("/api/extensions/agents")
    body = resp.json()
    claude = next(a for a in body["agents"] if a["key"] == "claude")
    for type_key in claude["dirs_by_type"]:
        assert claude["counts_by_type"].get(type_key, 0) == 0
