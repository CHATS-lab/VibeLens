"""Tool call model for ATIF trajectories."""

from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Single tool call record (ATIF v1.6 compatible)."""

    tool_call_id: str = Field(
        default="", description="Unique tool-use identifier for pairing with observation results."
    )
    function_name: str = Field(
        description="Name of the invoked tool (e.g. 'Bash', 'Read', 'Edit').",
    )
    arguments: Optional[Union[dict, str]] = Field(
        default=None, description="Arguments passed to the tool."
    )
    extra: Optional[dict[str, Any]] = Field(
        default=None, description="Custom tool call metadata (e.g. summary, output_digest)."
    )
