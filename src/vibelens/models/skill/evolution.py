"""Evolution-mode LLM output models."""

from pydantic import BaseModel, Field

from vibelens.models.llm.inference import BackendType
from vibelens.models.skill.patterns import WorkflowPattern
from vibelens.models.trajectories.metrics import Metrics


class SkillEvolutionProposal(BaseModel):
    """A lightweight evolution proposal before deep editing."""

    skill_name: str = Field(description="Existing skill to evolve.")
    rationale: str = Field(description="Why this skill should be evolved.")
    suggested_changes: str = Field(description="High-level description of proposed changes.")
    addressed_patterns: list[str] = Field(
        default_factory=list,
        description="Titles of workflow patterns this proposal addresses.",
    )
    relevant_session_indices: list[int] = Field(
        default_factory=list,
        description="0-indexed session indices pointing to relevant sessions.",
    )
    confidence: float = Field(
        default=0.0, description="Confidence that this evolution is needed. 0.0-1.0."
    )


class SkillEvolutionProposalOutput(BaseModel):
    """LLM output from the evolution proposal step."""

    title: str = Field(
        default="", description="Concise 5-10 word title summarizing the analysis findings."
    )
    user_profile: str = Field(
        default="",
        description=(
            "2-3 sentence description of the user's working style and project focus. "
            "Under 50 words."
        ),
    )
    workflow_patterns: list[WorkflowPattern] = Field(
        default_factory=list, description="Detected workflow patterns from trajectory analysis."
    )
    summary: str = Field(
        description=(
            "Concise analysis overview for readers of all expertise levels. Under 100 words."
        )
    )
    proposals: list[SkillEvolutionProposal] = Field(
        default_factory=list, description="Evolution proposals for existing skills."
    )


class SkillEdit(BaseModel):
    """A single edit to an existing skill definition.

    Uses old_string/new_string like the Edit tool:
    - Replace: old_string="original text", new_string="new text"
    - Delete: old_string="text to remove", new_string=""
    - Add/append: old_string="" (empty), new_string="text to add"
    """

    old_string: str = Field(description="Text to find in the skill. Empty string for append.")
    new_string: str = Field(description="Replacement text. Empty string for deletion.")
    replace_all: bool = Field(default=False, description="Replace all occurrences if True.")


class SkillEvolutionProposalResult(BaseModel):
    """Service result wrapping evolution proposals with metadata."""

    proposal_id: str | None = Field(
        default=None, description="Persistence ID. Set when saved to disk."
    )
    session_ids: list[str] = Field(
        description="Session IDs that were successfully loaded and analyzed."
    )
    skipped_session_ids: list[str] = Field(
        default_factory=list, description="Session IDs that could not be loaded."
    )
    backend_id: BackendType = Field(description="Inference backend used.")
    created_at: str = Field(description="ISO timestamp of analysis completion.")
    model: str = Field(description="Model identifier.")
    metrics: Metrics = Field(
        default_factory=Metrics, description="Token usage and cost from the inference step."
    )
    duration_seconds: float | None = Field(
        default=None, description="Wall-clock analysis duration in seconds."
    )
    batch_count: int = Field(default=1, description="Number of LLM batches used.")
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal issues encountered during analysis."
    )
    proposal_output: SkillEvolutionProposalOutput = Field(
        description="LLM-generated proposal output with patterns and proposals."
    )


class SkillEvolution(BaseModel):
    """A suggested improvement to an existing installed skill.

    Produced by the deep-edit LLM step. Confidence is set by the service
    from the originating proposal's confidence score.
    """

    skill_name: str = Field(description="Name of the existing skill to evolve.")
    edits: list[SkillEdit] = Field(description="Ordered list of granular edits to apply.")
    rationale: str = Field(description="Why these edits improve the skill.")
    confidence: float = Field(
        default=0.0,
        description=(
            "Confidence score 0-1 for the evolution suggestion. 0.8+ = strong, 0.5-0.8 = moderate."
        ),
    )
