"""Creation models for the proposal and deep-generation pipeline."""

from pydantic import BaseModel, Field

from vibelens.models.enums import AgentExtensionType
from vibelens.models.llm.inference import BackendType
from vibelens.models.personalization.constants import (
    DESCRIPTION_CONFIDENCE,
    DESCRIPTION_RATIONALE,
    DESCRIPTION_TITLE,
)
from vibelens.models.session.patterns import WorkflowPattern
from vibelens.models.trajectories.final_metrics import FinalMetrics
from vibelens.models.trajectories.metrics import Metrics


class CreationProposal(BaseModel):
    """A lightweight creation proposal from the proposal pipeline.

    Produced by the proposal LLM step. The user approves proposals
    before the deep-creation step generates full file content.
    """

    element_type: AgentExtensionType = Field(description="Type of element to create.")
    element_name: str = Field(description="Proposed element name in kebab-case.")
    session_indices: list[int] = Field(
        default_factory=list, description="0-indexed session indices pointing to relevant sessions."
    )
    addressed_patterns: list[str] = Field(
        default_factory=list, description="Titles of workflow patterns this proposal addresses."
    )
    rationale: str = Field(description=DESCRIPTION_RATIONALE)
    confidence: float = Field(default=0.0, description=DESCRIPTION_CONFIDENCE)


class CreationProposalBatch(BaseModel):
    """LLM output from the proposal generation step.

    Contains lightweight proposals (name + description + rationale) without
    full file content. Deep creation produces the full content per proposal.
    """

    title: str = Field(default="", description=DESCRIPTION_TITLE)
    workflow_patterns: list[WorkflowPattern] = Field(
        default_factory=list, description="Detected workflow patterns from trajectory analysis."
    )
    proposals: list[CreationProposal] = Field(
        default_factory=list, description="Creation proposals."
    )


class CreationProposalResult(BaseModel):
    """Service result wrapping proposals with metadata."""

    proposal_id: str | None = Field(
        default=None, description="Persistence ID. Set when saved to disk."
    )
    session_ids: list[str] = Field(
        description="Session IDs that were successfully loaded and analyzed."
    )
    skipped_session_ids: list[str] = Field(
        default_factory=list, description="Session IDs that could not be loaded."
    )
    created_at: str = Field(description="ISO timestamp of analysis completion.")
    backend: BackendType = Field(description="Inference backend used.")
    model: str = Field(description="Model identifier.")
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
    proposal_batch: CreationProposalBatch = Field(
        description="LLM-generated proposal output with patterns and proposals."
    )


class PersonalizationCreation(BaseModel):
    """A fully generated element from detected workflow patterns.

    Produced by the deep-creation LLM step. Confidence is set by the service
    from the originating proposal's confidence score.
    """

    element_type: AgentExtensionType = Field(description="Type of element to create.")
    element_name: str = Field(description="Element name in kebab-case.")
    description: str = Field(
        description=(
            "Specific trigger description for YAML frontmatter. "
            "State what the element does AND when it activates. "
            "Include trigger phrases. Max 30 words."
        )
    )
    skill_md_content: str = Field(description="Full SKILL.md content including YAML frontmatter.")
    rationale: str = Field(description=DESCRIPTION_RATIONALE)
    tools_used: list[str] = Field(
        default_factory=list,
        description="Tool names referenced in the element (e.g. Read, Edit, Bash).",
    )
    addressed_patterns: list[str] = Field(
        default_factory=list, description="Titles of workflow patterns addressed by this element."
    )
    confidence: float = Field(default=0.0, description=DESCRIPTION_CONFIDENCE)
