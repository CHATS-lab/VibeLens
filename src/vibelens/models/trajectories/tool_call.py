"""Tool call model for ATIF trajectories."""

from typing import Any

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Single tool call record (ATIF v1.6 compatible)."""

    tool_call_id: str = Field(
        default="", description="Unique tool-use identifier for pairing with observation results."
    )
    function_name: str = Field(
        description="Name of the invoked tool (e.g. 'Bash', 'Read', 'Edit').",
    )
    arguments: dict | str | None = Field(default=None, description="Arguments passed to the tool.")
    extra: dict[str, Any] | None = Field(
        default=None, description="Custom tool call metadata (e.g. summary, output_digest)."
    )
