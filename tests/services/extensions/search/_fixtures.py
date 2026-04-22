"""Shared fixtures for search module tests."""

from vibelens.models.enums import AgentExtensionType
from vibelens.models.extension import AgentExtensionItem


def make_item(
    name: str,
    description: str = "",
    topics: list[str] | None = None,
    ext_type: AgentExtensionType = AgentExtensionType.SKILL,
    quality: float = 75.0,
    popularity: float = 0.5,
    updated_at: str = "2026-04-01T00:00:00Z",
    readme: str = "",
    author: str = "alice",
) -> AgentExtensionItem:
    """Build a minimal :class:`AgentExtensionItem` for tests."""
    return AgentExtensionItem(
        extension_id=f"{author}/{name}",
        extension_type=ext_type,
        name=name,
        description=description,
        topics=topics or [],
        quality_score=quality,
        popularity=popularity,
        updated_at=updated_at,
        source_url=f"https://github.com/{author}/{name}",
        repo_full_name=f"{author}/{name}",
        author=author,
        readme_description=readme,
        discovery_source="seed",
        stars=10,
        forks=0,
    )
