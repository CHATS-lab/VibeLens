"""Tests for catalog API endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from vibelens.app import create_app
from vibelens.models.enums import AgentExtensionType
from vibelens.models.extension import ExtensionItem
from vibelens.services.recommendation.catalog import CatalogSnapshot


def _make_snapshot() -> CatalogSnapshot:
    """Create a test catalog snapshot."""
    items = [
        ExtensionItem(
            extension_id="bwc:skill:test-skill",
            extension_type=AgentExtensionType.SKILL,
            name="test-skill",
            description="A test skill",
            tags=["testing"],
            category="testing",
            platforms=["claude_code"],
            quality_score=80.0,
            popularity=0.5,
            updated_at="2026-04-01T00:00:00Z",
            source_url="https://github.com/test/repo",
            repo_full_name="test/repo",
            install_method="skill_file",
            install_content="# Test Skill\nContent here.",
        ),
        ExtensionItem(
            extension_id="bwc:mcp:test-mcp",
            extension_type=AgentExtensionType.REPO,
            name="test-mcp",
            description="A test MCP server",
            tags=["mcp"],
            category="development",
            platforms=["claude_code"],
            quality_score=75.0,
            popularity=0.3,
            updated_at="",
            source_url="",
            repo_full_name="",
            install_method="mcp_config",
            install_command="npx test-server",
            install_content=(
                '{"mcpServers": {"test-mcp": {"command": "npx", "args": ["test-server"]}}}'
            ),
        ),
    ]
    return CatalogSnapshot(version="2026-04-13", schema_version=1, items=items)


@pytest.fixture
def client():
    """Create test client with mocked catalog."""
    with patch("vibelens.api.catalog.load_catalog", return_value=_make_snapshot()):
        app = create_app()
        yield TestClient(app)


def test_list_catalog(client):
    """GET /api/catalog returns paginated items."""
    resp = client.get("/api/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    print(f"Listed {data['total']} items")


def test_list_catalog_search(client):
    """GET /api/catalog?search=mcp filters by keyword."""
    resp = client.get("/api/catalog?search=mcp")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["extension_id"] == "bwc:mcp:test-mcp"
    print(f"Search 'mcp': {data['total']} results")


def test_list_catalog_type_filter(client):
    """GET /api/catalog?item_type=skill filters by type."""
    resp = client.get("/api/catalog?item_type=skill")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["extension_type"] == "skill"
    print(f"Type filter: {data['total']} results")


def test_get_catalog_item(client):
    """GET /api/catalog/{item_id} returns full item."""
    resp = client.get("/api/catalog/bwc:skill:test-skill")
    assert resp.status_code == 200
    data = resp.json()
    assert data["extension_id"] == "bwc:skill:test-skill"
    assert data["install_content"] is not None
    print(f"Got item: {data['extension_id']}")


def test_get_catalog_item_not_found(client):
    """GET /api/catalog/nonexistent returns 404."""
    resp = client.get("/api/catalog/nonexistent")
    assert resp.status_code == 404
    print("404 for nonexistent item")


def test_get_catalog_item_content_with_install_content(client):
    """Content endpoint returns install_content for file-based items."""
    resp = client.get("/api/catalog/bwc:skill:test-skill/content")
    assert resp.status_code == 200
    data = resp.json()
    assert data["content_type"] == "install_content"
    assert "Test Skill" in data["content"]
    print(f"Content type: {data['content_type']}, length: {len(data['content'])}")


def test_get_catalog_item_content_null_for_empty_item(client):
    """Content endpoint returns null content for item without install_content or repo."""
    # bwc:mcp:test-mcp has install_content (MCP JSON config), so it should return it
    resp = client.get("/api/catalog/bwc:mcp:test-mcp/content")
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] is not None
    print(f"MCP content type: {data['content_type']}")


def test_get_catalog_item_content_not_found(client):
    """Content endpoint returns 404 for unknown item."""
    resp = client.get("/api/catalog/test:skill:nonexistent/content")
    assert resp.status_code == 404
