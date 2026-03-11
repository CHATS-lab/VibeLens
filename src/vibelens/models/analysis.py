"""Analysis result models."""

from pydantic import BaseModel


class ToolUsageStat(BaseModel):
    """Tool usage statistics."""

    tool_name: str
    call_count: int
    avg_per_session: float
    error_rate: float


class TimePattern(BaseModel):
    """Time pattern statistics."""

    hour_distribution: dict[int, int]
    weekday_distribution: dict[int, int]
    avg_session_duration: float
    avg_messages_per_session: float


class UserPreferenceResult(BaseModel):
    """User preference analysis result."""

    source_name: str
    session_count: int
    tool_usage: list[ToolUsageStat]
    time_pattern: TimePattern
    model_distribution: dict[str, int]
    project_distribution: dict[str, int]
    top_tool_sequences: list[list[str]]


class AgentBehaviorResult(BaseModel):
    """Agent behavior pattern analysis result."""

    model: str
    session_count: int
    avg_tool_calls_per_session: float
    avg_tokens_per_session: float
    tool_selection_variability: float
    common_tool_patterns: list[dict]
    thinking_action_consistency: float | None = None
