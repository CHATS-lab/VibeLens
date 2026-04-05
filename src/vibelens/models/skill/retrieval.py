"""Retrieval-mode LLM output models."""

from pydantic import BaseModel, Field

from vibelens.models.skill.patterns import WorkflowPattern


class SkillRecommendation(BaseModel):
    """A skill recommended from the catalog, matched to detected patterns."""

    skill_name: str = Field(description="Name of the recommended skill.")
    rationale: str = Field(
        description="Why this skill fits the detected patterns. 1-2 sentences, under 40 words."
    )
    addressed_patterns: list[str] = Field(
        default_factory=list,
        description="Titles of workflow patterns this recommendation addresses.",
    )
    confidence: float = Field(default=0.0, description="Match confidence from 0.0 to 1.0.")


class SkillRetrievalOutput(BaseModel):
    """LLM output for retrieval-mode skill analysis."""

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
    recommendations: list[SkillRecommendation] = Field(
        default_factory=list, description="Recommended skills from the featured catalog."
    )
