"""Retrieval-mode LLM output models."""

from pydantic import BaseModel, Field

from vibelens.models.skill.patterns import WorkflowPattern


class SkillRecommendation(BaseModel):
    """A skill recommended from the catalog, matched to detected patterns."""

    skill_name: str = Field(description="Name of the recommended skill.")
    description: str = Field(
        default="",
        description="Short description of what this skill does. Set by the service layer.",
    )
    rationale: str = Field(
        description=(
            "Plain-language explanation of why this skill fits. "
            "One short summary sentence, then 1-2 bullets. "
            "Each bullet: '\\n- **Reason**: concise detail'. "
            "Keep under 50 words total. Avoid jargon."
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
        description="Clear, reader-friendly title capturing the main finding. Max 8 words.",
    )
    user_profile: str = Field(
        default="",
        description=(
            "One plain sentence describing the user's role, then 1-2 bullets "
            "with '\\n- **Topic**: detail'. Under 40 words. Avoid jargon."
        ),
    )
    workflow_patterns: list[WorkflowPattern] = Field(
        default_factory=list, description="Detected workflow patterns from trajectory analysis."
    )
    summary: str = Field(
        description=(
            "One plain sentence summarizing the key finding, then 2-4 bullets. "
            "Each bullet: '\\n- **Finding**: concise explanation'. "
            "Readable by non-experts. Under 80 words total."
        )
    )
    recommendations: list[SkillRecommendation] = Field(
        default_factory=list, description="Recommended skills from the featured catalog."
    )
