"""Catalog API request/response schemas."""

from pydantic import BaseModel, Field


class CatalogListResponse(BaseModel):
    """Paginated catalog listing response."""

    items: list[dict] = Field(description="Catalog items (without install_content for list view).")
    total: int = Field(description="Total matching items.")
    page: int = Field(description="Current page number.")
    per_page: int = Field(description="Items per page.")


class CatalogInstallRequest(BaseModel):
    """Request body for installing a catalog item."""

    target_platform: str = Field(
        default="claude_code",
        description="Target agent platform for installation.",
    )
    overwrite: bool = Field(
        default=False,
        description="Overwrite existing file if it already exists.",
    )


class CatalogInstallResponse(BaseModel):
    """Response after installing a catalog item."""

    success: bool = Field(description="Whether installation succeeded.")
    installed_path: str = Field(description="Path where the item was installed.")
    message: str = Field(default="", description="Additional status message.")


class CatalogMetaResponse(BaseModel):
    """Catalog metadata for frontend filter/sort options."""

    categories: list[str] = Field(description="Unique category values from catalog.")
    has_profile: bool = Field(description="Whether a user profile exists for relevance sorting.")
