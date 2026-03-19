"""Observation model for ATIF trajectories."""

from pydantic import BaseModel, Field

from vibelens.models.trajectories.observation_result import ObservationResult


class Observation(BaseModel):
    """Collection of results from tool executions within a step (ATIF v1.6)."""

    results: list[ObservationResult] = Field(
        default_factory=list, description="Ordered list of tool execution results."
    )
