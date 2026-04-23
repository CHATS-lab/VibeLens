"""Final metrics model for ATIF trajectories."""

from typing import Any

from pydantic import BaseModel, Field


class DailyBucket(BaseModel):
    """Per-local-day slice of session activity.

    Populated by ingest from per-step timestamps so the dashboard fast
    path can split a cross-day session's messages/tokens/cost across
    the days its steps actually landed on, without re-parsing the full
    trajectory. Date keys are ``YYYY-MM-DD`` in the ingest host's local
    timezone — VibeLens is local-first, so ingest and viewer share tz.
    """

    messages: int = Field(default=0, description="User+agent step count landing on this day.")
    tokens: int = Field(default=0, description="prompt+completion tokens landing on this day.")
    cost_usd: float = Field(default=0.0, description="Sum of per-step cost landing on this day.")


class FinalMetrics(BaseModel):
    """Aggregate statistics for the entire trajectory (ATIF v1.6 compatible superset).

    Core ATIF fields: total_prompt_tokens, total_completion_tokens,
    total_cost_usd, total_steps, extra.
    VibeLens extensions: tool_call_count, duration, total_cache_write,
    total_cache_read, daily_breakdown.
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
    daily_breakdown: dict[str, DailyBucket] | None = Field(
        default=None,
        description=(
            "[VibeLens] Per-local-day slice of messages/tokens/cost keyed by YYYY-MM-DD "
            "(ingest-host local tz). None when no step timestamps were usable. "
            "Sums over all buckets equal the session-level totals."
        ),
    )
    extra: dict[str, Any] | None = Field(default=None, description="Custom aggregate metrics.")
