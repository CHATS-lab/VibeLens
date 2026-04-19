"""Agent configuration model for ATIF trajectories."""

from typing import Any

from pydantic import BaseModel, Field


class Agent(BaseModel):
    """Agent configuration (ATIF v1.6 compatible).

    Core ATIF fields: name, version, model_name, tool_definitions, extra.
    """

    name: str = Field(description="Name of the agent system (e.g. 'claude', 'codex').")
    version: str | None = Field(default=None, description="Version identifier of the agent system.")
    model_name: str | None = Field(
        default=None, description="Default LLM model. Step-level model_name overrides this."
    )
    tool_definitions: list[dict[str, Any]] | None = Field(
        default=None, description="Tool/function definitions available to the agent."
    )
    extra: dict[str, Any] | None = Field(
        default=None, description="Custom agent configuration details."
    )
