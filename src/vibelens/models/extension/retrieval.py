"""Retrieval-mode LLM output models."""

from pydantic import BaseModel, Field

from vibelens.models.session.patterns import WorkflowPattern


class SkillRecommendation(BaseModel):
    """A skill recommended from the catalog, matched to detected patterns."""

    skill_name: str = Field(description="Name of the recommended skill.")
    description: str = Field(
        default="",
        description="Short description of what this skill does. Set by the service layer.",
    )
    rationale: str = Field(
        description=(
            "One sentence (max 15 words), then 1-2 bullets "
            "starting with '\\n- ' (max 10 words each). Plain language, no jargon."
        )
    )
    addressed_patterns: list[str] = Field(
        default_factory=list,
        description="Titles of workflow patterns this recommendation addresses.",
    )
    confidence: float = Field(default=0.0, description="Match confidence from 0.0 to 1.0.")


class SkillRetrievalOutput(BaseModel):
    """LLM output for retrieval-mode skill analysis."""

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
    recommendations: list[SkillRecommendation] = Field(
        default_factory=list, description="Recommended skills from the featured catalog."
    )
