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

    session_id: str
    project_id: str = ""
    project_name: str = ""
    timestamp: datetime | None = None
    duration: int = 0
    message_count: int = 0
    tool_call_count: int = 0
    models: list[str] = Field(default_factory=list)
    first_message: str = ""
    source_type: DataSourceType = DataSourceType.LOCAL
    source_name: str = ""
    source_host: str = ""


class SessionDetail(BaseModel):
    """Full session data including all messages."""

    summary: SessionSummary
    messages: list = Field(default_factory=list)


class SessionMetadata(BaseModel):
    """Aggregated metadata extracted from a message list."""

    message_count: int = 0
    tool_call_count: int = 0
    models: list[str] = Field(default_factory=list)
    first_message: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read: int = 0
    total_cache_write: int = 0
    duration: int = 0


class PushRequest(BaseModel):
    """Push request payload."""

    session_ids: list[str]
    target: DataTargetType


class PushResult(BaseModel):
    """Push operation result."""

    total: int
    uploaded: int
    skipped: int
    errors: list[dict] = Field(default_factory=list)


class PullRequest(BaseModel):
    """HuggingFace pull request payload."""

    repo_id: str
    force_refresh: bool = False


class PullResult(BaseModel):
    """Pull operation result."""

    repo_id: str
    sessions_imported: int
    messages_imported: int
    skipped: int


class RemoteSessionsQuery(BaseModel):
    """Query parameters for remote session listing."""

    project_id: str | None = None
    source_type: DataSourceType | None = None
    limit: int = 100
    offset: int = 0
