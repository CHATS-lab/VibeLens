"""Agent extension model and type constants."""

from pydantic import BaseModel, Field, computed_field

from vibelens.models.enums import AgentExtensionType

FILE_BASED_TYPES: set[AgentExtensionType] = {
    AgentExtensionType.SKILL,
    AgentExtensionType.SUBAGENT,
    AgentExtensionType.COMMAND,
    AgentExtensionType.HOOK,
}

EXTENSION_TYPE_LABELS: dict[AgentExtensionType, str] = {
    AgentExtensionType.SKILL: "Skill",
    AgentExtensionType.SUBAGENT: "Expert Agent",
    AgentExtensionType.COMMAND: "Slash Command",
    AgentExtensionType.HOOK: "Automation",
    AgentExtensionType.REPO: "Repository",
}


class ExtensionItem(BaseModel):
    """A discoverable agent extension with quality metrics and installation metadata.

    Represents a skill, subagent, command, hook, or repo that users can
    browse, install, create, or evolve.
    """

    extension_id: str = Field(description="Unique identifier.")
    extension_type: AgentExtensionType = Field(description="Classified type.")
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
    stars: int = Field(default=0, description="GitHub star count.")
    forks: int = Field(default=0, description="GitHub fork count.")
    language: str = Field(default="", description="Primary repository language.")
    license_name: str = Field(default="", description="Repository license identifier (e.g. MIT).")
    install_method: str = Field(
        description="Installation method: skill_file, hook_config, mcp_config, pip, npm, etc."
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
        return self.extension_type in FILE_BASED_TYPES
