"""Dashboard aggregate analysis and behavior models."""

from pydantic import BaseModel, Field

from vibelens.models.analysis.phase import PhaseSegment


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


class DailyStat(BaseModel):
    """Single day aggregation for time series charts."""

    date: str = Field(description="ISO date string (YYYY-MM-DD).")
    session_count: int = Field(description="Number of sessions started on this day.")
    total_messages: int = Field(default=0, description="Total messages on this day.")
    total_tokens: int = Field(description="Sum of prompt + completion tokens.")
    total_duration: int = Field(description="Sum of session durations in seconds.")
    total_duration_hours: float = Field(description="Duration in hours (for chart Y-axis).")
    total_cost_usd: float = Field(default=0.0, description="Estimated cost in USD for this day.")


class PeriodStats(BaseModel):
    """Aggregated metrics for a time period (month/week)."""

    sessions: int = Field(default=0, description="Session count in this period.")
    messages: int = Field(default=0, description="Message count in this period.")
    tokens: int = Field(default=0, description="Total tokens in this period.")
    tool_calls: int = Field(default=0, description="Tool call count in this period.")
    duration: int = Field(default=0, description="Duration in seconds in this period.")
    input_tokens: int = Field(default=0, description="Prompt/input tokens in this period.")
    output_tokens: int = Field(default=0, description="Completion/output tokens in this period.")
    cache_read_tokens: int = Field(default=0, description="Cache read tokens in this period.")
    cache_creation_tokens: int = Field(
        default=0, description="Cache creation tokens in this period."
    )
    cost_usd: float = Field(default=0.0, description="Estimated cost in USD for this period.")


class ProjectDetail(BaseModel):
    """Per-project aggregate metrics for the project activity panel."""

    sessions: int = Field(description="Number of sessions in this project.")
    messages: int = Field(default=0, description="Total messages in this project.")
    tokens: int = Field(default=0, description="Total tokens (input + output).")
    cost_usd: float = Field(default=0.0, description="Estimated cost in USD.")


class DashboardStats(BaseModel):
    """Aggregate statistics for the analysis dashboard.

    Computed from full trajectory data via single-pass aggregation.
    All time-dimension charts (daily_stats, hourly_distribution, heatmap)
    exclude sessions with no timestamp.
    """

    total_sessions: int = Field(description="Total number of sessions.")
    total_messages: int = Field(description="Total message count across all sessions.")
    total_tokens: int = Field(description="Total tokens (prompt + completion).")
    total_tool_calls: int = Field(description="Total tool invocations.")
    total_duration: int = Field(description="Total duration in seconds.")
    total_duration_hours: float = Field(description="Total duration in hours (display).")

    total_input_tokens: int = Field(default=0, description="Total prompt/input tokens.")
    total_output_tokens: int = Field(default=0, description="Total completion/output tokens.")
    total_cache_tokens: int = Field(default=0, description="Total cache read + write tokens.")
    total_cache_read_tokens: int = Field(default=0, description="Total cache read tokens.")
    total_cache_creation_tokens: int = Field(
        default=0, description="Total cache creation/write tokens."
    )

    this_year: PeriodStats = Field(default_factory=PeriodStats, description="Current year stats.")
    this_month: PeriodStats = Field(default_factory=PeriodStats, description="Current month stats.")
    this_week: PeriodStats = Field(default_factory=PeriodStats, description="Current week stats.")

    avg_messages_per_session: float = Field(default=0.0, description="Mean messages per session.")
    avg_tokens_per_session: float = Field(default=0.0, description="Mean tokens per session.")
    avg_tool_calls_per_session: float = Field(
        default=0.0, description="Mean tool calls per session."
    )
    avg_duration_per_session: float = Field(
        default=0.0, description="Mean duration per session (seconds)."
    )

    total_cost_usd: float = Field(default=0.0, description="Estimated total cost in USD.")
    cost_by_model: dict[str, float] = Field(
        default_factory=dict, description="Cost breakdown by canonical model name."
    )
    avg_cost_per_session: float = Field(
        default=0.0, description="Mean estimated cost per session in USD."
    )

    project_count: int = Field(default=0, description="Number of unique projects.")

    daily_activity: dict[str, int] = Field(
        default_factory=dict, description="Session count per day for yearly heatmap."
    )

    daily_stats: list[DailyStat] = Field(description="Per-day aggregations for time series.")
    model_distribution: dict[str, int] = Field(description="Session count keyed by model name.")
    project_distribution: dict[str, int] = Field(description="Session count keyed by project path.")
    project_details: dict[str, ProjectDetail] = Field(
        default_factory=dict,
        description="Per-project aggregate metrics (sessions, messages, tokens, cost).",
    )
    hourly_distribution: dict[int, int] = Field(
        description="Session starts keyed by hour of day (0-23)."
    )
    weekday_hour_heatmap: dict[str, int] = Field(
        description="Session starts keyed by 'weekday_hour' (e.g. '1_14' = Monday 14:00)."
    )
    agent_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Session count keyed by agent name (e.g. claude-code, codex, gemini).",
    )
    timezone: str = Field(default="UTC", description="IANA timezone name used for time groupings.")
    cached_at: str | None = Field(
        default=None, description="ISO timestamp when these stats were last computed and cached."
    )


class SessionAnalytics(BaseModel):
    """Per-session analytics for the session detail view."""

    session_id: str = Field(description="Session identifier.")
    token_breakdown: dict[str, int] = Field(
        description="Token counts by category: prompt, completion, cache_read, cache_write."
    )
    tool_frequency: dict[str, int] = Field(description="Tool call counts keyed by function name.")
    step_count_by_source: dict[str, int] = Field(
        description="Step counts keyed by source: user, agent, system."
    )
    phase_segments: list[PhaseSegment] = Field(
        description="Conversation phase segments from PhaseDetector."
    )
    cost_usd: float | None = Field(
        default=None, description="Estimated session cost in USD based on API pricing."
    )
