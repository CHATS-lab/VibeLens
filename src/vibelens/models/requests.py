"""API request and response models for data transfer operations."""

from pydantic import BaseModel, Field

from vibelens.models.session import DataSourceType, DataTargetType


class PushRequest(BaseModel):
    """Push request payload."""

    session_ids: list[str] = Field(description="Session IDs to upload to the target.")
    target: DataTargetType = Field(description="Destination data store for the push operation.")


class PushResult(BaseModel):
    """Push operation result."""

    total: int = Field(description="Total number of sessions in the push request.")
    uploaded: int = Field(description="Number of sessions successfully uploaded.")
    skipped: int = Field(description="Number of sessions skipped (already exist or filtered).")
    errors: list[dict] = Field(
        default_factory=list, description="Per-session error details for failed uploads."
    )


class PullRequest(BaseModel):
    """HuggingFace pull request payload."""

    repo_id: str = Field(
        description="HuggingFace repository identifier (e.g. 'org/dataset-name')."
    )
    force_refresh: bool = Field(
        default=False, description="Re-download all sessions even if already cached."
    )


class PullResult(BaseModel):
    """Pull operation result."""

    repo_id: str = Field(description="HuggingFace repository that was pulled from.")
    sessions_imported: int = Field(description="Number of new sessions imported.")
    messages_imported: int = Field(description="Total messages imported across all sessions.")
    skipped: int = Field(description="Number of sessions skipped (already present locally).")


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
