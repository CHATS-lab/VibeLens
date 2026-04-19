"""Regression tests for catalog content resolution (Explore detail view)."""

import pytest

from vibelens.models.enums import AgentExtensionType
from vibelens.models.extension import AgentExtensionItem
from vibelens.services.extensions import catalog as catalog_module
from vibelens.services.extensions.catalog import _resolve_content


def _make_item(
    *,
    extension_type: AgentExtensionType,
    source_url: str,
    repo_full_name: str = "acme/widget",
    name: str = "demo",
) -> AgentExtensionItem:
    return AgentExtensionItem(
        extension_id=f"tree:acme/widget:{extension_type.value}/{name}",
        extension_type=extension_type,
        name=name,
        source_url=source_url,
        repo_full_name=repo_full_name,
        discovery_source="seed",
        topics=[],
        quality_score=70.0,
        popularity=0.5,
        stars=10,
        forks=0,
    )


@pytest.mark.asyncio
async def test_tree_url_pointing_at_md_file_fetches_raw_file(monkeypatch):
    """Regression: subagent tree URLs ending in .md used to 404 when treated
    as directories. They must be fetched as raw files instead.
    """
    fetched_urls: list[str] = []

    async def fake_fetch(url: str) -> str | None:
        fetched_urls.append(url)
        return "# security-reviewer\n\nbody\n"

    monkeypatch.setattr(catalog_module, "async_fetch_text", fake_fetch)
    item = _make_item(
        extension_type=AgentExtensionType.SUBAGENT,
        source_url="https://github.com/affaan-m/everything-claude-code/tree/main/.kiro/agents/security-reviewer.md",
        name="security-reviewer",
    )

    result = await _resolve_content(item)

    assert result["content_type"] == "markdown"
    assert result["content"] == "# security-reviewer\n\nbody\n"
    assert fetched_urls == [
        "https://raw.githubusercontent.com/affaan-m/everything-claude-code/main/.kiro/agents/security-reviewer.md"
    ]
    print(f"fetched from {fetched_urls[0]}")


@pytest.mark.asyncio
async def test_tree_url_pointing_at_directory_still_fetches_skill_md(monkeypatch):
    """Skill tree URLs point at a directory - SKILL.md lookup must still work."""
    fetched_urls: list[str] = []

    async def fake_fetch(url: str) -> str | None:
        fetched_urls.append(url)
        return "---\nname: frontend-design\n---\nbody"

    monkeypatch.setattr(catalog_module, "async_fetch_text", fake_fetch)
    item = _make_item(
        extension_type=AgentExtensionType.SKILL,
        source_url="https://github.com/acme/widget/tree/main/skills/frontend-design",
        name="frontend-design",
    )

    result = await _resolve_content(item)

    assert result["content_type"] == "skill_md"
    assert fetched_urls == [
        "https://raw.githubusercontent.com/acme/widget/main/skills/frontend-design/SKILL.md"
    ]


@pytest.mark.asyncio
async def test_blob_url_fetches_raw_blob(monkeypatch):
    fetched_urls: list[str] = []

    async def fake_fetch(url: str) -> str | None:
        fetched_urls.append(url)
        return "body"

    monkeypatch.setattr(catalog_module, "async_fetch_text", fake_fetch)
    item = _make_item(
        extension_type=AgentExtensionType.COMMAND,
        source_url="https://github.com/acme/widget/blob/main/commands/sync.md",
        name="sync",
    )

    result = await _resolve_content(item)

    assert result["content_type"] == "markdown"
    assert fetched_urls == [
        "https://raw.githubusercontent.com/acme/widget/main/commands/sync.md"
    ]


@pytest.mark.asyncio
async def test_repo_item_fetches_readme(monkeypatch):
    fetched_urls: list[str] = []

    async def fake_fetch(url: str) -> str | None:
        fetched_urls.append(url)
        return "# readme"

    monkeypatch.setattr(catalog_module, "async_fetch_text", fake_fetch)
    item = _make_item(
        extension_type=AgentExtensionType.REPO,
        source_url="https://github.com/acme/widget",
        name="widget",
    )

    result = await _resolve_content(item)

    assert result["content_type"] == "readme"
    assert fetched_urls == ["https://raw.githubusercontent.com/acme/widget/HEAD/README.md"]


