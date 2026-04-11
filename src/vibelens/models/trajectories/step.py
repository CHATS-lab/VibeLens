"""Step model for ATIF trajectories."""

from datetime import datetime
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, model_validator

from vibelens.models.enums import StepSource
from vibelens.models.trajectories.content import ContentPart
from vibelens.models.trajectories.metrics import Metrics
from vibelens.models.trajectories.observation import Observation
from vibelens.models.trajectories.tool_call import ToolCall
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class Step(BaseModel):
    """Unified step model (ATIF v1.6 compatible superset).

    Field order follows Harbor reference implementation:
    step_id, timestamp, source, model_name, reasoning_effort,
    message, reasoning_content, tool_calls, observation, metrics,
    is_copied_context, extra.
    """

    step_id: str = Field(
        description=(
            "Step identifier. ATIF uses ordinal int; VibeLens uses "
            "UUID strings for stable cross-session referencing."
        )
    )
    timestamp: Optional[datetime] = Field(default=None, description="When the step was created.")
    source: StepSource = Field(description="The originator of this step.")
    model_name: Optional[str] = Field(
        default=None, description="LLM model identifier for this step."
    )
    reasoning_effort: Optional[Union[str, float]] = Field(
        default=None,
        description="Qualitative or quantitative measure of reasoning effort (ATIF v1.6).",
    )
    message: Union[str, list[ContentPart]] = Field(
        default="",
        description=(
            "Dialogue message. String for text-only, or ContentPart "
            "array for multimodal content (ATIF v1.6)."
        ),
    )
    reasoning_content: Optional[str] = Field(
        default=None, description="Agent's explicit internal reasoning text."
    )
    tool_calls: list[ToolCall] = Field(
        default_factory=list, description="Tool invocations extracted from this step."
    )
    observation: Optional[Observation] = Field(
        default=None, description="Tool execution results observed after this step."
    )
    metrics: Optional[Metrics] = Field(
        default=None, description="Token usage and cost statistics for this step."
    )
    is_copied_context: Optional[bool] = Field(
        default=None,
        description=(
            "Whether this step was copied from a previous trajectory "
            "for context during continuation (ATIF v1.5)."
        ),
    )
    extra: Optional[dict[str, Any]] = Field(default=None, description="Custom step-level metadata.")

    @model_validator(mode="after")
    def validate_tool_observation_pairing(self) -> "Step":
        """Validate that tool_calls and observation results are paired.

        - Orphaned observations (obs referencing non-existent tool_call)
          raise ValueError — this is always a data integrity error.
        - Orphaned tool_calls (tool_call with no matching observation)
          log a warning — the last tool call in a session may not have
          received its result yet.
        """
        if not self.tool_calls or not self.observation:
            return self
        tc_ids = {tc.tool_call_id for tc in self.tool_calls if tc.tool_call_id}
        obs_ids = {r.source_call_id for r in self.observation.results if r.source_call_id}

        orphaned_obs = obs_ids - tc_ids
        if orphaned_obs:
            raise ValueError(
                f"Step {self.step_id}: observation(s) reference non-existent "
                f"tool_call IDs: {orphaned_obs}"
            )

        orphaned_tc = tc_ids - obs_ids
        if orphaned_tc:
            logger.debug(
                "Step %s: tool_call(s) without matching observation: %s", self.step_id, orphaned_tc
            )
        return self
