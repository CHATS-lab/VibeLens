"""Dashboard aggregate analysis models."""

from pydantic import BaseModel, Field

from vibelens.models.analysis.phase import PhaseSegment


class DailyStat(BaseModel):
    """Single day aggregation for time series charts."""

    date: str = Field(description="ISO date string (YYYY-MM-DD).")
    session_count: int = Field(description="Number of sessions started on this day.")
    total_messages: int = Field(default=0, description="Total messages on this day.")
    total_tokens: int = Field(description="Sum of prompt + completion tokens.")
    total_duration: int = Field(description="Sum of session durations in seconds.")
    total_duration_hours: float = Field(description="Duration in hours (for chart Y-axis).")


class PeriodStats(BaseModel):
    """Aggregated metrics for a time period (month/week)."""

    sessions: int = Field(default=0, description="Session count in this period.")
    messages: int = Field(default=0, description="Message count in this period.")
    tokens: int = Field(default=0, description="Total tokens in this period.")
    tool_calls: int = Field(default=0, description="Tool call count in this period.")
    duration: int = Field(default=0, description="Duration in seconds in this period.")


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

    # Token breakdown
    total_input_tokens: int = Field(default=0, description="Total prompt/input tokens.")
    total_output_tokens: int = Field(default=0, description="Total completion/output tokens.")
    total_cache_tokens: int = Field(default=0, description="Total cache read + write tokens.")

    # Period breakdowns
    this_year: PeriodStats = Field(default_factory=PeriodStats, description="Current year stats.")
    this_month: PeriodStats = Field(default_factory=PeriodStats, description="Current month stats.")
    this_week: PeriodStats = Field(default_factory=PeriodStats, description="Current week stats.")

    # Averages
    avg_messages_per_session: float = Field(default=0.0, description="Mean messages per session.")
    avg_tokens_per_session: float = Field(default=0.0, description="Mean tokens per session.")
    avg_tool_calls_per_session: float = Field(
        default=0.0, description="Mean tool calls per session."
    )
    avg_duration_per_session: float = Field(
        default=0.0, description="Mean duration per session (seconds)."
    )

    # Project count
    project_count: int = Field(default=0, description="Number of unique projects.")

    # Daily activity heatmap (YYYY-MM-DD -> session count)
    daily_activity: dict[str, int] = Field(
        default_factory=dict, description="Session count per day for yearly heatmap."
    )

    daily_stats: list[DailyStat] = Field(description="Per-day aggregations for time series.")
    model_distribution: dict[str, int] = Field(description="Session count keyed by model name.")
    project_distribution: dict[str, int] = Field(description="Session count keyed by project path.")
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
