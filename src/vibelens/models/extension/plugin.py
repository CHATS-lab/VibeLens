"""Plugin metadata model parsed from .claude-plugin/plugin.json files."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vibelens.models.extension.item import VALID_EXTENSION_NAME


class Plugin(BaseModel):
    """Parsed plugin.json metadata."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Kebab-case plugin identifier (directory name).")
    description: str = Field(default="", description="From plugin.json.")
    version: str = Field(default="0.0.0", description="From plugin.json version field.")
    topics: list[str] = Field(
        default_factory=list,
        alias="tags",
        description="From plugin.json keywords; accepts legacy `tags:` key.",
    )
    content_hash: str = Field(default="", description="SHA256 of raw plugin.json.")
    installed_in: list[str] = Field(default_factory=list, description="Agent keys where installed.")

    @field_validator("name")
    @classmethod
    def validate_kebab_case(cls, v: str) -> str:
        """Ensure name is valid kebab-case."""
        if not VALID_EXTENSION_NAME.match(v):
            raise ValueError(f"Plugin name must be kebab-case: {v!r}")
        return v
