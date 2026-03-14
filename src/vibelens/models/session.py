"""Session-level models and request/response types."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class DataSourceType(str, Enum):
    """Supported data source types."""

    LOCAL = "local"
    HUGGINGFACE = "huggingface"
    MONGODB = "mongodb"


class DataTargetType(str, Enum):
    """Supported data target types."""

    MONGODB = "mongodb"
    HUGGINGFACE = "huggingface"


class SessionSummary(BaseModel):
    """Session summary for list display."""

    session_id: str = Field(description="Unique identifier for the session (UUID format).")
    project_id: str = Field(
        default="", description="Encoded project identifier derived from the filesystem path."
    )
    project_name: str = Field(
        default="", description="Human-readable project name extracted from the project path."
    )
    timestamp: datetime | None = Field(
        default=None, description="Session start time as an ISO-8601 datetime."
    )
    duration: int = Field(default=0, description="Total session wall-clock duration in seconds.")
    message_count: int = Field(
        default=0, description="Number of user and assistant messages in the session."
    )
    tool_call_count: int = Field(
        default=0, description="Number of tool invocations made by the assistant."
    )
    models: list[str] = Field(
        default_factory=list, description="LLM model identifiers used during the session."
    )
    first_message: str = Field(
        default="", description="Truncated text of the first user message for preview."
    )
    source_type: DataSourceType = Field(
        default=DataSourceType.LOCAL, description="Origin of the session data."
    )
    source_name: str = Field(
        default="", description="Name of the data source (e.g. HuggingFace repo id)."
    )
    source_host: str = Field(default="", description="Hostname or URL of the remote data source.")


class SessionDetail(BaseModel):
    """Full session data including all messages."""

    summary: SessionSummary = Field(description="Aggregated session-level summary.")
    messages: list = Field(
        default_factory=list, description="Ordered list of Message objects in the session."
    )


class SessionMetadata(BaseModel):
    """Aggregated metadata extracted from a message list."""

    message_count: int = Field(default=0, description="Number of user and assistant messages.")
    tool_call_count: int = Field(
        default=0, description="Total tool invocations across all messages."
    )
    models: list[str] = Field(
        default_factory=list, description="Distinct LLM model identifiers observed."
    )
    first_message: str = Field(default="", description="Truncated first user message for display.")
    total_input_tokens: int = Field(
        default=0, description="Sum of input tokens consumed across all turns."
    )
    total_output_tokens: int = Field(
        default=0, description="Sum of output tokens generated across all turns."
    )
    total_cache_read: int = Field(
        default=0, description="Total tokens served from the prompt cache."
    )
    total_cache_write: int = Field(
        default=0, description="Total tokens written into the prompt cache."
    )
    duration: int = Field(default=0, description="Session wall-clock duration in seconds.")


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

    repo_id: str = Field(description="HuggingFace repository identifier (e.g. 'org/dataset-name').")
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
