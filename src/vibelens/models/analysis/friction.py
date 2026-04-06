"""User-centric friction analysis models.

Friction = user dissatisfaction. If the user moves on without complaint,
there is no friction — even if the agent read 20 files.

Model hierarchy:
- FrictionEvent: LLM-detected friction with computed cost
- FrictionAnalysisOutput: LLM output model (batch and synthesis)
- FrictionAnalysisResult: Final merged result across all batches
"""

from pydantic import BaseModel, Field

from vibelens.models.analysis.step_ref import StepRef
from vibelens.models.llm.inference import BackendType
from vibelens.models.trajectories.metrics import Metrics


class FrictionCost(BaseModel):
    """Computed from step span — NOT LLM-generated."""

    affected_steps: int = Field(default=0, description="Count of steps in the friction span.")
    affected_tokens: int | None = Field(
        default=None, description="Sum of step metrics tokens in span."
    )
    affected_time_seconds: int | None = Field(
        default=None, description="Timestamp delta in seconds across span."
    )


class FrictionEvent(BaseModel):
    """A single friction event detected by the LLM."""

    friction_type: str = Field(description="Kebab-case friction type from taxonomy.")
    span_ref: StepRef = Field(description="Step span where this friction occurs.")
    user_intention: str = Field(description="What the user wanted (max 15 words).")
    description: str = Field(description="Why the agent failed to satisfy the user (max 20 words).")
    severity: int = Field(description="Impact severity from 1 (minor) to 5 (critical).")
    friction_cost: FrictionCost = Field(
        default_factory=FrictionCost, description="Cost computed from step span metrics."
    )


class Mitigation(BaseModel):
    """A concrete, actionable recommendation to reduce friction."""

    action: str = Field(description="How to address the friction (max 30 words).")
    confidence: float = Field(default=0.0, description="Confidence this will help. 0.0-1.0.")


class FrictionAnalysisOutput(BaseModel):
    """LLM output model for one batch (and synthesis)."""

    title: str = Field(description="Short title for the analysis (max 10 words).")
    user_profile: str = Field(description="User's working style and project focus (max 50 words).")
    summary: str = Field(description="Narrative overview of friction (max 80 words).")
    friction_events: list[FrictionEvent] = Field(
        default_factory=list, description="0-5 friction events."
    )
    mitigations: list[Mitigation] = Field(
        default_factory=list, description="0-5 actionable recommendations."
    )


class FrictionAnalysisResult(BaseModel):
    """Complete friction analysis result merged across all batches."""

    analysis_id: str | None = Field(
        default=None, description="Persistence ID. Set when the result is saved to disk."
    )
    title: str | None = Field(default=None, description="Short title from LLM.")
    user_profile: str | None = Field(
        default=None, description="User's working style and project focus."
    )
    summary: str = Field(description="Narrative overview of friction across all sessions.")
    mitigations: list[Mitigation] = Field(
        default_factory=list, description="Actionable recommendations sorted by confidence."
    )
    friction_events: list[FrictionEvent] = Field(
        default_factory=list, description="All friction events ordered by severity descending."
    )
    session_ids: list[str] = Field(
        description="Session IDs that were successfully loaded and analyzed."
    )
    skipped_session_ids: list[str] = Field(
        default_factory=list, description="Session IDs from the request that were not found."
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal issues encountered during analysis."
    )
    backend_id: BackendType = Field(description="Inference backend used.")
    model: str = Field(description="Model identifier.")
    metrics: Metrics = Field(default_factory=Metrics, description="Token usage and cost.")
    duration_seconds: float | None = Field(
        default=None, description="Wall-clock analysis duration in seconds."
    )
    batch_count: int = Field(default=1, description="Number of LLM batches used.")
    created_at: str = Field(description="ISO timestamp of analysis completion.")
