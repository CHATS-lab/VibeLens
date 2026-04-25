"""Tests for link_type=symlink in the HTTP install request."""

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vibelens.api.extensions.factory import build_typed_router
from vibelens.models.enums import AgentExtensionType
from vibelens.services.extensions.skill_service import SkillService
from vibelens.storage.extension.skill_store import SkillStore

SAMPLE_SKILL = "---\ndescription: t\n---\n# T\n"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    central = SkillStore(root=tmp_path / "central", create=True)
    agents = {"claude": SkillStore(root=tmp_path / "claude", create=True)}
    service = SkillService(central=central, agents=agents)

    router = build_typed_router(lambda: service, AgentExtensionType.SKILL)
    app = FastAPI()
    app.include_router(router, prefix="/api/extensions")
    test_client = TestClient(app)
    test_client.tmp_path = tmp_path  # type: ignore[attr-defined]
    return test_client


def test_install_with_link_type_symlink(client) -> None:
    """POST /skills with link_type=symlink creates a symlink in the agent store."""
    if sys.platform == "win32":
        pytest.skip("symlinks require dev mode on Windows")

    res = client.post(
        "/api/extensions/skills",
        json={
            "name": "alpha",
            "content": SAMPLE_SKILL,
            "sync_to": ["claude"],
            "link_type": "symlink",
        },
    )
    assert res.status_code == 200, res.json()
    agent_path = client.tmp_path / "claude" / "alpha"  # type: ignore[attr-defined]
    assert agent_path.is_symlink()


def test_install_default_is_symlink(client) -> None:
    """When link_type is omitted, default is symlink."""
    if sys.platform == "win32":
        pytest.skip("symlinks require dev mode on Windows")

    res = client.post(
        "/api/extensions/skills",
        json={"name": "alpha", "content": SAMPLE_SKILL, "sync_to": ["claude"]},
    )
    assert res.status_code == 200
    assert (client.tmp_path / "claude" / "alpha").is_symlink()  # type: ignore[attr-defined]
