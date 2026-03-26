"""User-centric friction analysis models.

Friction = user dissatisfaction. If the user moves on without complaint,
there is no friction — even if the agent read 20 files.

Model hierarchy:
- StepSignal: Input (kept for skill analysis compatibility)
- FrictionLLMEvent → FrictionEvent: LLM output → enriched with computed cost
- FrictionLLMBatchOutput: Raw output for one batch
- FrictionSynthesisOutput: LLM output from post-batch synthesis
- FrictionAnalysisResult: Final merged result across all batches
"""

from uuid import uuid4

from pydantic import BaseModel, Field

from vibelens.models.analysis.step_ref import StepRef
from vibelens.models.inference import BackendType
from vibelens.models.trajectories.step import Step


class StepSignal(BaseModel):
    """A single trajectory step prepared for LLM friction analysis.

    Clean reference into the ATIF data model. Carries the original Step
    with its tool calls and observations intact. No pre-classification
    or pre-filtering — the LLM makes all analytical decisions.
    """

    session_id: str = Field(description="Session this step belongs to.")
    project_path: str | None = Field(
        default=None, description="Project working directory from the trajectory."
    )
    step_index: int = Field(description="Zero-based position of this step in the trajectory.")
    step: Step = Field(
        description="Original ATIF Step object including tool_calls and observation."
    )

    @property
    def ref(self) -> StepRef:
        """Build a point StepRef from this signal's session and step."""
        return StepRef(session_id=self.session_id, start_step_id=self.step.step_id)


class FrictionCost(BaseModel):
    """Computed from step span — NOT LLM-generated."""

    affected_steps: int = Field(default=0, description="Count of steps in the friction span.")
    affected_tokens: int | None = Field(
        default=None, description="Sum of step metrics tokens in span. None if unavailable."
    )
    affected_time_seconds: int | None = Field(
        default=None, description="Timestamp delta in seconds across span. None if unavailable."
    )


class Mitigation(BaseModel):
    """Structured mitigation action — ready to apply."""

    action_type: str = Field(
        description=(
            "Type of mitigation: 'update_claude_md', 'write_test', 'create_skill', "
            "'update_skill', 'add_linter_rule', 'update_workflow'."
        ),
    )
    target: str = Field(
        description="CLAUDE.md section, test file path, skill name, or workflow target.",
    )
    content: str = Field(
        description="Exact text to add or change — ready to apply.",
    )


class FrictionLLMEvent(BaseModel):
    """What the LLM outputs for a single friction event. No cost or ID fields."""

    friction_type: str = Field(
        description="Kebab-case friction type from taxonomy.",
    )
    span_ref: StepRef = Field(
        description="Step span where this friction occurs.",
    )
    severity: int = Field(
        description="Impact severity from 1 (minor) to 5 (critical).",
    )
    user_intention: str = Field(
        description="What the user fundamentally wanted.",
    )
    friction_detail: str = Field(
        description="Why the agent failed to satisfy the user (1 sentence or empty).",
    )
    claude_helpfulness: int = Field(
        description="1=unhelpful, 2=slightly, 3=moderately, 4=very, 5=essential.",
    )
    mitigations: list[Mitigation] = Field(
        default_factory=list, description="Structured mitigation actions."
    )


class FrictionEvent(FrictionLLMEvent):
    """FrictionLLMEvent enriched with server-generated ID and computed cost."""

    friction_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Server-generated UUID for this friction event.",
    )
    estimated_cost: FrictionCost = Field(
        default_factory=FrictionCost, description="Cost computed from step span metrics."
    )


class FrictionLLMBatchOutput(BaseModel):
    """Raw LLM output for one batch of sessions."""

    events: list[FrictionLLMEvent] = Field(
        default_factory=list, description="Friction events identified in this batch."
    )
    summary: str = Field(description="Narrative overview of friction in this batch.")
    top_mitigation: Mitigation | None = Field(
        default=None, description="Single highest-impact mitigation across the batch."
    )


class FrictionTypeDescription(BaseModel):
    """LLM-generated description for a single friction type."""

    friction_type: str = Field(description="Kebab-case friction type label matching batch events.")
    description: str = Field(
        description="1-2 sentence explanation of the friction pattern observed."
    )


class FrictionSynthesisOutput(BaseModel):
    """LLM output from post-batch synthesis — cohesive narrative across all sessions."""

    title: str = Field(description="Short title for the analysis (max 10 words).")
    summary: str = Field(
        description="High-level narrative overview (max 80 words)."
    )
    type_descriptions: list[FrictionTypeDescription] = Field(
        default_factory=list, description="One description per friction type found."
    )
    cross_session_patterns: list[str] = Field(
        default_factory=list, description="0-3 cross-session observations."
    )
    mitigations: list[Mitigation] = Field(
        default_factory=list, description="0-3 highest-impact actionable recommendations."
    )


class TypeSummary(BaseModel):
    """Aggregated statistics per friction_type."""

    friction_type: str = Field(
        description="Friction type label (matches FrictionEvent.friction_type)."
    )
    count: int = Field(description="Total friction events of this type.")
    affected_sessions: int = Field(description="Number of distinct sessions containing this type.")
    avg_severity: float = Field(description="Average severity across events of this type.")
    total_estimated_cost: FrictionCost = Field(
        default_factory=FrictionCost, description="Aggregated cost across all events of this type."
    )
    description: str | None = Field(
        default=None, description="LLM-generated description of this friction pattern."
    )


class FrictionAnalysisResult(BaseModel):
    """Complete friction analysis result merged across all batches."""

    analysis_id: str | None = Field(
        default=None, description="Persistence ID. Set when the result is saved to disk."
    )
    title: str | None = Field(
        default=None, description="Short title from synthesis LLM call."
    )
    model: str = Field(description="Model identifier.")
    created_at: str = Field(description="ISO timestamp of analysis completion.")
    backend_id: BackendType = Field(description="Inference backend used.")
    session_ids: list[str] = Field(
        description="Session IDs that were successfully loaded and analyzed."
    )
    batch_count: int = Field(default=1, description="Number of LLM batches used for this analysis.")
    summary: str = Field(description="Narrative overview of friction across all sessions.")
    type_summary: list[TypeSummary] = Field(
        default_factory=list, description="Aggregated statistics per friction type."
    )
    top_mitigation: Mitigation | None = Field(
        default=None, description="Single highest-impact mitigation across all batches."
    )
    cross_batch_patterns: list[str] = Field(
        default_factory=list, description="Aggregate observations spanning multiple batches."
    )
    sessions_skipped: list[str] = Field(
        default_factory=list, description="Session IDs from the request that were not found."
    )
    cost_usd: float | None = Field(
        default=None, description="Total inference cost in USD across all batches."
    )
    events: list[FrictionEvent] = Field(
        default_factory=list, description="All friction events ordered by severity descending."
    )


class FrictionAnalysisRequest(BaseModel):
    """Request for LLM-powered friction analysis across sessions."""

    session_ids: list[str] = Field(description="Session IDs to analyze for friction events.")
