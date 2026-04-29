"""Skill metadata model parsed from SKILL.md files."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vibelens.models.extension.item import VALID_EXTENSION_NAME


class Skill(BaseModel):
    """Parsed SKILL.md metadata."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Kebab-case skill identifier (directory name).")
    description: str = Field(default="", description="From frontmatter.")
    topics: list[str] = Field(
        default_factory=list,
        alias="tags",
        description="Classification topics; accepts legacy `tags:` frontmatter key.",
    )
    allowed_tools: list[str] = Field(default_factory=list, description="From frontmatter.")
    content_hash: str = Field(default="", description="SHA256 of raw SKILL.md content.")
    installed_in: list[str] = Field(default_factory=list, description="Agent keys where installed.")

    @field_validator("name")
    @classmethod
    def validate_kebab_case(cls, v: str) -> str:
        """Ensure name is valid kebab-case."""
        if not VALID_EXTENSION_NAME.match(v):
            raise ValueError(f"Skill name must be kebab-case: {v!r}")
        return v
