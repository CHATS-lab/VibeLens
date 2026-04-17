"""Skill metadata model parsed from SKILL.md files."""

from pydantic import BaseModel, Field, field_validator

from vibelens.storage.extension.base_store import VALID_EXTENSION_NAME


class Skill(BaseModel):
    """Parsed SKILL.md metadata."""

    name: str = Field(description="Kebab-case skill identifier (directory name).")
    description: str = Field(default="", description="From frontmatter.")
    tags: list[str] = Field(default_factory=list, description="From frontmatter.")
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
