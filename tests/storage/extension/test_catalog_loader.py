"""Tests for the new catalog loader."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from vibelens.storage.extension.catalog import (
    CatalogSnapshot,
    _clear_user_catalog,
    load_catalog_from_dir,
    reset_catalog_cache,
)

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "hub_sample"
SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "build_catalog.py"


@pytest.fixture
def built_catalog(tmp_path: Path) -> Path:
    """Run the real build script against the fixture, return the out dir."""
    out = tmp_path / "catalog"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--hub-output", str(FIXTURE), "--out", str(out)],
        check=True,
    )
    return out


def test_load_catalog_from_dir_returns_snapshot(built_catalog: Path):
    snap = load_catalog_from_dir(built_catalog)
    assert snap is not None
    assert isinstance(snap, CatalogSnapshot)
    # Fixture contains 7 items; mcp_server is excluded from the loaded catalog.
    assert snap.manifest.total == len(snap.items) == 6
    assert "mcp_server" not in snap.manifest.item_counts
    assert all(it.extension_type.value != "mcp_server" for it in snap.items)
    assert snap.data_dir == built_catalog
    print(f"loaded snapshot: total={snap.manifest.total}")


def test_snapshot_index_populated(built_catalog: Path):
    snap = load_catalog_from_dir(built_catalog)
    item = snap.get_item("tree:acme/widget:skills/alpha")
    assert item is not None
    assert item.name == "alpha"
    assert item.item_metadata is None
    assert item.author is None
    print(f"summary ok: {item.name} item_metadata={item.item_metadata}")


def test_get_full_hydrates_detail_fields(built_catalog: Path):
    snap = load_catalog_from_dir(built_catalog)
    full = snap.get_full("tree:acme/widget:skills/alpha")
    assert full is not None
    assert full.item_metadata == {"name": "alpha", "description": "plain ascii skill"}
    assert full.author == "acme"
    assert full.validation_errors == []
    full2 = snap.get_full("tree:acme/widget:skills/alpha")
    assert full2 is full
    cached = snap.get_item("tree:acme/widget:skills/alpha")
    assert cached.item_metadata == full.item_metadata
    print(f"hydrated: item_metadata={full.item_metadata}")


def test_get_full_handles_non_ascii(built_catalog: Path):
    snap = load_catalog_from_dir(built_catalog)
    full = snap.get_full("tree:acme/widget:skills/beta")
    assert full is not None
    assert "🙂" in full.description
    assert "漢字" in full.description
    print(f"non-ascii hydrated: {full.description!r}")


def test_get_full_missing_id_returns_none(built_catalog: Path):
    snap = load_catalog_from_dir(built_catalog)
    assert snap.get_full("does-not-exist") is None


def test_missing_manifest_returns_none(tmp_path: Path):
    (tmp_path / "catalog-summary.json").write_text('{"items":[]}')
    (tmp_path / "catalog-offsets.json").write_text("{}")
    assert load_catalog_from_dir(tmp_path) is None


def test_missing_agent_file_raises(built_catalog: Path):
    (built_catalog / "agent-skill.json").unlink()
    with pytest.raises(FileNotFoundError):
        load_catalog_from_dir(built_catalog)


def test_offset_mismatch_degrades_gracefully(built_catalog: Path):
    offsets = json.loads((built_catalog / "catalog-offsets.json").read_text())
    first_id = next(iter(offsets))
    offsets[first_id] = ["skill", 9999999, 10]
    (built_catalog / "catalog-offsets.json").write_text(json.dumps(offsets))

    snap = load_catalog_from_dir(built_catalog)
    assert snap is not None
    assert snap.get_full(first_id) is None
    assert snap.get_item(first_id) is not None


def test_clear_user_catalog_removes_stale_tree(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    user_catalog = fake_home / ".vibelens" / "catalog"
    user_catalog.mkdir(parents=True)
    (user_catalog / "catalog.json").write_text("{}")
    (user_catalog / "stray.txt").write_text("x")

    from vibelens.storage.extension import catalog as catalog_module

    monkeypatch.setattr(catalog_module, "USER_CATALOG_DIR", user_catalog)
    _clear_user_catalog()
    assert not user_catalog.exists()


def test_clear_user_catalog_idempotent(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    user_catalog = fake_home / ".vibelens" / "catalog"

    from vibelens.storage.extension import catalog as catalog_module

    monkeypatch.setattr(catalog_module, "USER_CATALOG_DIR", user_catalog)
    _clear_user_catalog()


def test_load_catalog_caches(monkeypatch, built_catalog: Path):
    """load_catalog() returns the same instance on repeated calls until reset."""
    from vibelens.storage.extension import catalog as catalog_module

    monkeypatch.setattr(catalog_module, "_catalog_dir", lambda: built_catalog)
    reset_catalog_cache()
    snap1 = catalog_module.load_catalog()
    snap2 = catalog_module.load_catalog()
    assert snap1 is snap2
    reset_catalog_cache()
    snap3 = catalog_module.load_catalog()
    assert snap3 is not snap1
