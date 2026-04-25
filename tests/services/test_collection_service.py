"""Tests for CollectionService CRUD + batch install + export/import."""

import json
from pathlib import Path

import pytest

from vibelens.models.enums import AgentExtensionType
from vibelens.services.extensions.collection_service import CollectionService
from vibelens.services.extensions.skill_service import SkillService
from vibelens.storage.extension.collection_store import CollectionStore
from vibelens.storage.extension.skill_store import SkillStore

SKILL_BODY = "---\ndescription: t\n---\n# T\n"


@pytest.fixture
def collection_service(tmp_path: Path) -> CollectionService:
    store = CollectionStore(root=tmp_path, create=True)
    return CollectionService(store=store, services_by_type={})


@pytest.fixture
def collection_service_with_skills(tmp_path: Path) -> CollectionService:
    skill_central = SkillStore(root=tmp_path / "skills" / "central", create=True)
    skill_agents = {
        "claude": SkillStore(root=tmp_path / "skills" / "claude", create=True),
        "cursor": SkillStore(root=tmp_path / "skills" / "cursor", create=True),
    }
    skill_service = SkillService(central=skill_central, agents=skill_agents)
    skill_service.install(name="alpha", content=SKILL_BODY)
    skill_service.install(name="beta", content=SKILL_BODY)

    coll_store = CollectionStore(root=tmp_path / "collections", create=True)
    return CollectionService(
        store=coll_store,
        services_by_type={AgentExtensionType.SKILL: skill_service},
    )


def test_create_writes_collection(collection_service) -> None:
    coll = collection_service.create(
        name="data-stack",
        description="Python stack",
        items=[(AgentExtensionType.SKILL, "alpha")],
        tags=["data"],
    )
    assert coll.name == "data-stack"
    assert coll.items[0].name == "alpha"

    listed = collection_service.list_all()
    assert [c.name for c in listed] == ["data-stack"]


def test_create_rejects_duplicate_name(collection_service) -> None:
    collection_service.create(name="a", description="", items=[], tags=[])
    with pytest.raises(ValueError):
        collection_service.create(name="a", description="", items=[], tags=[])


def test_get_returns_existing(collection_service) -> None:
    collection_service.create(name="a", description="", items=[], tags=[])
    fetched = collection_service.get("a")
    assert fetched.name == "a"


def test_get_raises_keyerror_when_missing(collection_service) -> None:
    with pytest.raises(KeyError):
        collection_service.get("missing")


def test_update_replaces_items(collection_service) -> None:
    collection_service.create(
        name="a",
        description="",
        items=[(AgentExtensionType.SKILL, "x")],
        tags=[],
    )

    collection_service.update(
        name="a",
        description="updated",
        items=[(AgentExtensionType.SKILL, "y")],
        tags=["new"],
    )

    coll = collection_service.get("a")
    assert coll.description == "updated"
    assert [it.name for it in coll.items] == ["y"]
    assert coll.tags == ["new"]


def test_delete_removes_collection(collection_service) -> None:
    collection_service.create(name="a", description="", items=[], tags=[])
    assert collection_service.delete("a") is True
    assert collection_service.delete("a") is False


def test_install_to_agents_fans_out(collection_service_with_skills, tmp_path: Path) -> None:
    """install_to_agents syncs every item to every requested agent."""
    collection_service_with_skills.create(
        name="bundle",
        description="",
        items=[
            (AgentExtensionType.SKILL, "alpha"),
            (AgentExtensionType.SKILL, "beta"),
        ],
        tags=[],
    )

    results = collection_service_with_skills.install_to_agents(
        collection_name="bundle",
        agents=["claude", "cursor"],
        link_type="copy",
    )

    assert results["alpha"]["claude"] == "ok"
    assert results["alpha"]["cursor"] == "ok"
    assert results["beta"]["claude"] == "ok"
    assert (tmp_path / "skills" / "claude" / "alpha").exists()
    assert (tmp_path / "skills" / "cursor" / "beta").exists()


def test_install_to_agents_reports_per_item_errors(collection_service_with_skills) -> None:
    """Unsupported types report errors without aborting the rest."""
    collection_service_with_skills.create(
        name="mixed",
        description="",
        items=[
            (AgentExtensionType.SKILL, "alpha"),
            (AgentExtensionType.HOOK, "missing-hook"),
        ],
        tags=[],
    )

    results = collection_service_with_skills.install_to_agents(
        collection_name="mixed",
        agents=["claude"],
        link_type="copy",
    )

    assert results["alpha"]["claude"] == "ok"
    assert "error" in results["missing-hook"]


def test_install_to_agents_reports_missing_extension(
    collection_service_with_skills,
) -> None:
    """Items that reference a non-existent extension report 'missing' per agent."""
    collection_service_with_skills.create(
        name="orphan",
        description="",
        items=[(AgentExtensionType.SKILL, "does-not-exist")],
        tags=[],
    )

    results = collection_service_with_skills.install_to_agents(
        collection_name="orphan",
        agents=["claude", "cursor"],
        link_type="copy",
    )

    assert results["does-not-exist"] == {"claude": "missing", "cursor": "missing"}


def test_export_and_import_roundtrip(collection_service_with_skills) -> None:
    """export_json -> import_json round-trips."""
    collection_service_with_skills.create(
        name="export-me",
        description="d",
        items=[(AgentExtensionType.SKILL, "alpha")],
        tags=["t1"],
    )

    payload = collection_service_with_skills.export_json("export-me")
    parsed = json.loads(payload)
    assert parsed["version"] == 1
    assert parsed["name"] == "export-me"

    collection_service_with_skills.delete("export-me")
    imported = collection_service_with_skills.import_json(payload)

    assert imported.name == "export-me"
    assert imported.items[0].name == "alpha"


def test_import_rejects_invalid_version(collection_service) -> None:
    bad = json.dumps({"version": 99, "name": "x", "items": [], "tags": []})
    with pytest.raises(ValueError, match="unsupported export version"):
        collection_service.import_json(bad)
