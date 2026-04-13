"""Tests for the catalog builder orchestrator."""
import json
from pathlib import Path
from unittest.mock import patch

from vibelens.catalog.builder import build_catalog
from vibelens.models.recommendation.catalog import ItemType


def _noop_validate(items):
    """Bypass URL validation in tests (no network access)."""
    return items


def _setup_hub(tmp_path: Path) -> Path:
    """Create a minimal hub directory with one item from each source."""
    bwc = tmp_path / "buildwithclaude"
    agent_dir = bwc / "plugins" / "agents-test" / "agents"
    agent_dir.mkdir(parents=True)
    (agent_dir / "test-agent.md").write_text("""---
name: test-agent
description: A test agent for validation
category: testing
---
# Test Agent
""")
    (bwc / "mcp-servers.json").write_text(json.dumps({
        "mcpServers": {
            "test-mcp": {
                "command": "npx",
                "args": ["-y", "test-server"],
                "_metadata": {
                    "displayName": "Test MCP",
                    "category": "dev",
                    "description": "A test MCP server",
                },
            }
        }
    }))
    cct = tmp_path / "claude-code-templates"
    skill_dir = cct / "cli-tool" / "components" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill from templates
---
# Test Skill
""")
    featured = tmp_path / "skills-hub"
    featured.mkdir(parents=True)
    (featured / "featured-skills.json").write_text(json.dumps({
        "skills": [{
            "slug": "featured-skill",
            "name": "featured-skill",
            "summary": "A featured skill with many stars",
            "stars": 5000,
            "category": "ai-assistant",
            "tags": ["featured"],
            "source_url": "https://github.com/anthropics/skills/tree/main/skills/featured-skill",
            "updated_at": "2026-03-25T00:00:00Z",
        }]
    }))
    return tmp_path


@patch("vibelens.catalog.builder.validate_source_urls", side_effect=_noop_validate)
def test_build_catalog_produces_items(mock_validate, tmp_path: Path):
    """Builder reads all sources and produces scored, deduped items."""
    hub_dir = _setup_hub(tmp_path)
    output_path = tmp_path / "catalog.json"
    items = build_catalog(hub_dir=hub_dir, output_path=output_path)
    assert len(items) >= 4
    assert output_path.is_file()
    data = json.loads(output_path.read_text())
    assert data["schema_version"] == 1
    assert len(data["items"]) == len(items)
    print(f"Built {len(items)} items, output at {output_path}")
    for item in items:
        print(f"  {item.item_id}: score={item.quality_score:.1f}, type={item.item_type}")


@patch("vibelens.catalog.builder.validate_source_urls", side_effect=_noop_validate)
def test_build_catalog_all_items_scored(mock_validate, tmp_path: Path):
    """Every item has quality_score in valid range."""
    hub_dir = _setup_hub(tmp_path)
    items = build_catalog(hub_dir=hub_dir, output_path=tmp_path / "out.json")
    for item in items:
        assert 50.0 <= item.quality_score <= 100.0, f"{item.item_id} score={item.quality_score}"
    print(f"All {len(items)} items scored in 50-100 range")


@patch("vibelens.catalog.builder.validate_source_urls", side_effect=_noop_validate)
def test_build_catalog_preserves_existing(mock_validate, tmp_path: Path):
    """Existing hand-curated items are preserved."""
    hub_dir = _setup_hub(tmp_path)
    existing_path = tmp_path / "existing.json"
    existing_path.write_text(json.dumps({
        "version": "2026-04-12",
        "schema_version": 1,
        "items": [{
            "item_id": "skill-memory-bank",
            "item_type": "skill",
            "name": "Memory Bank",
            "description": "Persistent project memory",
            "tags": ["memory"],
            "category": "context-management",
            "platforms": ["claude_code"],
            "quality_score": 88.0,
            "popularity": 0.92,
            "updated_at": "2026-04-01T00:00:00Z",
            "source_url": "https://github.com/AnswerDotAI/memory-bank",
            "repo_full_name": "AnswerDotAI/memory-bank",
            "install_method": "skill_file",
        }],
    }))
    items = build_catalog(
        hub_dir=hub_dir,
        output_path=tmp_path / "out.json",
        existing_catalog_path=existing_path,
    )
    existing_ids = {i.item_id for i in items if i.item_id == "skill-memory-bank"}
    assert "skill-memory-bank" in existing_ids
    print(f"Preserved existing: {existing_ids}")


@patch("vibelens.catalog.builder.validate_source_urls", side_effect=_noop_validate)
def test_build_catalog_type_distribution(mock_validate, tmp_path: Path):
    """Builder produces items of various types."""
    hub_dir = _setup_hub(tmp_path)
    items = build_catalog(hub_dir=hub_dir, output_path=tmp_path / "out.json")
    types = {i.item_type for i in items}
    assert ItemType.SUBAGENT in types
    assert ItemType.SKILL in types
    assert ItemType.REPO in types
    print(f"Types: {[t.value for t in types]}")
