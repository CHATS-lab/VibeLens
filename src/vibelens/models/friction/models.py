"""User-centric friction analysis models.

Friction = user dissatisfaction. If the user moves on without complaint,
there is no friction — even if the agent read 20 files.

Model hierarchy:
- FrictionType: LLM-detected friction category with computed cost
- FrictionAnalysisOutput: LLM output model (batch and synthesis)
- FrictionAnalysisResult: Final merged result across all batches
"""

from pydantic import BaseModel, Field

from vibelens.models.llm.inference import BackendType
from vibelens.models.step_ref import StepRef
from vibelens.models.trajectories.final_metrics import FinalMetrics
from vibelens.models.trajectories.metrics import Metrics


class FrictionCost(BaseModel):
    """Computed from example_refs spans — NOT LLM-generated."""

    affected_steps: int = Field(default=0, description="Total steps across all example spans.")
    affected_tokens: int | None = Field(
        default=None, description="Sum of step metrics tokens across all spans."
    )
    affected_time_seconds: int | None = Field(
        default=None, description="Sum of timestamp deltas across all spans."
    )


class FrictionType(BaseModel):
    """A friction category detected by the LLM, with one or more examples."""

    type_name: str = Field(
        description="Plain-language kebab-case label (e.g. 'changed-wrong-files')."
    )
    description: str = Field(
        description="What the user wanted and how the agent performed differently (max 30 words)."
    )
    severity: int = Field(description="Impact severity from 1 (minor) to 5 (critical).")
    example_refs: list[StepRef] = Field(
        default_factory=list, description="Step spans where this friction was observed."
    )
    friction_cost: FrictionCost = Field(
        default_factory=FrictionCost, description="Aggregate cost computed from example_refs."
    )


class Mitigation(BaseModel):
    """A concrete, actionable recommendation to reduce friction.

    Two-audience design: ``title`` is human-facing (what the user sees when
    skimming the report); ``action`` is agent-directed (a rule the user can
    paste verbatim into CLAUDE.md or AGENT.md to change agent behavior).
    """

    title: str = Field(
        description=(
            "Short human-facing heading naming the fix. Non-technical users "
            "must grasp what this mitigation does from the title alone. Max 8 words."
        )
    )
    addressed_friction_types: list[str] = Field(
        default_factory=list,
        description=(
            "Friction type_name values this mitigation addresses (e.g. 'changed-wrong-files')."
        ),
    )
    action: str = Field(
        description=(
            "Agent-directed instruction written as an imperative rule, ready for the "
            "user to paste into CLAUDE.md or AGENT.md. Speak to the agent ('Do X', "
            "'Before Y, check Z'), not to the user. Self-contained: the rule must "
            "make sense without the surrounding report context. Max 30 words."
        )
    )
    rationale: str = Field(
        description=(
            "One sentence (max 15 words), then 1-2 bullets "
            "starting with '\\n- ' (max 10 words each). Plain language, no jargon."
        )
    )
    confidence: float = Field(default=0.0, description="Confidence this will help. 0.0-1.0.")


class FrictionAnalysisOutput(BaseModel):
    """LLM output model for one batch (and synthesis)."""

    title: str = Field(
        description=(
            "Human-facing headline naming the dominant friction theme. A non-technical "
            "user skimming only this title must grasp the main finding. Max 10 words."
        )
    )
    friction_types: list[FrictionType] = Field(
        default_factory=list, description="Friction type categories."
    )
    mitigations: list[Mitigation] = Field(
        default_factory=list, description="Actionable recommendations."
    )


class FrictionAnalysisResult(BaseModel):
    """Complete friction analysis result merged across all batches."""

    id: str = Field(default="", description="Persistence ID. Set when the result is saved to disk.")
    session_ids: list[str] = Field(
        description="Session IDs that were successfully loaded and analyzed."
    )
    skipped_session_ids: list[str] = Field(
        default_factory=list, description="Session IDs from the request that were not found."
    )
    title: str | None = Field(
        default=None,
        description=(
            "Human-facing headline naming the dominant friction theme. A non-technical "
            "user skimming only this title must grasp the main finding. Max 10 words."
        ),
    )
    mitigations: list[Mitigation] = Field(
        default_factory=list, description="Actionable recommendations sorted by confidence."
    )
    friction_types: list[FrictionType] = Field(
        default_factory=list, description="Friction categories ordered by severity descending."
    )
    backend: BackendType = Field(description="Inference backend used.")
    model: str = Field(description="Model identifier.")
    created_at: str = Field(description="ISO timestamp of analysis completion.")
    batch_count: int = Field(default=1, description="Number of LLM batches used.")
    batch_metrics: list[Metrics] = Field(
        default_factory=list, description="Per-batch token usage and cost entries."
    )
    final_metrics: FinalMetrics = Field(
        default_factory=FinalMetrics, description="Aggregate cost and token totals."
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal issues encountered during analysis."
    )
    is_example: bool = Field(
        default=False, description="Whether this is a bundled example analysis."
    )
