"""Session-related request and response models."""

from pydantic import BaseModel, Field

from vibelens.models.enums import DataSourceType


class DownloadRequest(BaseModel):
    """Batch download request payload."""

    session_ids: list[str] = Field(description="Session IDs to export as a zip archive.")


class RemoteSessionsQuery(BaseModel):
    """Query parameters for remote session listing."""

    project_id: str | None = Field(
        default=None, description="Filter sessions by project identifier."
    )
    source_type: DataSourceType | None = Field(
        default=None, description="Filter sessions by data source type."
    )
    limit: int = Field(default=100, description="Maximum number of sessions to return.")
    offset: int = Field(default=0, description="Number of sessions to skip for pagination.")


class DonateRequest(BaseModel):
    """Donation request payload."""

    session_ids: list[str] = Field(description="Session IDs to donate.")


class DonateResult(BaseModel):
    """Donation operation result."""

    total: int = Field(description="Total number of sessions in the request.")
    donated: int = Field(description="Number of sessions successfully donated.")
    errors: list[dict] = Field(
        default_factory=list, description="Per-session error details for failed donations."
    )
