"""Observation result model for ATIF trajectories."""

from typing import Any

from pydantic import BaseModel, Field

from vibelens.models.trajectories.content import ContentPart
from vibelens.models.trajectories.trajectory_ref import TrajectoryRef


class ObservationResult(BaseModel):
    """Result from a single tool execution or sub-agent trajectory (ATIF v1.6).

    Aligned with ATIF v1.6 ObservationResultSchema:
    - source_call_id is nullable (null for non-tool-call actions)
    - content supports multimodal ContentPart arrays
    - subagent_trajectory_ref is a list of TrajectoryRef
    """

    source_call_id: str | None = Field(
        default=None,
        description=(
            "Tool call ID this result corresponds to. Null for actions "
            "outside the standard tool calling format."
        ),
    )
    content: str | list[ContentPart] | None = Field(
        default=None,
        description=(
            "Tool output. String for text-only, or ContentPart array "
            "for multimodal content (ATIF v1.6)."
        ),
    )
    subagent_trajectory_ref: list[TrajectoryRef] | None = Field(
        default=None, description="References to delegated subagent trajectories."
    )
    extra: dict[str, Any] | None = Field(
        default=None,
        description="Structured metadata from tool execution (exit_code, stdout, stderr, etc.).",
    )
