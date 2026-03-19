"""Trajectory reference model for ATIF trajectories.

Unified model for all trajectory cross-references: continuation,
subagent delegation, and parent session linkage.
"""

from typing import Any

from pydantic import BaseModel, Field


class TrajectoryRef(BaseModel):
    """Reference to another trajectory.

    Used for all trajectory cross-referencing:
    - last_trajectory_ref: links to the continued-from session
    - parent_trajectory_ref: links back to parent that spawned a sub-agent
    - continued_trajectory_ref: links continuation segments
    - subagent_trajectory_ref: links delegated subagent runs
    """

    session_id: str = Field(description="Session ID of the referenced trajectory.")
    trajectory_path: str | None = Field(
        default=None,
        description="File path to the referenced trajectory.",
    )
    step_id: str | None = Field(
        default=None,
        description="Step ID in the parent that spawned this sub-agent.",
    )
    tool_call_id: str | None = Field(
        default=None,
        description="Tool call ID that triggered the sub-agent spawn.",
    )
    extra: dict[str, Any] | None = Field(
        default=None,
        description="Custom metadata about the referenced trajectory.",
    )
