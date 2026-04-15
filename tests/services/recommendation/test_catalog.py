"""Tests for the recommendation catalog loader."""

import json
import tempfile
from pathlib import Path

from vibelens.models.extension import ExtensionItem
from vibelens.storage.extension.catalog import load_catalog_from_path


def _build_test_catalog(item_count: int = 3) -> dict:
    """Build a minimal catalog dict for testing."""
    items = []
    for i in range(item_count):
        items.append(
            {
                "extension_id": f"test-org/test-repo-{i}",
                "extension_type": "skill",
                "name": f"test-skill-{i}",
                "description": f"Test skill {i} description",
                "tags": ["test", "skill"],
                "category": "testing",
                "platforms": ["claude-code"],
                "quality_score": 75.0,
                "popularity": 0.5,
                "updated_at": "2026-04-01T00:00:00Z",
                "source_url": f"https://github.com/test-org/test-repo-{i}",
                "repo_full_name": f"test-org/test-repo-{i}",
                "install_method": "skill_file",
            }
        )
    return {
        "schema_version": 1,
        "version": "2026-04-10",
        "built_at": "2026-04-10T08:30:00Z",
        "item_count": item_count,
        "items": items,
    }


def test_load_catalog_from_path():
    """load_catalog_from_path parses catalog.json into CatalogSnapshot."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(_build_test_catalog(5), f)
        path = Path(f.name)

    snapshot = load_catalog_from_path(path)
    assert snapshot is not None
    assert snapshot.version == "2026-04-10"
    assert len(snapshot.items) == 5
    assert all(isinstance(item, ExtensionItem) for item in snapshot.items)
    print(f"Loaded {len(snapshot.items)} items, version={snapshot.version}")
    path.unlink()


def test_load_catalog_missing_file():
    """load_catalog_from_path returns None for missing file."""
    snapshot = load_catalog_from_path(Path("/nonexistent/catalog.json"))
    assert snapshot is None


def test_load_catalog_invalid_json():
    """load_catalog_from_path returns None for corrupt JSON."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("not json")
        path = Path(f.name)

    snapshot = load_catalog_from_path(path)
    assert snapshot is None
    path.unlink()


def test_catalog_snapshot_item_lookup():
    """CatalogSnapshot supports item lookup by ID."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(_build_test_catalog(3), f)
        path = Path(f.name)

    snapshot = load_catalog_from_path(path)
    item = snapshot.get_item("test-org/test-repo-1")
    assert item is not None
    assert item.name == "test-skill-1"
    assert snapshot.get_item("nonexistent") is None
    path.unlink()
