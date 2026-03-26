"""Friction analysis API schemas — lightweight metadata for persistence."""

from pydantic import BaseModel, Field


class FrictionMeta(BaseModel):
    """Lightweight metadata for a persisted friction analysis."""

    analysis_id: str = Field(description="Unique ID for this analysis.")
    title: str | None = Field(default=None, description="Short title from synthesis.")
    session_ids: list[str] = Field(description="Sessions that were analyzed.")
    event_count: int = Field(description="Number of friction events found.")
    summary_preview: str = Field(description="First ~120 chars of the summary.")
    created_at: str = Field(description="ISO timestamp of analysis.")
    model: str = Field(description="Model used for analysis.")
    cost_usd: float | None = Field(default=None, description="Inference cost.")
    batch_count: int = Field(default=1, description="Number of LLM batches used.")
