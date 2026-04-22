"""Tests for extension catalog API endpoints."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from vibelens.app import create_app
from vibelens.models.enums import AgentExtensionType
from vibelens.models.extension import AgentExtensionItem
from vibelens.storage.extension.catalog import CatalogManifest, CatalogSnapshot


def _make_item(
    *,
    extension_id: str,
    extension_type: AgentExtensionType,
    name: str,
    description: str,
    topics: list[str] | None = None,
) -> AgentExtensionItem:
    return AgentExtensionItem(
        extension_id=extension_id,
        extension_type=extension_type,
        name=name,
        description=description,
        topics=topics or [],
        source_url=f"https://github.com/test/{name}/tree/main",
        repo_full_name=f"test/{name}",
        discovery_source="seed",
        quality_score=80.0,
        popularity=0.5,
        stars=10,
        forks=0,
    )


def _make_snapshot() -> CatalogSnapshot:
    """Build a synthetic catalog of 12 items.

    Why 12 and not 2: BM25 IDF misbehaves on tiny corpora (a term
    appearing in exactly half the docs has IDF = ln(1) = 0 in the
    pure Okapi formula, zeroing out its score). Real catalogs have
    thousands of items so this never matters in production, but
    tests must sit outside the pathology.
    """
    items = [
        _make_item(
            extension_id="bwc:skill:test-skill",
            extension_type=AgentExtensionType.SKILL,
            name="test-skill",
            description="A test skill",
            topics=["testing"],
        ),
        _make_item(
            extension_id="bwc:plugin:test-plugin",
            extension_type=AgentExtensionType.PLUGIN,
            name="test-plugin",
            description="A test plugin",
            topics=["plugin"],
        ),
    ]
    # Filler items whose names/descriptions share no tokens with the
    # two items above. Their presence stabilizes IDF without changing
    # which item matches a given query.
    filler_labels = (
        "alpha", "bravo", "charlie", "delta", "echo",
        "foxtrot", "golf", "hotel", "india", "juliet",
    )
    for i, label in enumerate(filler_labels):
        items.append(
            _make_item(
                extension_id=f"bwc:skill:filler-{label}",
                extension_type=AgentExtensionType.SKILL,
                name=f"filler-{label}",
                description=f"unrelated filler item number {i}",
                topics=[f"filler-{label}"],
            )
        )
    skill_count = sum(1 for it in items if it.extension_type == AgentExtensionType.SKILL)
    plugin_count = sum(1 for it in items if it.extension_type == AgentExtensionType.PLUGIN)
    manifest = CatalogManifest(
        generated_on="2026-04-13",
        hub_source="test",
        total=len(items),
        item_counts={"skill": skill_count, "plugin": plugin_count},
        file_sizes={},
    )
    return CatalogSnapshot(manifest=manifest, items=items, data_dir=Path("/nonexistent"))


@pytest.fixture
def client():
    snapshot = _make_snapshot()
    # Reset the extension search index singleton so it rebuilds from the
    # patched catalog (not a cached real 28K-item index from a prior test).
    from vibelens.services.extensions.search import reset_index

    reset_index()
    with (
        patch("vibelens.services.extensions.catalog.load_catalog", return_value=snapshot),
        patch("vibelens.api.extensions.catalog.load_catalog", return_value=snapshot),
        patch("vibelens.storage.extension.catalog.load_catalog", return_value=snapshot),
    ):
        app = create_app()
        yield TestClient(app)
    reset_index()


def test_list_extensions(client):
    resp = client.get("/api/extensions/catalog")
    assert resp.status_code == 200
    data = resp.json()
    # 2 named items + 10 fillers = 12 total when no query is active.
    assert data["total"] == 12
    print(f"Listed {data['total']} items")


def test_list_extensions_search(client):
    """A non-empty query filters to items whose text score is positive."""
    resp = client.get("/api/extensions/catalog?search=plugin")
    assert resp.status_code == 200
    data = resp.json()
    # Only the plugin item contains the token "plugin" in its searchable fields.
    assert data["total"] == 1
    assert data["items"][0]["extension_id"] == "bwc:plugin:test-plugin"


def test_list_extensions_type_filter(client):
    resp = client.get("/api/extensions/catalog?extension_type=plugin")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["extension_type"] == "plugin"


def test_list_extensions_accepts_deprecated_category_param(client):
    """Old clients passing ?category=... still get 200 (param ignored)."""
    resp = client.get("/api/extensions/catalog?category=testing")
    assert resp.status_code == 200
    assert resp.json()["total"] == 12


def test_list_extensions_accepts_deprecated_platform_param(client):
    resp = client.get("/api/extensions/catalog?platform=claude")
    assert resp.status_code == 200
    assert resp.json()["total"] == 12


def test_list_extensions_legacy_sort_popularity_coerced(client):
    """?sort=popularity coerces to default without error."""
    resp = client.get("/api/extensions/catalog?sort=popularity")
    assert resp.status_code == 200
    assert resp.json()["total"] == 12


def test_list_extensions_legacy_sort_relevance_coerced(client):
    """?sort=relevance coerces to personalized (or default when no profile)."""
    resp = client.get("/api/extensions/catalog?sort=relevance")
    assert resp.status_code == 200
    assert resp.json()["total"] == 12


def test_meta_returns_topics(client):
    resp = client.get("/api/extensions/catalog/meta")
    assert resp.status_code == 200
    data = resp.json()
    assert "topics" in data
    assert "plugin" in data["topics"]
    assert "testing" in data["topics"]


def test_get_extension_item_returns_summary_when_offsets_empty(client):
    """Detail endpoint falls back to summary when get_full has no offsets."""
    resp = client.get("/api/extensions/catalog/bwc:skill:test-skill")
    assert resp.status_code == 200
    body = resp.json()
    assert body["extension_id"] == "bwc:skill:test-skill"
    # Detail-only fields stay None when hydration falls back to summary.
    assert body["item_metadata"] is None


def test_get_extension_item_not_found(client):
    resp = client.get("/api/extensions/catalog/nonexistent")
    assert resp.status_code == 404


def test_catalog_tree_returns_stubbed_entries(client, monkeypatch):
    """Tree endpoint shapes the service output into ExtensionTreeResponse."""
    import vibelens.services.extensions.catalog as catalog_service

    def fake_list(source_url: str, max_entries: int) -> tuple[list[dict], bool]:
        assert source_url == "https://github.com/test/test-skill/tree/main"
        return (
            [
                {"path": "SKILL.md", "kind": "file", "size": 100},
                {"path": "LICENSE.txt", "kind": "file", "size": 50},
            ],
            False,
        )

    monkeypatch.setattr(catalog_service, "list_github_tree", fake_list)
    # Clear the tree cache so the stub is exercised.
    catalog_service._tree_cache.clear()

    resp = client.get("/api/extensions/catalog/bwc:skill:test-skill/tree")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "test-skill"
    assert body["truncated"] is False
    paths = {e["path"] for e in body["entries"]}
    assert paths == {"SKILL.md", "LICENSE.txt"}
    print(f"catalog tree paths: {sorted(paths)}")


def test_catalog_file_returns_stubbed_content(client, monkeypatch):
    """File endpoint returns the fetched file body."""
    import vibelens.services.extensions.catalog as catalog_service

    def fake_fetch(source_url: str, relative: str) -> str | None:
        assert source_url == "https://github.com/test/test-skill/tree/main"
        assert relative == "SKILL.md"
        return "# skill body\n"

    monkeypatch.setattr(catalog_service, "fetch_github_tree_file", fake_fetch)
    catalog_service._file_cache.clear()

    resp = client.get("/api/extensions/catalog/bwc:skill:test-skill/files/SKILL.md")
    assert resp.status_code == 200
    body = resp.json()
    assert body["path"] == "SKILL.md"
    assert body["content"] == "# skill body\n"
    assert body["truncated"] is False


def test_catalog_tree_unknown_item_returns_404(client):
    resp = client.get("/api/extensions/catalog/nope/tree")
    assert resp.status_code == 404
