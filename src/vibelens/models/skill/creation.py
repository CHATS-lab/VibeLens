"""Creation-mode LLM output and service result models."""

from pydantic import BaseModel, Field

from vibelens.models.llm.inference import BackendType
from vibelens.models.skill.patterns import WorkflowPattern
from vibelens.models.trajectories.metrics import Metrics


class SkillCreationProposal(BaseModel):
    """A lightweight skill proposal from the proposal pipeline."""

    skill_name: str = Field(description="Proposed skill name in kebab-case.")
    description: str = Field(
        description=(
            "Specific trigger description for YAML frontmatter. "
            "State what the skill does AND when it activates. "
            "Include trigger phrases the user would say. Max 30 words."
        )
    )
    rationale: str = Field(
        description=(
            "One sentence (max 15 words), then 1-2 bullets "
            "starting with '\\n- ' (max 10 words each). Plain language, no jargon."
        )
    )
    addressed_patterns: list[str] = Field(
        default_factory=list,
        description="Titles of workflow patterns this proposal addresses.",
    )
    relevant_session_indices: list[int] = Field(
        default_factory=list,
        description="0-indexed session indices pointing to relevant sessions.",
    )
    confidence: float = Field(
        default=0.0,
        description="Confidence that this skill addresses a real recurring need. 0.0-1.0.",
    )


class SkillCreationProposalOutput(BaseModel):
    """LLM output from the proposal generation step.

    Contains lightweight proposals (name + description + rationale) without
    full SKILL.md content. Deep creation produces the full content per proposal.
    """

    title: str = Field(
        default="",
        description=(
            "Self-explanatory title describing the main finding. "
            "Understandable without reading the rest. Max 10 words."
        ),
    )
    workflow_patterns: list[WorkflowPattern] = Field(
        default_factory=list, description="Detected workflow patterns from trajectory analysis."
    )
    proposals: list[SkillCreationProposal] = Field(
        default_factory=list, description="Proposed skills."
    )


class SkillCreationProposalResult(BaseModel):
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
    model: str = Field(description="Model identifier.")
    backend_id: BackendType = Field(description="Inference backend used.")
    created_at: str = Field(description="ISO timestamp of analysis completion.")
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
    proposal_output: SkillCreationProposalOutput = Field(
        description="LLM-generated proposal output with patterns and proposals."
    )


class SkillCreation(BaseModel):
    """A new skill generated from detected workflow patterns.

    Produced by the deep-creation LLM step. Confidence is set by the service
    from the originating proposal's confidence score.
    """

    name: str = Field(description="Skill name in kebab-case.")
    description: str = Field(
        description=(
            "Specific trigger description for YAML frontmatter. "
            "State what the skill does AND when it activates. "
            "Include trigger phrases. Max 30 words."
        )
    )
    skill_md_content: str = Field(description="Full SKILL.md content including YAML frontmatter.")
    rationale: str = Field(
        description=(
            "One sentence (max 15 words), then 1-2 bullets "
            "starting with '\\n- ' (max 10 words each). Plain language, no jargon."
        )
    )
    tools_used: list[str] = Field(
        default_factory=list,
        description="Tool names referenced in the skill (e.g. Read, Edit, Bash).",
    )
    addressed_patterns: list[str] = Field(
        default_factory=list,
        description="Titles of workflow patterns addressed by this skill.",
    )
    confidence: float = Field(
        default=0.0,
        description="Confidence that this skill addresses a real recurring need. 0.0-1.0.",
    )
