"""LLM-generated insight models for session analysis."""

from enum import StrEnum

from pydantic import BaseModel, Field


class InsightCategory(StrEnum):
    """Category of an insight item detected in a session."""

    ACCOMPLISHMENT = "accomplishment"
    MILESTONE = "milestone"
    EFFICIENCY = "efficiency"
    ERROR_LOOP = "error_loop"
    WASTED_EFFORT = "wasted_effort"
    MISUNDERSTANDING = "misunderstanding"
    RECOVERY = "recovery"
    TOOL_MISUSE = "tool_misuse"


class InsightItem(BaseModel):
    """Single insight detected in a session."""

    category: InsightCategory = Field(description="Type of insight.")
    title: str = Field(description="Short human-readable title.")
    description: str = Field(description="Detailed explanation of the insight.")
    step_range: list[int] = Field(
        description="Start and end step indices (inclusive) where this insight occurs."
    )
    severity: int = Field(description="Severity level from 1 (minor) to 5 (critical).")
    evidence: str = Field(description="Quoted or summarized evidence from the session data.")


class SessionHighlights(BaseModel):
    """Key accomplishments and notable events in a session."""

    summary: str = Field(description="One-paragraph narrative summary of the session.")
    highlights: list[InsightItem] = Field(
        default_factory=list, description="Notable events and accomplishments."
    )
    effectiveness_score: int = Field(
        description="Overall session effectiveness from 1 (poor) to 10 (excellent)."
    )


class FrictionReport(BaseModel):
    """Friction points and wasted effort detected in a session."""

    summary: str = Field(description="One-paragraph summary of friction and inefficiencies.")
    friction_points: list[InsightItem] = Field(
        default_factory=list, description="Detected friction points and their severity."
    )
    wasted_steps: int = Field(
        default=0, description="Estimated number of steps that did not contribute to progress."
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Actionable recommendations to reduce friction."
    )


class InsightReport(BaseModel):
    """Combined LLM-generated analysis result for a session."""

    session_id: str = Field(description="Session this report covers.")
    highlights: SessionHighlights | None = Field(
        default=None, description="Session highlights analysis (None if not requested)."
    )
    friction: FrictionReport | None = Field(
        default=None, description="Friction analysis (None if not requested)."
    )
    backend_id: str = Field(description="Inference backend that generated this report.")
    model: str = Field(description="Model used for generation.")
    cost_usd: float | None = Field(
        default=None,
        description="Total inference cost in USD. None for free backends.",
    )
    computed_at: str = Field(description="ISO 8601 timestamp when the report was generated.")
