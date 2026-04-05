"""Service-layer result models with metadata for skill analysis."""

from pydantic import BaseModel, Field

from vibelens.models.inference import BackendType
from vibelens.models.skill.creation import SkillCreation
from vibelens.models.skill.evolution import SkillEvolution
from vibelens.models.skill.patterns import SkillMode, WorkflowPattern
from vibelens.models.skill.retrieval import SkillRecommendation
from vibelens.models.trajectories.metrics import Metrics


class SkillAnalysisResult(BaseModel):
    """Complete skill analysis result with service metadata.

    Flattens mode-specific LLM output fields and adds session tracking,
    backend info, and cost metadata from the service layer.
    """

    analysis_id: str | None = Field(
        default=None, description="Persistence ID. Set when saved to disk."
    )
    mode: SkillMode = Field(description="Which analysis mode was used.")
    session_ids: list[str] = Field(
        description="Session IDs that were successfully loaded and analyzed."
    )
    title: str = Field(default="", description="LLM-generated analysis title, 5-10 words.")
    workflow_patterns: list[WorkflowPattern] = Field(
        default_factory=list, description="Detected workflow patterns from trajectory analysis."
    )
    recommendations: list[SkillRecommendation] = Field(
        default_factory=list, description="Recommended skills (retrieval mode)."
    )
    creations: list[SkillCreation] = Field(
        default_factory=list, description="Generated skills (creation mode)."
    )
    evolutions: list[SkillEvolution] = Field(
        default_factory=list, description="Evolution suggestions (evolution mode)."
    )
    summary: str = Field(description="Overall analysis summary.")
    user_profile: str = Field(default="", description="Detected user workflow style.")
    skipped_session_ids: list[str] = Field(
        default_factory=list, description="Session IDs that could not be loaded."
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal issues encountered during analysis."
    )
    backend_id: BackendType = Field(description="Inference backend used.")
    model: str = Field(description="Model identifier.")
    metrics: Metrics = Field(
        default_factory=Metrics, description="Token usage and cost from the inference step."
    )
    duration_seconds: float | None = Field(
        default=None, description="Wall-clock analysis duration in seconds."
    )
    batch_count: int = Field(default=1, description="Number of LLM batches used.")
    created_at: str = Field(description="ISO timestamp of analysis completion.")
