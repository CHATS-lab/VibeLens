"""Friction analysis API schemas — request models and lightweight metadata."""

from pydantic import BaseModel, Field


class FrictionAnalysisRequest(BaseModel):
    """Request for LLM-powered friction analysis across sessions."""

    session_ids: list[str] = Field(description="Session IDs to analyze for friction events.")


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
