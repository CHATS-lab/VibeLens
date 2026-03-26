"""Skill personalization models for LLM-powered trajectory analysis.

Defines the model hierarchy from LLM output through enriched result.
Covers three modes: retrieval, creation, and evolution.

LLM output models contain only fields the LLM should generate.
Business fields (frequency, pattern_id) are computed post-inference.
"""

from enum import StrEnum

from pydantic import BaseModel, Field, computed_field

from vibelens.models.analysis.step_ref import StepRef
from vibelens.models.inference import BackendType


class SkillMode(StrEnum):
    """Skill personalization analysis mode."""

    CREATION = "creation"
    RETRIEVAL = "retrieval"
    EVOLUTION = "evolution"


class WorkflowPattern(BaseModel):
    """A recurring workflow pattern detected from trajectory analysis.

    The LLM generates title, description, pain_point, and example_refs.
    frequency is computed from the number of example_refs.
    """

    title: str = Field(
        description="Short, readable name for this pattern (e.g. 'Search-Read-Edit Cycle')."
    )
    description: str = Field(description="Human-readable description of what this pattern does.")
    pain_point: str = Field(description="Why this pattern is suboptimal or could be automated.")
    example_refs: list[StepRef] = Field(
        default_factory=list, description="Step references where this pattern was observed."
    )

    @computed_field
    @property
    def frequency(self) -> int:
        """Number of occurrences, derived from example_refs count."""
        return len(self.example_refs)


class SkillRecommendation(BaseModel):
    """A skill recommended from the catalog, matched to detected patterns."""

    skill_name: str = Field(description="Name of the recommended skill.")
    match_reason: str = Field(description="Why this skill matches the user's workflow patterns.")
    confidence: float = Field(default=0.0, description="Match confidence from 0.0 to 1.0.")


class SkillCreation(BaseModel):
    """A new skill generated from detected workflow patterns."""

    name: str = Field(description="Proposed skill name in kebab-case.")
    description: str = Field(description="Trigger description for the skill.")
    skill_md_content: str = Field(description="Full SKILL.md content including YAML frontmatter.")
    rationale: str = Field(description="Why this skill would improve the user's workflow.")


class SkillEditKind(StrEnum):
    """Type of granular edit to an existing skill."""

    ADD_INSTRUCTION = "add_instruction"
    REMOVE_INSTRUCTION = "remove_instruction"
    REPLACE_INSTRUCTION = "replace_instruction"
    UPDATE_DESCRIPTION = "update_description"
    ADD_TOOL = "add_tool"
    REMOVE_TOOL = "remove_tool"


class SkillEdit(BaseModel):
    """A single granular edit to an existing skill definition."""

    kind: SkillEditKind = Field(description="Type of edit operation.")
    target: str = Field(description="The instruction, tool, or section being modified.")
    replacement: str | None = Field(
        default=None, description="New content for replace operations. None for removals."
    )
    rationale: str = Field(description="Why this edit improves the skill.")


class SkillEvolutionSuggestion(BaseModel):
    """A suggested improvement to an existing installed skill."""

    skill_name: str = Field(description="Name of the existing skill to evolve.")
    edits: list[SkillEdit] = Field(description="Ordered list of granular edits to apply.")
    rationale: str = Field(description="Overall rationale for evolving this skill.")


class SkillLLMOutput(BaseModel):
    """Raw structured output from LLM skill analysis.

    Contains only fields the LLM should generate. Business fields
    like pattern IDs and frequency are computed post-inference.
    """

    workflow_patterns: list[WorkflowPattern] = Field(
        default_factory=list, description="Detected workflow patterns from trajectory analysis."
    )
    recommendations: list[SkillRecommendation] = Field(
        default_factory=list, description="Recommended skills for retrieval mode."
    )
    generated_skills: list[SkillCreation] = Field(
        default_factory=list, description="Generated skills for creation mode."
    )
    evolution_suggestions: list[SkillEvolutionSuggestion] = Field(
        default_factory=list, description="Evolution suggestions for existing skills."
    )
    summary: str = Field(description="Overall analysis summary across all sessions.")
    user_profile: str = Field(
        default="", description="Brief description of the detected user workflow style."
    )


class SkillAnalysisResult(BaseModel):
    """Complete skill analysis result with service metadata.

    Flattens SkillLLMOutput fields and adds session tracking,
    backend info, and cost metadata from the service layer.
    """

    analysis_id: str | None = Field(
        default=None, description="Persistence ID. Set when saved to disk."
    )
    mode: SkillMode = Field(description="Which analysis mode was used.")
    session_ids: list[str] = Field(
        description="Session IDs that were successfully loaded and analyzed."
    )
    workflow_patterns: list[WorkflowPattern] = Field(
        default_factory=list, description="Detected workflow patterns from trajectory analysis."
    )
    recommendations: list[SkillRecommendation] = Field(
        default_factory=list, description="Recommended skills (retrieval mode)."
    )
    generated_skills: list[SkillCreation] = Field(
        default_factory=list, description="Generated skills (creation mode)."
    )
    evolution_suggestions: list[SkillEvolutionSuggestion] = Field(
        default_factory=list, description="Evolution suggestions (evolution mode)."
    )
    summary: str = Field(description="Overall analysis summary.")
    user_profile: str = Field(default="", description="Detected user workflow style.")
    sessions_skipped: list[str] = Field(
        default_factory=list, description="Session IDs that could not be loaded."
    )
    backend_id: BackendType = Field(description="Inference backend used.")
    model: str = Field(description="Model identifier.")
    cost_usd: float | None = Field(default=None, description="Inference cost in USD.")
    created_at: str = Field(description="ISO timestamp of analysis completion.")
