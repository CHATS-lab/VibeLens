"""Cross-agent session correlation models."""

from pydantic import BaseModel, Field


class CorrelatedSession(BaseModel):
    """A single session participating in a correlated group."""

    agent_name: str = Field(description="Agent name (e.g. 'claude-code', 'codex').")
    session_id: str = Field(description="Unique session identifier.")
    is_main: bool = Field(
        default=True, description="Whether this is a main session or a sub-agent session."
    )


class CorrelatedGroup(BaseModel):
    """A group of trajectories from different agents on the same project.

    Includes hierarchy details: which sessions are main-agent sessions
    and which are sub-agent sessions, supporting cascade relationships
    where sub-agents can themselves have subordinate sub-agents.
    """

    project_path: str = Field(description="Project path shared by all trajectories in the group.")
    sessions: list[CorrelatedSession] = Field(
        default_factory=list,
        description="Sessions in this correlated group with main/sub-agent roles.",
    )
    time_overlap_seconds: int = Field(
        default=0, description="Maximum time overlap between any two sessions in seconds."
    )
