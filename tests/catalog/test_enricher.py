"""Tests for catalog GitHub enrichment."""

from vibelens.catalog.enricher import (
    _construct_source_url,
    _extract_repo_full_name,
)
from vibelens.models.recommendation.catalog import CatalogItem, ItemType


def _make_item(item_id: str, source_url: str = "", item_type: str = "skill") -> CatalogItem:
    """Build a minimal CatalogItem for testing."""
    return CatalogItem(
        item_id=item_id,
        item_type=ItemType(item_type),
        name=item_id.split(":")[-1],
        description="Test item",
        tags=[],
        category="test",
        platforms=["claude_code"],
        quality_score=70.0,
        popularity=0.0,
        updated_at="",
        source_url=source_url,
        repo_full_name="",
        install_method="skill_file",
    )


def test_construct_source_url_bwc_plugin():
    item = _make_item("bwc:agent:python-expert")
    path_map = {"bwc:agent:python-expert": "plugins/python-tools/agents/python-expert.md"}
    url = _construct_source_url(item, path_map, bwc_repo="davepoon/buildwithclaude")
    assert url == "https://github.com/davepoon/buildwithclaude/blob/main/plugins/python-tools/agents/python-expert.md"


def test_construct_source_url_cct_item():
    item = _make_item("cct:skill:arxiv-assistant")
    path_map = {"cct:skill:arxiv-assistant": "cli-tool/components/skills/arxiv-assistant/SKILL.md"}
    url = _construct_source_url(item, path_map, cct_repo="davila7/claude-code-templates")
    assert url == "https://github.com/davila7/claude-code-templates/blob/main/cli-tool/components/skills/arxiv-assistant/SKILL.md"


def test_construct_source_url_already_has_url():
    item = _make_item("featured:skill:foo", source_url="https://github.com/org/repo/tree/main/skills/foo")
    url = _construct_source_url(item, {})
    assert url == "https://github.com/org/repo/tree/main/skills/foo"


def test_construct_source_url_no_match():
    item = _make_item("bwc:agent:unknown")
    url = _construct_source_url(item, {}, bwc_repo="davepoon/buildwithclaude")
    assert url == ""


def test_extract_repo_full_name_standard_url():
    url = "https://github.com/anthropics/skills/tree/main/x"
    assert _extract_repo_full_name(url) == "anthropics/skills"


def test_extract_repo_full_name_simple_url():
    url = "https://github.com/domdomegg/airtable-mcp-server"
    assert _extract_repo_full_name(url) == "domdomegg/airtable-mcp-server"


def test_extract_repo_full_name_org_only():
    assert _extract_repo_full_name("https://github.com/302ai") == ""


def test_extract_repo_full_name_empty():
    assert _extract_repo_full_name("") == ""
