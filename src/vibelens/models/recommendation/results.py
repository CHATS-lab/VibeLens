"""Recommendation pipeline result models."""

from pydantic import BaseModel, Field

from vibelens.models.llm.inference import BackendType
from vibelens.models.recommendation.catalog import ItemType
from vibelens.models.recommendation.profile import UserProfile
from vibelens.models.trajectories.metrics import Metrics


class RationaleItem(BaseModel):
    """LLM-generated rationale for a single candidate."""

    item_id: str = Field(description="CatalogItem reference.")
    rationale: str = Field(
        description=(
            "Personalized explanation: one sentence (max 15 words), "
            "then 1-2 bullets starting with '\\n- ' (max 10 words each)."
        )
    )
    confidence: float = Field(description="Match confidence from 0.0 to 1.0.")


class RationaleOutput(BaseModel):
    """LLM output for L4 rationale generation."""

    rationales: list[RationaleItem] = Field(
        description="Per-candidate personalized rationales."
    )


class CatalogRecommendation(BaseModel):
    """A single catalog item recommended to the user.

    Includes personalized rationale and scoring from the recommendation pipeline.
    """

    item_id: str = Field(description="CatalogItem reference.")
    item_type: ItemType = Field(description="Item type.")
    user_label: str = Field(description="User-facing type label.")
    name: str = Field(description="Display name.")
    description: str = Field(description="Plain language description.")
    rationale: str = Field(description="Personalized rationale: 1 sentence + 1-2 bullets.")
    confidence: float = Field(description="Match confidence 0.0-1.0.")
    quality_score: float = Field(description="Catalog quality score 0-100.")
    score: float = Field(description="Composite score from scoring pipeline.")
    install_method: str = Field(description="How to install.")
    install_command: str | None = Field(default=None, description="Install command.")
    has_content: bool = Field(description="Whether install_content is bundled.")
    source_url: str = Field(description="GitHub URL.")


class RecommendationResult(BaseModel):
    """Complete recommendation pipeline result.

    Contains the user profile, ranked recommendations, and analysis metadata.
    """

    analysis_id: str | None = Field(default=None, description="Set on persistence.")
    session_ids: list[str] = Field(description="Sessions analyzed.")
    skipped_session_ids: list[str] = Field(default_factory=list, description="Sessions not found.")
    title: str = Field(description="Main finding, max 10 words.")
    summary: str = Field(description="1-2 sentence narrative.")
    user_profile: UserProfile = Field(description="Extracted profile from L2.")
    recommendations: list[CatalogRecommendation] = Field(description="Ranked results.")
    backend_id: BackendType = Field(description="Inference backend.")
    model: str = Field(description="Model identifier.")
    created_at: str = Field(description="ISO timestamp.")
    metrics: Metrics = Field(default_factory=Metrics, description="Token usage and cost.")
    duration_seconds: float | None = Field(default=None, description="Wall-clock time.")
    catalog_version: str = Field(description="Catalog snapshot version used.")
    is_example: bool = Field(default=False, description="Bundled example flag.")
