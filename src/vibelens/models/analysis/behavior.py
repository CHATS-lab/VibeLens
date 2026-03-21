"""Behavior and preference analysis result models."""

from pydantic import BaseModel, Field


class ToolUsageStat(BaseModel):
    """Tool usage statistics."""

    tool_name: str = Field(description="Name of the tool (e.g. 'Bash', 'Read', 'Edit').")
    call_count: int = Field(description="Total number of times this tool was invoked.")
    avg_per_session: float = Field(description="Average invocations per session.")
    error_rate: float = Field(description="Fraction of calls that resulted in an error (0.0-1.0).")


class TimePattern(BaseModel):
    """Time pattern statistics."""

    hour_distribution: dict[int, int] = Field(
        description="Session counts keyed by hour of day (0-23)."
    )
    weekday_distribution: dict[int, int] = Field(
        description="Session counts keyed by weekday (0=Mon ... 6=Sun)."
    )
    avg_session_duration: float = Field(description="Mean session duration in seconds.")
    avg_messages_per_session: float = Field(description="Mean number of messages per session.")


class UserPreferenceResult(BaseModel):
    """User preference analysis result."""

    source_name: str = Field(description="Name of the data source analysed.")
    session_count: int = Field(description="Total sessions included in the analysis.")
    tool_usage: list[ToolUsageStat] = Field(description="Per-tool usage statistics.")
    time_pattern: TimePattern = Field(description="Temporal usage patterns.")
    model_distribution: dict[str, int] = Field(
        description="Session counts keyed by LLM model identifier."
    )
    project_distribution: dict[str, int] = Field(
        description="Session counts keyed by project name."
    )
    top_tool_sequences: list[list[str]] = Field(
        description="Most common ordered sequences of tool invocations."
    )


class AgentBehaviorResult(BaseModel):
    """Agent behavior pattern analysis result."""

    model: str = Field(description="LLM model identifier being analysed.")
    session_count: int = Field(description="Number of sessions included in the analysis.")
    avg_tool_calls_per_session: float = Field(description="Mean tool invocations per session.")
    avg_tokens_per_session: float = Field(
        description="Mean total tokens (input + output) per session."
    )
    tool_selection_variability: float = Field(
        description="Entropy-based measure of tool selection diversity (0.0-1.0)."
    )
    common_tool_patterns: list[dict] = Field(
        description="Frequently observed tool-call sequences and their counts."
    )
    thinking_action_consistency: float | None = Field(
        default=None,
        description="Correlation between thinking content and subsequent actions (0.0-1.0).",
    )
