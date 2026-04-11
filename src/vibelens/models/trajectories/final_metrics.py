"""Final metrics model for ATIF trajectories."""

from typing import Any

from pydantic import BaseModel, Field


class FinalMetrics(BaseModel):
    """Aggregate statistics for the entire trajectory (ATIF v1.6 compatible superset).

    Core ATIF fields: total_prompt_tokens, total_completion_tokens,
    total_cost_usd, total_steps, extra.
    VibeLens extensions: tool_call_count, duration, total_cache_write, total_cache_read.
    """

    duration: int = Field(
        default=0, description="[VibeLens] Session wall-clock duration in seconds."
    )
    total_steps: int | None = Field(
        default=None, ge=0, description="Total number of steps in the trajectory."
    )
    tool_call_count: int = Field(
        default=0, description="[VibeLens] Total tool invocations across all steps."
    )
    total_prompt_tokens: int | None = Field(
        default=None,
        description="Sum of all prompt tokens across all steps, including cached tokens.",
    )
    total_completion_tokens: int | None = Field(
        default=None, description="Sum of all completion tokens across all steps."
    )
    total_cache_read: int = Field(
        default=0,
        description="[VibeLens] Total tokens read from the prompt cache (Anthropic-specific).",
    )
    total_cache_write: int = Field(
        default=0,
        description="[VibeLens] Total tokens written into the prompt cache (Anthropic-specific).",
    )
    total_cost_usd: float | None = Field(
        default=None,
        description="Total monetary cost for the entire trajectory including subagents.",
    )
    extra: dict[str, Any] | None = Field(default=None, description="Custom aggregate metrics.")
