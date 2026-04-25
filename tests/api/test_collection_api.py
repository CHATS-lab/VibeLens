"""HTTP-level tests for the collections router."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vibelens.api.extensions.collections import build_collections_router
from vibelens.models.enums import AgentExtensionType
from vibelens.services.extensions.collection_service import CollectionService
from vibelens.services.extensions.skill_service import SkillService
from vibelens.storage.extension.collection_store import CollectionStore
from vibelens.storage.extension.skill_store import SkillStore

SKILL = "---\ndescription: t\n---\n# T\n"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    skill_central = SkillStore(root=tmp_path / "skills" / "central", create=True)
    skill_agents = {"claude": SkillStore(root=tmp_path / "skills" / "claude", create=True)}
    skill_service = SkillService(central=skill_central, agents=skill_agents)
    skill_service.install(name="alpha", content=SKILL)

    coll_service = CollectionService(
        store=CollectionStore(root=tmp_path / "collections", create=True),
        services_by_type={AgentExtensionType.SKILL: skill_service},
    )

    router = build_collections_router(lambda: coll_service)
    app = FastAPI()
    app.include_router(router, prefix="/api/extensions")
    test_client = TestClient(app)
    test_client.tmp_path = tmp_path  # type: ignore[attr-defined]
    return test_client


def test_create_collection(client) -> None:
    res = client.post(
        "/api/extensions/collections",
        json={
            "name": "bundle",
            "description": "d",
            "items": [{"extension_type": "skill", "name": "alpha"}],
            "tags": ["t"],
        },
    )
    assert res.status_code == 200
    assert res.json()["name"] == "bundle"


def test_create_duplicate_returns_409(client) -> None:
    body = {"name": "a", "description": "", "items": [], "tags": []}
    client.post("/api/extensions/collections", json=body)
    res = client.post("/api/extensions/collections", json=body)
    assert res.status_code == 409


def test_list_collections(client) -> None:
    client.post(
        "/api/extensions/collections",
        json={"name": "a", "description": "", "items": [], "tags": []},
    )
    client.post(
        "/api/extensions/collections",
        json={"name": "b", "description": "", "items": [], "tags": []},
    )

    res = client.get("/api/extensions/collections")
    names = {c["name"] for c in res.json()["items"]}
    assert names == {"a", "b"}


def test_get_collection(client) -> None:
    client.post(
        "/api/extensions/collections",
        json={"name": "a", "description": "d", "items": [], "tags": []},
    )
    res = client.get("/api/extensions/collections/a")
    assert res.json()["name"] == "a"


def test_get_returns_404_for_missing(client) -> None:
    res = client.get("/api/extensions/collections/missing")
    assert res.status_code == 404


def test_delete_collection(client) -> None:
    client.post(
        "/api/extensions/collections",
        json={"name": "a", "description": "", "items": [], "tags": []},
    )
    res = client.delete("/api/extensions/collections/a")
    assert res.status_code == 200
    assert client.get("/api/extensions/collections/a").status_code == 404


def test_install_collection(client) -> None:
    client.post(
        "/api/extensions/collections",
        json={
            "name": "bundle",
            "description": "",
            "items": [{"extension_type": "skill", "name": "alpha"}],
            "tags": [],
        },
    )

    res = client.post(
        "/api/extensions/collections/bundle/install",
        json={"agents": ["claude"], "link_type": "copy"},
    )
    assert res.status_code == 200
    assert res.json()["results"]["alpha"]["claude"] == "ok"


def test_export_collection(client) -> None:
    client.post(
        "/api/extensions/collections",
        json={
            "name": "bundle",
            "description": "d",
            "items": [{"extension_type": "skill", "name": "alpha"}],
            "tags": [],
        },
    )
    res = client.get("/api/extensions/collections/bundle/export")
    assert res.status_code == 200
    payload = res.json()
    assert payload["version"] == 1
    assert payload["name"] == "bundle"


def test_import_collection(client) -> None:
    payload = {
        "version": 1,
        "name": "imported",
        "description": "i",
        "items": [{"extension_type": "skill", "name": "alpha"}],
        "tags": [],
    }
    res = client.post(
        "/api/extensions/collections/import",
        json={"payload": payload},
    )
    assert res.status_code == 200
    assert res.json()["name"] == "imported"


def test_import_invalid_version_returns_400(client) -> None:
    payload = {"version": 99, "name": "x", "items": [], "tags": []}
    res = client.post(
        "/api/extensions/collections/import",
        json={"payload": payload},
    )
    assert res.status_code == 400
