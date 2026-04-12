"""Catalog item model and type classification for the recommendation pipeline."""

from pydantic import BaseModel, Field, computed_field

from vibelens.utils.compat import StrEnum


class ItemType(StrEnum):
    """Catalog item type classification."""

    SKILL = "skill"
    SUBAGENT = "subagent"
    COMMAND = "command"
    HOOK = "hook"
    REPO = "repo"


FILE_BASED_TYPES: set[ItemType] = {
    ItemType.SKILL,
    ItemType.SUBAGENT,
    ItemType.COMMAND,
    ItemType.HOOK,
}

ITEM_TYPE_LABELS: dict[ItemType, str] = {
    ItemType.SKILL: "Skill",
    ItemType.SUBAGENT: "Expert Agent",
    ItemType.COMMAND: "Slash Command",
    ItemType.HOOK: "Automation",
    ItemType.REPO: "Repository",
}


class CatalogItem(BaseModel):
    """A single item in the recommendation catalog.

    Represents a discoverable AI tool (skill, subagent, command, hook, or repo)
    with quality metrics and installation metadata.
    """

    item_id: str = Field(description="Unique identifier.")
    item_type: ItemType = Field(description="Classified type.")
    name: str = Field(description="Display name.")
    description: str = Field(description="Plain language, 1-2 sentences.")
    tags: list[str] = Field(description="Searchable tags.")
    category: str = Field(description="Classification category.")
    platforms: list[str] = Field(description="Compatible agent platforms.")
    quality_score: float = Field(description="0-100 composite from crawler scorer.")
    popularity: float = Field(description="Normalized from stars, 0.0-1.0.")
    updated_at: str = Field(description="Last commit ISO timestamp.")
    source_url: str = Field(description="GitHub URL.")
    repo_full_name: str = Field(description="GitHub owner/repo.")
    install_method: str = Field(
        description="Installation method: skill_file, pip, npm, mcp_config, etc."
    )
    install_command: str | None = Field(
        default=None, description="CLI install command, e.g. 'pip install foo'."
    )
    install_content: str | None = Field(
        default=None, description="Full file content for direct install."
    )

    @computed_field
    @property
    def is_file_based(self) -> bool:
        """True for file-based types (skill, subagent, command, hook)."""
        return self.item_type in FILE_BASED_TYPES
