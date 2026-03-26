"""User-centric friction analysis models.

Friction = user dissatisfaction. If the user moves on without complaint,
there is no friction — even if the agent read 20 files.

Model hierarchy:
- StepSignal: Input (kept for skill analysis compatibility)
- FrictionLLMEvent → FrictionEvent: LLM output → enriched with computed cost
- FrictionLLMBatchOutput: Raw output for one batch
- FrictionAnalysisResult: Final merged result across all batches
"""

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
    step_index: int = Field(
        description="Zero-based position of this step in the trajectory.",
    )
    step: Step = Field(
        description="Original ATIF Step object including tool_calls and observation.",
    )

    @property
    def ref(self) -> StepRef:
        """Build a point StepRef from this signal's session and step."""
        return StepRef(session_id=self.session_id, start_step_id=self.step.step_id)


class FrictionCost(BaseModel):
    """Computed from step span — NOT LLM-generated."""

    affected_steps: int = Field(
        default=0,
        description="Count of steps in the friction span.",
    )
    affected_tokens: int | None = Field(
        default=None,
        description="Sum of step metrics tokens in span. None if unavailable.",
    )
    affected_time_seconds: int | None = Field(
        default=None,
        description="Timestamp delta in seconds across span. None if unavailable.",
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
    """What the LLM outputs for a single friction event. No cost fields."""

    friction_id: str = Field(
        description="Sequential identifier (friction-001, friction-002, ...).",
    )
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
        default_factory=list,
        description="Structured mitigation actions.",
    )
    related_friction_ids: list[str] = Field(
        default_factory=list,
        description="IDs of causally related friction events.",
    )


class FrictionEvent(FrictionLLMEvent):
    """FrictionLLMEvent enriched with computed cost (post-inference)."""

    estimated_cost: FrictionCost = Field(
        default_factory=FrictionCost,
        description="Cost computed from step span metrics.",
    )


class FrictionLLMBatchOutput(BaseModel):
    """Raw LLM output for one batch of sessions."""

    events: list[FrictionLLMEvent] = Field(
        default_factory=list,
        description="Friction events identified in this batch.",
    )
    summary: str = Field(
        description="Narrative overview of friction in this batch.",
    )
    top_mitigation: Mitigation | None = Field(
        default=None,
        description="Single highest-impact mitigation across the batch.",
    )


class TypeSummary(BaseModel):
    """Aggregated statistics per friction_type. Replaces ModeSummary."""

    friction_type: str = Field(
        description="Friction type label (matches FrictionEvent.friction_type).",
    )
    count: int = Field(description="Total friction events of this type.")
    affected_sessions: int = Field(
        description="Number of distinct sessions containing this type.",
    )
    avg_severity: float = Field(
        description="Average severity across events of this type.",
    )
    total_estimated_cost: FrictionCost = Field(
        default_factory=FrictionCost,
        description="Aggregated cost across all events of this type.",
    )


class FrictionAnalysisResult(BaseModel):
    """Complete friction analysis result merged across all batches."""

    analysis_id: str | None = Field(
        default=None,
        description="Persistence ID. Set when the result is saved to disk.",
    )
    events: list[FrictionEvent] = Field(
        default_factory=list,
        description="All friction events ordered by severity descending.",
    )
    summary: str = Field(
        description="Narrative overview of friction across all sessions.",
    )
    top_mitigation: Mitigation | None = Field(
        default=None,
        description="Single highest-impact mitigation across all batches.",
    )
    type_summary: list[TypeSummary] = Field(
        default_factory=list,
        description="Aggregated statistics per friction type.",
    )
    session_ids: list[str] = Field(
        description="Session IDs that were successfully loaded and analyzed.",
    )
    sessions_skipped: list[str] = Field(
        default_factory=list,
        description="Session IDs from the request that were not found.",
    )
    batch_count: int = Field(
        default=1,
        description="Number of LLM batches used for this analysis.",
    )
    backend_id: BackendType = Field(description="Inference backend used.")
    model: str = Field(description="Model identifier.")
    cost_usd: float | None = Field(
        default=None,
        description="Total inference cost in USD across all batches.",
    )
    created_at: str = Field(description="ISO timestamp of analysis completion.")


class FrictionAnalysisRequest(BaseModel):
    """Request for LLM-powered friction analysis across sessions."""

    session_ids: list[str] = Field(description="Session IDs to analyze for friction events.")
