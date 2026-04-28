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
    is_skill: bool | None = Field(
        default=None,
        description=(
            "Whether this tool invocation is a Skill (a packaged prompt + "
            "reference assets) rather than a generic tool. Set by parsers "
            "whose agent exposes Skills as explicit tool calls (Claude "
            "'Skill', CodeBuddy 'Skill', Gemini 'activate_skill', "
            "OpenCode/Kilo 'skill'). Cursor and Kiro inject Skills as "
            "system-prompt context rather than tool calls, so this stays "
            "None for those agents. VibeLens extension; not part of "
            "upstream ATIF."
        ),
    )
    extra: dict[str, Any] | None = Field(
        default=None, description="Custom tool call metadata (e.g. summary, output_digest)."
    )
