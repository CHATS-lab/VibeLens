"""Trajectory model for ATIF (Agent Trajectory Interchange Format)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from vibelens.models.trajectories.agent import Agent
from vibelens.models.trajectories.final_metrics import FinalMetrics
from vibelens.models.trajectories.step import Step
from vibelens.models.trajectories.trajectory_ref import TrajectoryRef
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# All ATIF schema versions this codebase can parse
ATIF_VERSION = Literal[
    "ATIF-v1.0",
    "ATIF-v1.1",
    "ATIF-v1.2",
    "ATIF-v1.3",
    "ATIF-v1.4",
    "ATIF-v1.5",
    "ATIF-v1.6",
]
# Version stamped on newly created trajectories
DEFAULT_ATIF_VERSION = "ATIF-v1.6"


class Trajectory(BaseModel):
    """Agent Trajectory in ATIF format (v1.6 compatible superset).

    Root-level container for a complete agent interaction session.
    VibeLens extends with project_path, first_message,
    prev_trajectory_ref (session continuation), and
    parent_trajectory_ref (sub-agent lineage).
    """

    schema_version: ATIF_VERSION = Field(
        default=DEFAULT_ATIF_VERSION, description="ATIF schema version string."
    )
    session_id: str = Field(description="Unique identifier for the entire agent run.")
    agent: Agent = Field(description="Agent system configuration.")
    timestamp: datetime | None = Field(
        default=None, description="[VibeLens] Session start timestamp, derived from first step."
    )
    project_path: str | None = Field(
        default=None, description="[VibeLens] Working directory inferred from conversation data."
    )
    first_message: str | None = Field(
        default=None, description="[VibeLens] Truncated first user message for session preview."
    )
    final_metrics: FinalMetrics | None = Field(
        default=None, description="Summary metrics for the entire trajectory."
    )
    prev_trajectory_ref: TrajectoryRef | None = Field(
        default=None,
        description=(
            "[VibeLens] Reference to the previous session this one continues from. "
            "Only set on main sessions that are continuations of earlier conversations."
        ),
    )
    parent_trajectory_ref: TrajectoryRef | None = Field(
        default=None,
        description=(
            "[VibeLens] Reference to the parent trajectory that spawned this sub-agent. "
            "Includes step_id and tool_call_id of the spawning call. "
            "Only set on sub-agent trajectories."
        ),
    )
    next_trajectory_ref: TrajectoryRef | None = Field(
        default=None,
        description="Reference to continuation trajectory for multi-segment sessions.",
    )
    notes: str | None = Field(
        default=None, description="Design notes or explanations for format discrepancies."
    )
    extra: dict[str, Any] | None = Field(default=None, description="Custom root-level metadata.")
    steps: list[Step] = Field(
        min_length=1, description="Complete interaction history as ordered Step objects."
    )

    @model_validator(mode="after")
    def backfill_timestamp(self) -> "Trajectory":
        """Derive timestamp from the first step if not already set."""
        if not self.timestamp and self.steps and self.steps[0].timestamp:
            self.timestamp = self.steps[0].timestamp
        return self

    def to_summary(self) -> dict:
        """Return a summary dict excluding steps, suitable for meta sidecar files."""
        return self.model_dump(exclude={"steps"}, mode="json")

    @model_validator(mode="after")
    def validate_unique_step_ids(self) -> "Trajectory":
        """Ensure all step IDs within the trajectory are unique.

        Duplicate step_ids would break cross-referencing (e.g. TrajectoryRef.step_id,
        parent_step_id in extra). Raises ValueError for hard integrity violation.
        """
        seen: set[str] = set()
        duplicates: list[str] = []
        for step in self.steps:
            if step.step_id in seen:
                duplicates.append(step.step_id)
            seen.add(step.step_id)
        if duplicates:
            raise ValueError(f"Trajectory {self.session_id}: duplicate step IDs: {duplicates}")
        return self

    @model_validator(mode="after")
    def validate_tool_observation_balance(self) -> "Trajectory":
        """Warn when total tool_calls and observation results are unbalanced.

        Across all steps, every tool_call should eventually produce one
        ObservationResult. A mismatch indicates orphaned calls or results.
        """
        total_tc = sum(len(s.tool_calls) for s in self.steps)
        total_obs = sum(len(s.observation.results) for s in self.steps if s.observation)
        if total_tc != total_obs:
            logger.debug(
                "Trajectory %s: %d total tool_calls but %d observation results",
                self.session_id,
                total_tc,
                total_obs,
            )
        return self

    @model_validator(mode="after")
    def validate_unique_tool_call_ids(self) -> "Trajectory":
        """Warn when tool_call_ids are duplicated across steps.

        Tool call IDs should be globally unique within a trajectory
        for correct pairing with ObservationResults.
        """
        seen: set[str] = set()
        duplicates: list[str] = []
        for step in self.steps:
            for tc in step.tool_calls:
                if not tc.tool_call_id:
                    continue
                if tc.tool_call_id in seen:
                    duplicates.append(tc.tool_call_id)
                seen.add(tc.tool_call_id)
        if duplicates:
            logger.warning(
                "Trajectory %s: duplicate tool_call_ids: %s", self.session_id, duplicates
            )
        return self
