"""Creation pipeline result model."""

from pydantic import BaseModel, Field

from vibelens.models.creation.models import ElementCreation
from vibelens.models.llm.inference import BackendType
from vibelens.models.session.patterns import WorkflowPattern
from vibelens.models.trajectories.metrics import Metrics


class CreationResult(BaseModel):
    """Complete creation analysis result across all batches.

    Contains detected workflow patterns and the generated elements.
    """

    analysis_id: str | None = Field(default=None, description="Set on persistence.")
    session_ids: list[str] = Field(description="Sessions analyzed.")
    skipped_session_ids: list[str] = Field(default_factory=list, description="Sessions not found.")
    title: str = Field(description="Main finding, max 10 words.")
    workflow_patterns: list[WorkflowPattern] = Field(
        default_factory=list, description="Detected workflow patterns."
    )
    creations: list[ElementCreation] = Field(
        default_factory=list, description="Generated elements."
    )
    backend_id: BackendType = Field(description="Inference backend.")
    model: str = Field(description="Model identifier.")
    created_at: str = Field(description="ISO timestamp.")
    batch_count: int = Field(default=1, description="Number of LLM batches.")
    metrics: Metrics = Field(default_factory=Metrics, description="Token usage and cost.")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal issues.")
    duration_seconds: float | None = Field(default=None, description="Wall-clock duration.")
    is_example: bool = Field(default=False, description="Bundled example flag.")
