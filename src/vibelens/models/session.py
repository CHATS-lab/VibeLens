"""Session-level domain models."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from vibelens.models.message import Message


class DataSourceType(StrEnum):
    """Supported data source types."""

    LOCAL = "local"
    HUGGINGFACE = "huggingface"
    MONGODB = "mongodb"
    UPLOAD = "upload"


class DataTargetType(StrEnum):
    """Supported data target types."""

    MONGODB = "mongodb"
    HUGGINGFACE = "huggingface"


class ParseDiagnostics(BaseModel):
    """Diagnostics collected during session parsing."""

    skipped_lines: int = Field(default=0, description="JSONL lines that failed JSON decode.")
    orphaned_tool_calls: int = Field(
        default=0, description="tool_use blocks with no matching tool_result."
    )
    orphaned_tool_results: int = Field(
        default=0, description="tool_result blocks with no matching tool_use."
    )
    completeness_score: float = Field(
        default=1.0, description="Quality score from 0.0 (poor) to 1.0 (perfect)."
    )


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
    diagnostics: ParseDiagnostics | None = Field(
        default=None, description="Parse quality diagnostics, if collected."
    )


MAIN_AGENT_ID = ""


class SubAgentSession(BaseModel):
    """Sub-agent conversation spawned from a parent session.

    Supports recursive nesting: a sub-agent can itself spawn further
    sub-agents, forming a cascade hierarchy. The ``spawn_index`` field
    tells the frontend exactly which parent message triggered this
    sub-agent, enabling inline expandable display.
    """

    agent_id: str = Field(
        description="Sub-agent identifier extracted from filename (e.g. 'agent-abc123')."
    )
    spawn_index: int | None = Field(
        default=None,
        description="0-based index of the parent message that spawned this sub-agent.",
    )
    spawn_tool_call_id: str = Field(
        default="",
        description="Tool call ID in the parent message that triggered this sub-agent.",
    )
    messages: list[Message] = Field(
        default_factory=list,
        description="Ordered messages in this sub-agent's conversation.",
    )
    sub_sessions: list["SubAgentSession"] = Field(
        default_factory=list,
        description="Nested sub-agent sessions spawned by this sub-agent (cascade).",
    )


SubAgentSession.model_rebuild()


class SessionDetail(BaseModel):
    """Full session data including all messages and sub-agent hierarchy.

    The ``messages`` list contains only the main session's messages.
    Sub-agent conversations are kept separate in ``sub_sessions``,
    preserving the cascade hierarchy for frontend display: the left
    panel shows only main sessions, while sub-agent messages are
    revealed via expandable dropdowns at their spawn points.
    """

    summary: SessionSummary = Field(description="Aggregated session-level summary.")
    messages: list[Message] = Field(
        default_factory=list, description="Ordered list of Message objects in the main session."
    )
    sub_sessions: list[SubAgentSession] = Field(
        default_factory=list,
        description="Sub-agent sessions spawned during this session.",
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
