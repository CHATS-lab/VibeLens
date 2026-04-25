"""Pydantic models for extension collections."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from vibelens.models.enums import AgentExtensionType
from vibelens.storage.extension.base_store import VALID_EXTENSION_NAME


class ExtensionCollectionItem(BaseModel):
    """A single (extension_type, name) reference inside a collection."""

    model_config = ConfigDict(populate_by_name=True)

    extension_type: AgentExtensionType = Field(description="Type of extension this item points at.")
    name: str = Field(description="Kebab-case extension name.")
    pinned_version: str | None = Field(
        default=None, description="Optional version string. None means 'always latest'."
    )

    @field_validator("name")
    @classmethod
    def validate_kebab_case(cls, v: str) -> str:
        if not VALID_EXTENSION_NAME.match(v):
            raise ValueError(f"Item name must be kebab-case: {v!r}")
        return v


class ExtensionCollection(BaseModel):
    """A named bundle of mixed extension references."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Kebab-case collection identifier.")
    description: str = Field(default="", description="Human description.")
    items: list[ExtensionCollectionItem] = Field(
        default_factory=list, description="Ordered list of extension references."
    )
    tags: list[str] = Field(default_factory=list, description="Free-form tags.")
    created_at: datetime = Field(description="Creation timestamp (UTC).")
    updated_at: datetime = Field(description="Last-modified timestamp (UTC).")

    @field_validator("name")
    @classmethod
    def validate_kebab_case(cls, v: str) -> str:
        if not VALID_EXTENSION_NAME.match(v):
            raise ValueError(f"Collection name must be kebab-case: {v!r}")
        return v

    @model_validator(mode="after")
    def reject_duplicate_items(self) -> "ExtensionCollection":
        seen: set[tuple[str, str]] = set()
        for item in self.items:
            key = (item.extension_type.value, item.name)
            if key in seen:
                raise ValueError(f"duplicate item in collection: {key}")
            seen.add(key)
        return self
