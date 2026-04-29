"""Command metadata model parsed from flat .md command files."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vibelens.models.extension.item import VALID_EXTENSION_NAME


class Command(BaseModel):
    """Parsed command metadata from a flat .md file."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Kebab-case command identifier (filename without .md).")
    description: str = Field(default="", description="From frontmatter.")
    topics: list[str] = Field(
        default_factory=list,
        alias="tags",
        description="Classification topics; accepts legacy `tags:` frontmatter key.",
    )
    content_hash: str = Field(default="", description="SHA256 of raw .md content.")
    installed_in: list[str] = Field(default_factory=list, description="Agent keys where installed.")

    @field_validator("name")
    @classmethod
    def validate_kebab_case(cls, v: str) -> str:
        """Ensure name is valid kebab-case."""
        if not VALID_EXTENSION_NAME.match(v):
            raise ValueError(f"Command name must be kebab-case: {v!r}")
        return v
