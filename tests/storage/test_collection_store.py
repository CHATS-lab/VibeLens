"""Tests for CollectionStore JSON CRUD."""

from datetime import datetime, timezone
from pathlib import Path

from vibelens.models.collection import ExtensionCollection, ExtensionCollectionItem
from vibelens.models.enums import AgentExtensionType
from vibelens.storage.extension.collection_store import CollectionStore


def _make_collection(name: str = "data-stack") -> ExtensionCollection:
    now = datetime.now(timezone.utc)
    return ExtensionCollection(
        name=name,
        description="t",
        items=[ExtensionCollectionItem(extension_type=AgentExtensionType.SKILL, name="alpha")],
        tags=["a"],
        created_at=now,
        updated_at=now,
    )


def test_write_and_read_roundtrip(tmp_path: Path) -> None:
    store = CollectionStore(root=tmp_path, create=True)
    collection = _make_collection()
    store.write(collection)

    loaded = store.read("data-stack")
    assert loaded is not None
    assert loaded.name == "data-stack"
    assert loaded.items[0].name == "alpha"


def test_list_returns_all_collections(tmp_path: Path) -> None:
    store = CollectionStore(root=tmp_path, create=True)
    store.write(_make_collection("a"))
    store.write(_make_collection("b"))

    assert sorted(store.list_names()) == ["a", "b"]


def test_delete_removes_file(tmp_path: Path) -> None:
    store = CollectionStore(root=tmp_path, create=True)
    store.write(_make_collection("a"))
    assert store.delete("a") is True

    assert store.read("a") is None
    assert store.list_names() == []


def test_read_missing_returns_none(tmp_path: Path) -> None:
    store = CollectionStore(root=tmp_path, create=True)
    assert store.read("nonexistent") is None
    assert store.delete("nonexistent") is False


def test_read_returns_none_for_corrupt_json(tmp_path: Path) -> None:
    store = CollectionStore(root=tmp_path, create=True)
    (tmp_path / "broken.json").write_text("{ not valid json")

    assert store.read("broken") is None
