"""Friction analysis API schemas — lightweight metadata for persistence."""

from pydantic import BaseModel, Field


class FrictionEstimateResponse(BaseModel):
    """Pre-flight cost estimate returned before running analysis."""

    model: str = Field(description="Model that will be used for analysis.")
    batch_count: int = Field(description="Number of LLM batches planned.")
    total_input_tokens: int = Field(description="Total input tokens across all batches.")
    total_output_tokens_budget: int = Field(description="Max output token budget.")
    cost_min_usd: float = Field(description="Optimistic cost estimate in USD.")
    cost_max_usd: float = Field(description="Pessimistic cost estimate in USD.")
    pricing_found: bool = Field(description="Whether model pricing was found.")
    formatted_cost: str = Field(description="Human-readable cost range string.")


class FrictionMeta(BaseModel):
    """Lightweight metadata for a persisted friction analysis."""

    analysis_id: str = Field(description="Unique ID for this analysis.")
    title: str | None = Field(default=None, description="Short title from synthesis.")
    session_ids: list[str] = Field(description="Sessions that were analyzed.")
    created_at: str = Field(description="ISO timestamp of analysis.")
    model: str = Field(description="Model used for analysis.")
    cost_usd: float | None = Field(default=None, description="Inference cost.")
    batch_count: int = Field(default=1, description="Number of LLM batches used.")
    duration_seconds: float | None = Field(
        default=None, description="Wall-clock analysis duration in seconds."
    )
