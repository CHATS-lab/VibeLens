"""Friction analysis models for multi-session LLM-powered analysis.

Defines the complete model hierarchy from input (StepSignal) through
LLM output (FrictionLLMOutput) to the enriched service response
(FrictionAnalysisResult). See docs/spec-friction-analysis.md v0.4.
"""

from pydantic import BaseModel, Field, model_validator

from vibelens.models.analysis.step_ref import StepRef
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
    """Estimated cost of a friction event in steps, time, and tokens."""

    wasted_steps: int = Field(
        default=0,
        description="Estimated steps consumed by this friction (retries, rework, exploration).",
    )
    wasted_time_seconds: int | None = Field(
        default=None,
        description=(
            "Estimated wall-clock seconds lost. Derived from step timestamps "
            "when available, None otherwise."
        ),
    )
    wasted_tokens: int | None = Field(
        default=None,
        description=(
            "Estimated tokens spent on friction steps (input + output). "
            "Derived from step metrics when available, None otherwise."
        ),
    )


class FrictionEvent(BaseModel):
    """A specific friction instance identified by the LLM within a session.

    Fine-grained and low-level: one FrictionEvent per concrete occurrence.
    Multiple events may share the same mode if the same type of friction
    recurs across steps or sessions.
    """

    event_id: str = Field(
        description="Unique identifier for this friction event. Format: f-{sequential_number}.",
    )
    mode: str = Field(
        description=(
            "Friction mode label determined by the LLM. Descriptive kebab-case "
            "string (e.g., 'wrong-approach', 'excessive-planning')."
        ),
    )
    ref: StepRef = Field(description="Canonical location of this friction event in the session.")
    step_ids: list[str] = Field(
        description=(
            "Step IDs where this friction manifests (references Step.step_id). "
            "Single-element for point events, multi-element for spanning sequences."
        ),
    )
    severity: int = Field(
        description="Impact severity from 1 (minor inconvenience) to 5 (session blocker).",
    )
    description: str = Field(
        description="What happened and why the LLM classified this as friction.",
    )
    evidence: str = Field(
        description="Quoted or summarized evidence from the session data.",
    )
    root_cause: str = Field(
        description=(
            "Underlying cause: what triggered this friction. Distinguishes symptom from cause."
        ),
    )
    mitigations: list[str] = Field(
        description=(
            "Actionable suggestions to prevent this friction. "
            "Prefer CLAUDE.md rule additions where applicable."
        ),
    )
    estimated_cost: FrictionCost = Field(
        default_factory=FrictionCost,
        description="Estimated resources consumed by this friction event.",
    )
    related_event_ids: list[str] = Field(
        default_factory=list, description="IDs of other FrictionEvents that are causally related."
    )

    @model_validator(mode="before")
    @classmethod
    def backfill_ref(cls, data: dict) -> dict:
        """Auto-build ref from legacy session_id/step_ids/tool_call_id fields."""
        if isinstance(data, dict) and "ref" not in data and "session_id" in data:
            step_ids = data.get("step_ids", [])
            data["ref"] = {
                "session_id": data.pop("session_id"),
                "start_step_id": step_ids[0] if step_ids else "",
                "end_step_id": step_ids[-1] if len(step_ids) > 1 else None,
                "tool_call_id": data.pop("tool_call_id", None),
            }
        return data


class ClaudeMdSuggestion(BaseModel):
    """A suggested CLAUDE.md rule derived from observed friction."""

    rule: str = Field(
        description="The CLAUDE.md rule text to add.",
    )
    section: str = Field(
        description="Suggested CLAUDE.md section to place the rule.",
    )
    rationale: str = Field(
        description="Why this rule is recommended, citing observed friction events.",
    )
    source_event_ids: list[str] = Field(
        default_factory=list, description="FrictionEvent IDs that motivated this suggestion."
    )


class ModeSummary(BaseModel):
    """Aggregated statistics for one friction mode across the analysis."""

    mode: str = Field(description="Friction mode label (matches FrictionEvent.mode).")
    count: int = Field(description="Total friction events with this mode.")
    affected_sessions: int = Field(description="Number of distinct sessions containing this mode.")
    avg_severity: float = Field(description="Average severity across events of this mode.")
    total_estimated_cost: FrictionCost = Field(
        default_factory=FrictionCost,
        description="Aggregated estimated cost across all events of this mode.",
    )


class FrictionLLMOutput(BaseModel):
    """Intermediate model for raw LLM friction analysis output.

    The LLM produces events, summary, suggestions, and mode_summary.
    The service wraps this with metadata to form FrictionAnalysisResult.
    """

    events: list[FrictionEvent] = Field(
        default_factory=list,
        description="All identified friction events, ordered by session then step.",
    )
    summary: str = Field(
        description="Narrative overview of friction across analyzed sessions.",
    )
    top_mitigation: str = Field(
        description="Single highest-impact CLAUDE.md rule or workflow change.",
    )
    claude_md_suggestions: list[ClaudeMdSuggestion] = Field(
        default_factory=list,
        description="Actionable CLAUDE.md additions derived from friction patterns.",
    )
    mode_summary: list[ModeSummary] = Field(
        default_factory=list,
        description="Aggregated statistics per friction mode.",
    )


class FrictionAnalysisResult(BaseModel):
    """Complete friction analysis result with service metadata.

    Extends FrictionLLMOutput fields with session tracking, backend info,
    and cost metadata that the service adds after LLM inference.
    """

    analysis_id: str | None = Field(
        default=None,
        description="Persistence ID. Set when the result is saved to disk.",
    )
    events: list[FrictionEvent] = Field(
        default_factory=list,
        description="All identified friction events, ordered by session then step.",
    )
    summary: str = Field(
        description="Narrative overview of friction across analyzed sessions.",
    )
    top_mitigation: str = Field(
        description="Single highest-impact CLAUDE.md rule or workflow change.",
    )
    claude_md_suggestions: list[ClaudeMdSuggestion] = Field(
        default_factory=list,
        description="Actionable CLAUDE.md additions derived from friction patterns.",
    )
    mode_summary: list[ModeSummary] = Field(
        default_factory=list,
        description="Aggregated statistics per friction mode (recomputed by service).",
    )
    session_ids: list[str] = Field(
        description="Session IDs that were successfully loaded and analyzed.",
    )
    sessions_skipped: list[str] = Field(
        default_factory=list,
        description="Session IDs from the request that were not found in the store.",
    )
    backend_id: str = Field(description="Inference backend used.")
    model: str = Field(description="Model identifier.")
    cost_usd: float | None = Field(
        default=None,
        description="Inference cost in USD. None for free backends.",
    )
    computed_at: str = Field(description="ISO timestamp of analysis completion.")


class FrictionAnalysisRequest(BaseModel):
    """Request for LLM-powered friction analysis across sessions."""

    session_ids: list[str] = Field(description="Session IDs to analyze for friction events.")
