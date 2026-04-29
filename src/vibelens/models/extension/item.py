"""Agent extension item model and type utilities."""

import re

from pydantic import BaseModel, ConfigDict, Field, computed_field

from vibelens.models.enums import AgentExtensionType

# Shared name validator for all extension types (skills, subagents, commands,
# hooks, plugins). Kept here so models/ never has to import from storage/.
VALID_EXTENSION_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

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
    AgentExtensionType.PLUGIN: "Plugin",
    AgentExtensionType.MCP_SERVER: "MCP Server",
    AgentExtensionType.REPO: "Repository",
}


class AgentExtensionItem(BaseModel):
    """A discoverable agent extension with quality metrics and install metadata.

    Faithful to ``agent-tool-hub``'s output schema, with two VibeLens-local
    conventions: field names ``extension_id`` / ``extension_type`` (aliased
    to the hub's ``item_id`` / ``item_type``), and a ``popularity`` value
    pre-baked at catalog-build time from star counts.

    Detail-only fields default to ``None`` — the catalog-summary file omits
    them, and the loader repopulates them on demand from the per-type JSON.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    extension_id: str = Field(alias="item_id", description="Unique identifier.")
    extension_type: AgentExtensionType = Field(alias="item_type", description="Classified type.")
    name: str = Field(description="Display name.")

    description: str | None = Field(default=None, description="Per-item description.")
    repo_description: str | None = Field(default=None, description="Repo-level description.")
    readme_description: str | None = Field(default=None, description="First README paragraph.")

    author: str | None = Field(default=None, description="GitHub owner/org login.")
    source_url: str = Field(description="GitHub URL (repo or tree path).")
    repo_full_name: str = Field(description="GitHub owner/repo.")
    path_in_repo: str | None = Field(default=None, description="Path within repo.")

    discovery_source: str = Field(description='"seed" or "awesome_list".')
    discovery_origin: str | None = Field(default=None, description="Slug that surfaced the item.")

    topics: list[str] = Field(default_factory=list, description="Repo topics.")
    platforms: list[str] | None = Field(
        default=None,
        description="VibeLens-derived compatible platforms. Reserved for next release.",
    )

    scores: dict[str, float] | None = Field(
        default=None, description="Per-dimension score breakdown."
    )
    quality_score: float = Field(description="Weighted composite 0-100.")
    popularity: float = Field(
        default=0.0,
        description="log1p(stars)/log1p(MAX_STARS). Pre-baked at catalog-build time.",
    )

    stars: int = Field(description="GitHub star count.")
    forks: int = Field(description="GitHub fork count.")
    license: str | None = Field(default=None, description="SPDX id of containing repo.")
    language: str | None = Field(default=None, description="Primary repo language.")
    updated_at: str | None = Field(default=None, description="Last push ISO8601.")
    created_at: str | None = Field(default=None, description="Repo creation ISO8601.")

    author_followers: int | None = Field(default=None, description="Owner follower count.")
    contributors_count: int | None = Field(default=None, description="Repo contributor count.")

    item_metadata: dict[str, str] | None = Field(
        default=None,
        description="Primary metadata file key-value pairs (frontmatter/JSON/TOML).",
    )
    validation_errors: list[str] | None = Field(
        default=None, description="Per-type validation errors."
    )

    install_command: str | None = Field(
        default=None, description="VibeLens-only; meaningful for REPO. Reserved."
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_valid(self) -> bool:
        """True when no validation errors recorded."""
        return not self.validation_errors

    @computed_field  # type: ignore[prop-decorator]
    @property
    def display_description(self) -> str | None:
        """First non-empty description across (description, readme, repo)."""
        if self.description:
            return self.description
        if self.readme_description:
            return self.readme_description
        if self.repo_description:
            return self.repo_description
        return None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_file_based(self) -> bool:
        """True for file-based types (skill, subagent, command, hook)."""
        return self.extension_type in FILE_BASED_TYPES
