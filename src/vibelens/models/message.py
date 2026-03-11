"""Message-level models."""

from datetime import datetime

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Single tool call record."""

    id: str = ""
    name: str
    input: dict | str | None = None
    output: str | None = None
    is_error: bool = False


class TokenUsage(BaseModel):
    """Token usage statistics."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0


class ContentBlock(BaseModel):
    """Claude API content block."""

    type: str
    text: str | None = None
    thinking: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict | str | None = None
    tool_use_id: str | None = None
    content: str | list | None = None
    is_error: bool | None = None


class Message(BaseModel):
    """Unified message model compatible with all data sources."""

    uuid: str
    session_id: str
    parent_uuid: str = ""
    role: str
    type: str
    content: str | list[ContentBlock] = ""
    thinking: str | None = None
    model: str = ""
    timestamp: datetime | None = None
    is_sidechain: bool = False
    usage: TokenUsage | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
