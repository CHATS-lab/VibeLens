"""Message-level models."""

from datetime import datetime

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Single tool call record."""

    id: str = Field(
        default="", description="Unique tool-use identifier for pairing with tool results."
    )
    name: str = Field(description="Name of the invoked tool (e.g. 'Bash', 'Read', 'Edit').")
    input: dict | str | None = Field(default=None, description="Arguments passed to the tool.")
    output: str | None = Field(
        default=None, description="Raw output returned by the tool execution."
    )
    is_error: bool = Field(
        default=False, description="Whether the tool execution resulted in an error."
    )
    summary: str = Field(
        default="", description="Short human-readable summary (e.g. 'src/main.py', 'ls -la')."
    )
    category: str = Field(
        default="",
        description="Semantic category: file_read, file_write, shell, search, web, agent, other.",
    )
    output_digest: str = Field(default="", description="One-line digest of the tool output signal.")


class TokenUsage(BaseModel):
    """Token usage statistics."""

    input_tokens: int = Field(
        default=0, description="Number of input tokens consumed in this turn."
    )
    output_tokens: int = Field(
        default=0, description="Number of output tokens generated in this turn."
    )
    cache_creation_tokens: int = Field(
        default=0, description="Tokens written into the prompt cache."
    )
    cache_read_tokens: int = Field(default=0, description="Tokens served from the prompt cache.")


class ContentBlock(BaseModel):
    """Claude API content block."""

    type: str = Field(description="Block type: 'text', 'thinking', 'tool_use', or 'tool_result'.")
    text: str | None = Field(default=None, description="Text content for 'text' type blocks.")
    thinking: str | None = Field(
        default=None, description="Extended thinking content for 'thinking' type blocks."
    )
    id: str | None = Field(default=None, description="Tool-use identifier for 'tool_use' blocks.")
    name: str | None = Field(default=None, description="Tool name for 'tool_use' blocks.")
    input: dict | str | None = Field(
        default=None, description="Tool arguments for 'tool_use' blocks."
    )
    tool_use_id: str | None = Field(
        default=None, description="Matching tool-use id for 'tool_result' blocks."
    )
    content: str | list | None = Field(
        default=None, description="Result payload for 'tool_result' blocks."
    )
    is_error: bool | None = Field(
        default=None, description="Whether the tool result represents an error."
    )


class Message(BaseModel):
    """Unified message model compatible with all data sources."""

    uuid: str = Field(description="Unique message identifier (UUID format).")
    session_id: str = Field(description="Session this message belongs to.")
    parent_uuid: str = Field(
        default="", description="UUID of the parent message for conversation threading."
    )
    role: str = Field(description="Message author role: 'user' or 'assistant'.")
    type: str = Field(description="Message type matching the role (e.g. 'user', 'assistant').")
    content: str | list[ContentBlock] = Field(
        default="", description="Plain text or structured content blocks."
    )
    thinking: str | None = Field(
        default=None, description="Top-level extended thinking text, if present."
    )
    model: str = Field(default="", description="LLM model identifier that generated this message.")
    timestamp: datetime | None = Field(default=None, description="When the message was created.")
    is_sidechain: bool = Field(
        default=False, description="Whether this message is part of a sidechain (sub-agent)."
    )
    usage: TokenUsage | None = Field(
        default=None, description="Token usage statistics for this turn."
    )
    tool_calls: list[ToolCall] = Field(
        default_factory=list, description="Tool invocations extracted from this message."
    )


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
