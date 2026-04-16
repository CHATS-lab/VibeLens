"""Extension browsing API request/response schemas."""

from pydantic import BaseModel, Field


class ExtensionListResponse(BaseModel):
    """Paginated extension listing response."""

    items: list[dict] = Field(description="Extension items (without install_content).")
    total: int = Field(description="Total matching items.")
    page: int = Field(description="Current page number.")
    per_page: int = Field(description="Items per page.")


class ExtensionInstallRequest(BaseModel):
    """Request body for installing an extension item."""

    target_platforms: list[str] | None = Field(
        default=None, description="Target agent platforms for installation."
    )
    overwrite: bool = Field(
        default=False, description="Overwrite existing file if it already exists."
    )


class ExtensionInstallResult(BaseModel):
    """Result of installing to a single platform."""

    success: bool = Field(description="Whether installation succeeded.")
    installed_path: str = Field(default="", description="Path where the item was installed.")
    message: str = Field(default="", description="Additional status message.")


class ExtensionInstallResponse(BaseModel):
    """Response after installing an extension item."""

    success: bool = Field(description="Whether all installations succeeded.")
    installed_path: str = Field(default="", description="Path of first successful install.")
    message: str = Field(default="", description="Additional status message.")
    results: dict[str, ExtensionInstallResult] = Field(
        default_factory=dict, description="Per-platform install results."
    )


class ExtensionMetaResponse(BaseModel):
    """Extension catalog metadata for frontend filter/sort options."""

    categories: list[str] = Field(description="Unique category values from catalog.")
    has_profile: bool = Field(description="Whether a user profile exists for relevance sorting.")
