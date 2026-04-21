"""Tests for GET /api/version."""

from fastapi.testclient import TestClient

from vibelens.app import create_app
from vibelens.services import version as version_mod


def test_version_endpoint_shape(monkeypatch):
    monkeypatch.setattr(version_mod, "fetch_latest_version", lambda: "1.0.5")
    monkeypatch.setattr(version_mod, "detect_install_method", lambda: "uv")
    client = TestClient(create_app())
    resp = client.get("/api/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["current"]
    assert body["latest"] == "1.0.5"
    assert body["update_available"] in (True, False)
    assert body["is_dev_build"] in (True, False)
    assert body["install_method"] == "uv"
    assert set(body["install_commands"]) == {"uv", "pip", "npx"}


def test_version_endpoint_offline(monkeypatch):
    monkeypatch.setattr(version_mod, "fetch_latest_version", lambda: None)
    monkeypatch.setattr(version_mod, "detect_install_method", lambda: "unknown")
    client = TestClient(create_app())
    resp = client.get("/api/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["latest"] is None
    assert body["update_available"] is False