@pytest.mark.asyncio
async def test_plugin_tree_url_fetches_readme_from_plugin_dir(monkeypatch):
    """Plugins with a tree URL should fetch README.md from inside the plugin
    path, not SKILL.md. README takes precedence over plugin.json.
    """
    fetched_urls: list[str] = []

    async def fake_fetch(url: str) -> str | None:
        fetched_urls.append(url)
        return "# Plugin readme\n" if url.endswith("README.md") else None

    monkeypatch.setattr(catalog_module, "async_fetch_text", fake_fetch)
    item = _make_item(
        extension_type=AgentExtensionType.PLUGIN,
        source_url="https://github.com/wshobson/agents/tree/main/plugins/documentation-standards",
        name="documentation-standards",
    )

    result = await _resolve_content(item)

    assert result["content_type"] == "readme"
    assert result["content"].startswith("# Plugin readme")
    assert fetched_urls[0] == (
        "https://raw.githubusercontent.com/wshobson/agents/main/"
        "plugins/documentation-standards/README.md"
    )


@pytest.mark.asyncio
async def test_plugin_tree_url_falls_back_to_manifest_when_no_readme(monkeypatch):
    """When README is missing, plugin content falls back to plugin.json."""
    fetched_urls: list[str] = []

    async def fake_fetch(url: str) -> str | None:
        fetched_urls.append(url)
        if url.endswith("plugin.json"):
            return '{"name": "demo"}'
        return None

    monkeypatch.setattr(catalog_module, "async_fetch_text", fake_fetch)
    item = _make_item(
        extension_type=AgentExtensionType.PLUGIN,
        source_url="https://github.com/wshobson/agents/tree/main/plugins/documentation-standards",
        name="documentation-standards",
    )

    result = await _resolve_content(item)

    assert result["content_type"] == "markdown"
    assert '"name": "demo"' in result["content"]
    # First README attempt, then plugin.json.
    assert len(fetched_urls) == 2
    assert fetched_urls[0].endswith("README.md")
    assert fetched_urls[1].endswith(".claude-plugin/plugin.json")


@pytest.mark.asyncio
async def test_plugin_bare_repo_url_fetches_readme_from_root(monkeypatch):
    """Catalog entries with a bare repo URL (no tree/) must still resolve."""
    fetched_urls: list[str] = []

    async def fake_fetch(url: str) -> str | None:
        fetched_urls.append(url)
        return "# Root readme" if url.endswith("README.md") else None

    monkeypatch.setattr(catalog_module, "async_fetch_text", fake_fetch)
    item = _make_item(
        extension_type=AgentExtensionType.PLUGIN,
        source_url="https://github.com/affaan-m/everything-claude-code",
        name="everything-claude-code",
    )

    result = await _resolve_content(item)

    assert result["content_type"] == "readme"
    assert fetched_urls[0] == (
        "https://raw.githubusercontent.com/affaan-m/everything-claude-code/HEAD/README.md"
    )


@pytest.mark.asyncio
async def test_bare_repo_non_plugin_fetches_readme_at_head(monkeypatch):
    """Any bare-repo catalog URL (not just plugins) should resolve to README."""
    fetched_urls: list[str] = []

    async def fake_fetch(url: str) -> str | None:
        fetched_urls.append(url)
        return "# readme"

    monkeypatch.setattr(catalog_module, "async_fetch_text", fake_fetch)
    item = _make_item(
        extension_type=AgentExtensionType.SKILL,
        source_url="https://github.com/acme/widget",
        name="widget",
    )

    result = await _resolve_content(item)

    assert result["content_type"] == "readme"
    assert fetched_urls == [
        "https://raw.githubusercontent.com/acme/widget/HEAD/README.md"
    ]


@pytest.mark.asyncio
async def test_missing_content_returns_error_field(monkeypatch):
    async def fake_fetch(url: str) -> str | None:
        return None

    monkeypatch.setattr(catalog_module, "async_fetch_text", fake_fetch)
    item = _make_item(
        extension_type=AgentExtensionType.SUBAGENT,
        source_url="https://github.com/acme/widget/tree/main/agents/x.md",
        name="x",
    )

    result = await _resolve_content(item)

    assert result["content"] is None
    assert "Failed to fetch" in result["error"]
