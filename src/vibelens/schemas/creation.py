"""Creation analysis API schemas — request models and lightweight metadata."""

from pydantic import BaseModel, Field


class CreationAnalysisRequest(BaseModel):
    """Request body for running a creation analysis across sessions."""

    session_ids: list[str] = Field(description="Session IDs to analyze.")


class CreationAnalysisMeta(BaseModel):
    """Lightweight metadata for a persisted creation analysis."""

    analysis_id: str = Field(description="Unique ID for this analysis.")
    title: str = Field(default="", description="LLM-generated analysis title.")
    session_ids: list[str] = Field(description="Sessions that were analyzed.")
    created_at: str = Field(description="ISO timestamp of analysis.")
    model: str = Field(description="Model used for analysis.")
    cost_usd: float | None = Field(default=None, description="Inference cost in USD.")
    duration_seconds: float | None = Field(
        default=None, description="Wall-clock analysis duration in seconds."
    )
    is_example: bool = Field(
        default=False, description="Whether this is a bundled example analysis."
    )
