"""Service-layer result and metadata models for personalization analysis."""

from pydantic import BaseModel, Field

from vibelens.models.llm.inference import BackendType
from vibelens.models.personalization.constants import DESCRIPTION_TITLE
from vibelens.models.personalization.creation import PersonalizationCreation
from vibelens.models.personalization.enums import PersonalizationMode
from vibelens.models.personalization.evolution import PersonalizationEvolution
from vibelens.models.personalization.recommendation import (
    RankedRecommendationItem,
    UserProfile,
)
from vibelens.models.session.patterns import WorkflowPattern
from vibelens.models.trajectories.final_metrics import FinalMetrics
from vibelens.models.trajectories.metrics import Metrics


class PersonalizationMeta(BaseModel):
    """Lightweight metadata for a persisted personalization analysis."""

    id: str = Field(description="Unique analysis ID.")
    mode: PersonalizationMode = Field(description="Analysis mode used.")
    title: str = Field(default="", description=DESCRIPTION_TITLE)
    session_count: int = Field(description="Number of sessions analyzed.")
    batch_count: int = Field(default=1, description="Number of LLM batches used.")
    item_count: int = Field(
        default=0, description="Number of output items (recommendations, creations, or evolutions)."
    )
    backend: BackendType = Field(description="Inference backend used.")
    model: str = Field(description="Model identifier.")
    created_at: str = Field(description="ISO timestamp of analysis completion.")
    final_metrics: FinalMetrics = Field(
        default_factory=FinalMetrics, description="Aggregate cost and token totals."
    )
    is_example: bool = Field(default=False, description="Whether this is a bundled example.")


class PersonalizationResult(BaseModel):
    """Complete personalization result with service metadata.

    Flattens mode-specific LLM output fields and adds session tracking,
    backend info, and cost metadata from the service layer.
    """

    id: str = Field(description="Persistence ID. Set when saved to disk.")
    mode: PersonalizationMode = Field(description="Which analysis mode was used.")
    title: str = Field(description=DESCRIPTION_TITLE)
    session_ids: list[str] = Field(
        description="Session IDs that were successfully loaded and analyzed."
    )
    skipped_session_ids: list[str] = Field(
        default_factory=list, description="Session IDs that could not be loaded."
    )
    workflow_patterns: list[WorkflowPattern] = Field(
        default_factory=list, description="Detected workflow patterns from trajectory analysis."
    )
    recommendations: list[RankedRecommendationItem] = Field(
        default_factory=list, description="Ranked catalog recommendations."
    )
    user_profile: UserProfile | None = Field(
        default=None, description="User profile from L2 generation (recommendation mode)."
    )
    creations: list[PersonalizationCreation] = Field(
        default_factory=list, description="Generated skills (creation mode)."
    )
    evolutions: list[PersonalizationEvolution] = Field(
        default_factory=list, description="Evolution suggestions (evolution mode)."
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
    is_example: bool = Field(default=False, description="Whether this is an example.")
