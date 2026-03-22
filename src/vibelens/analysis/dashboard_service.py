"""Dashboard aggregate analysis computation.

Pure functions that transform trajectories into dashboard statistics.
Uses full Trajectory objects to get accurate token/tool/duration metrics.
"""

import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from vibelens.analysis.phase_detector import detect_phases
from vibelens.ingest.parsers.base import is_error_content
from vibelens.models.analysis.behavior import ToolUsageStat
from vibelens.models.analysis.dashboard import (
    DailyStat,
    DashboardStats,
    PeriodStats,
    SessionAnalytics,
)
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Step, Trajectory
from vibelens.utils import get_logger
from vibelens.utils.timestamps import parse_metadata_timestamp

logger = get_logger(__name__)

UNKNOWN_MODEL = "unknown"
NO_PROJECT = "(no project)"


def compute_dashboard_stats(
    trajectories: list[Trajectory],
    total_sessions: int | None = None,
) -> DashboardStats:
    """Compute aggregate dashboard statistics from full trajectories.

    Iterates all trajectories and their steps to accurately compute
    token counts, tool calls, duration, and model distribution.

    Args:
        trajectories: Full Trajectory objects with steps loaded.
        total_sessions: Override session count (e.g. from metadata count
            when some sessions failed to parse). Defaults to len(trajectories).

    Returns:
        DashboardStats with all chart data populated.
    """
    start = time.monotonic()
    local_tz = datetime.now().astimezone().tzinfo
    acc = _StatsAccumulator(local_tz)

    for traj in trajectories:
        session = _aggregate_session(traj)
        acc.add_session(session)

    session_count = total_sessions if total_sessions is not None else len(trajectories)
    stats = acc.build(session_count)

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "Dashboard stats computed: %d sessions in %.1fms",
        session_count,
        elapsed_ms,
    )
    return stats


def compute_tool_usage(trajectories: list[Trajectory]) -> list[ToolUsageStat]:
    """Compute per-tool usage statistics from full trajectories.

    Args:
        trajectories: Fully loaded Trajectory objects.

    Returns:
        ToolUsageStat list sorted by call_count descending.
    """
    tool_counts: dict[str, int] = defaultdict(int)
    tool_errors: dict[str, int] = defaultdict(int)
    session_count = len(trajectories)

    for traj in trajectories:
        for step in traj.steps:
            for tc in step.tool_calls:
                tool_counts[tc.function_name] += 1
            if step.observation:
                _count_observation_errors(step, tool_errors)

    if session_count == 0:
        return []

    stats = []
    for tool_name, count in tool_counts.items():
        errors = tool_errors.get(tool_name, 0)
        error_rate = round(errors / count, 3) if count > 0 else 0.0
        stats.append(
            ToolUsageStat(
                tool_name=tool_name,
                call_count=count,
                avg_per_session=round(count / session_count, 2),
                error_rate=error_rate,
            )
        )

    stats.sort(key=lambda s: s.call_count, reverse=True)
    return stats


def compute_session_analytics(trajectories: list[Trajectory]) -> SessionAnalytics:
    """Compute detailed analytics for a single session.

    Args:
        trajectories: Trajectory group for one session (main + sub-agents).

    Returns:
        SessionAnalytics with token breakdown, tool frequency, and phase segments.
    """
    if not trajectories:
        raise ValueError("No trajectories provided for session analytics")

    main = trajectories[0]
    all_steps = []
    for traj in trajectories:
        all_steps.extend(traj.steps)

    return SessionAnalytics(
        session_id=main.session_id,
        token_breakdown=_compute_token_breakdown(trajectories),
        tool_frequency=_compute_tool_frequency(trajectories),
        step_count_by_source=_compute_step_counts(trajectories),
        phase_segments=detect_phases(all_steps),
    )


def filter_metadata(
    metadata_list: list[dict],
    project_path: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Filter metadata by project path and date range.

    Args:
        metadata_list: Raw metadata list from store.
        project_path: Optional project path filter.
        date_from: Optional start date (YYYY-MM-DD, inclusive).
        date_to: Optional end date (YYYY-MM-DD, inclusive).

    Returns:
        Filtered metadata list.
    """
    result = metadata_list

    if project_path:
        result = [m for m in result if m.get("project_path") == project_path]

    if date_from or date_to:
        result = [m for m in result if _in_date_range(m, date_from, date_to)]

    return result


class _SessionAggregate:
    """Aggregated metrics for a single session."""

    __slots__ = (
        "messages", "input_tokens", "output_tokens",
        "cache_read_tokens", "cache_creation_tokens", "tool_calls", "duration",
        "model", "project", "timestamp", "agent_name",
    )

    def __init__(self) -> None:
        self.messages: int = 0
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cache_read_tokens: int = 0
        self.cache_creation_tokens: int = 0
        self.tool_calls: int = 0
        self.duration: int = 0
        self.model: str = UNKNOWN_MODEL
        self.project: str = NO_PROJECT
        self.timestamp: datetime | None = None
        self.agent_name: str = "unknown"


class _DailyAccumulator:
    """Mutable accumulator for daily stat aggregation."""

    __slots__ = ("session_count", "total_messages", "total_tokens", "total_duration")

    def __init__(self) -> None:
        self.session_count = 0
        self.total_messages = 0
        self.total_tokens = 0
        self.total_duration = 0


class _StatsAccumulator:
    """Accumulates all dashboard dimensions in a single pass over sessions.

    Stores period boundaries at init using the local timezone so that
    daily/hourly groupings and period comparisons match the user's clock.
    """

    def __init__(self, local_tz: datetime.tzinfo) -> None:
        # Period boundaries use local timezone so "this week" and
        # "this month" match the user's wall clock, not UTC.
        self.local_tz = local_tz
        now = datetime.now(tz=local_tz)
        self.year_start = now.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        self.month_start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        self.week_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        self.total_messages = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cache_read_tokens = 0
        self.total_cache_creation_tokens = 0
        self.total_tool_calls = 0
        self.total_duration = 0

        self.year = PeriodStats()
        self.month = PeriodStats()
        self.week = PeriodStats()

        self.daily_buckets: dict[str, _DailyAccumulator] = {}
        self.daily_activity: dict[str, int] = defaultdict(int)
        self.model_dist: dict[str, int] = defaultdict(int)
        self.project_dist: dict[str, int] = defaultdict(int)
        self.agent_dist: dict[str, int] = defaultdict(int)
        self.hourly_dist: dict[int, int] = defaultdict(int)
        self.heatmap: dict[str, int] = defaultdict(int)
        self.projects_seen: set[str] = set()

    def _to_local(self, ts: datetime) -> datetime:
        """Convert timestamp to local timezone (naive assumed UTC)."""
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts.astimezone(self.local_tz)

    def add_session(self, session: _SessionAggregate) -> None:
        """Accumulate one session's metrics."""
        tokens = session.input_tokens + session.output_tokens

        self.total_messages += session.messages
        self.total_input_tokens += session.input_tokens
        self.total_output_tokens += session.output_tokens
        self.total_cache_read_tokens += session.cache_read_tokens
        self.total_cache_creation_tokens += session.cache_creation_tokens
        self.total_tool_calls += session.tool_calls
        self.total_duration += session.duration

        self.model_dist[session.model] += 1
        self.project_dist[session.project] += 1
        self.agent_dist[session.agent_name] += 1
        if session.project != NO_PROJECT:
            self.projects_seen.add(session.project)

        if not session.timestamp:
            return

        local_ts = self._to_local(session.timestamp)

        # Period breakdowns (year / month / week)
        self._accumulate_period(
            self.year, local_ts >= self.year_start,
            session, tokens,
        )
        self._accumulate_period(
            self.month, local_ts >= self.month_start,
            session, tokens,
        )
        self._accumulate_period(
            self.week, local_ts >= self.week_start,
            session, tokens,
        )

        # Daily bucket (local time)
        date_key = local_ts.strftime("%Y-%m-%d")
        bucket = self.daily_buckets.get(date_key)
        if bucket is None:
            bucket = _DailyAccumulator()
            self.daily_buckets[date_key] = bucket
        bucket.session_count += 1
        bucket.total_messages += session.messages
        bucket.total_tokens += tokens
        bucket.total_duration += session.duration

        self.daily_activity[date_key] += 1
        self.hourly_dist[local_ts.hour] += 1
        self.heatmap[f"{local_ts.weekday()}_{local_ts.hour}"] += 1

    def _accumulate_period(
        self,
        period: PeriodStats,
        in_period: bool,
        session: _SessionAggregate,
        tokens: int,
    ) -> None:
        """Add session metrics to a period if it falls within the boundary."""
        if not in_period:
            return
        period.sessions += 1
        period.messages += session.messages
        period.tokens += tokens
        period.tool_calls += session.tool_calls
        period.duration += session.duration
        period.input_tokens += session.input_tokens
        period.output_tokens += session.output_tokens
        period.cache_read_tokens += session.cache_read_tokens
        period.cache_creation_tokens += session.cache_creation_tokens

    def build(self, total_sessions: int) -> DashboardStats:
        """Build the final DashboardStats from accumulated data."""
        total_tokens = self.total_input_tokens + self.total_output_tokens
        total_hours = round(self.total_duration / 3600, 2)

        safe_div = max(total_sessions, 1)

        daily_stats = []
        for date_key in sorted(self.daily_buckets):
            acc = self.daily_buckets[date_key]
            daily_stats.append(
                DailyStat(
                    date=date_key,
                    session_count=acc.session_count,
                    total_messages=acc.total_messages,
                    total_tokens=acc.total_tokens,
                    total_duration=acc.total_duration,
                    total_duration_hours=round(acc.total_duration / 3600, 2),
                )
            )

        return DashboardStats(
            total_sessions=total_sessions,
            total_messages=self.total_messages,
            total_tokens=total_tokens,
            total_tool_calls=self.total_tool_calls,
            total_duration=self.total_duration,
            total_duration_hours=total_hours,
            total_input_tokens=self.total_input_tokens,
            total_output_tokens=self.total_output_tokens,
            total_cache_tokens=self.total_cache_read_tokens + self.total_cache_creation_tokens,
            total_cache_read_tokens=self.total_cache_read_tokens,
            total_cache_creation_tokens=self.total_cache_creation_tokens,
            this_year=self.year,
            this_month=self.month,
            this_week=self.week,
            avg_messages_per_session=round(self.total_messages / safe_div, 1),
            avg_tokens_per_session=round(total_tokens / safe_div, 0),
            avg_tool_calls_per_session=round(self.total_tool_calls / safe_div, 1),
            avg_duration_per_session=round(self.total_duration / safe_div, 0),
            project_count=len(self.projects_seen),
            daily_activity=dict(self.daily_activity),
            daily_stats=daily_stats,
            agent_distribution=dict(self.agent_dist),
            model_distribution=dict(self.model_dist),
            project_distribution=dict(self.project_dist),
            hourly_distribution=dict(self.hourly_dist),
            weekday_hour_heatmap=dict(self.heatmap),
            timezone=str(self.local_tz),
        )


def _is_real_model(name: str | None) -> bool:
    """Check if a model name is a real model (not a placeholder).

    Some parsers emit placeholder names like "<unknown>" when the model
    field is absent or unrecognizable. The ``<`` prefix filters these
    so dashboard model distribution only shows real identifiers.
    """
    if not name:
        return False
    return not name.startswith("<")


def _aggregate_session(traj: Trajectory) -> _SessionAggregate:
    """Extract aggregate metrics from a single trajectory."""
    agg = _SessionAggregate()
    # Count only user and agent steps as "messages" — system-injected
    # steps (context continuations, tool result summaries) inflate counts.
    # Exclude system steps (context continuations, tool result summaries)
    # from the message count — they inflate numbers without representing
    # real user-agent interaction.
    agg.messages = sum(1 for s in traj.steps if s.source != StepSource.SYSTEM)
    agg.project = traj.project_path or NO_PROJECT
    agg.timestamp = traj.timestamp
    agg.agent_name = (traj.agent.name if traj.agent else None) or "unknown"

    # Model from agent, then step-level fallback; skip placeholders
    if traj.agent and _is_real_model(traj.agent.model_name):
        agg.model = traj.agent.model_name
    else:
        for step in traj.steps:
            if _is_real_model(step.model_name):
                agg.model = step.model_name
                break

    # Aggregate step-level metrics
    for step in traj.steps:
        for _tc in step.tool_calls:
            agg.tool_calls += 1
        if step.metrics:
            agg.input_tokens += step.metrics.prompt_tokens
            agg.output_tokens += step.metrics.completion_tokens
            agg.cache_read_tokens += step.metrics.cached_tokens
            agg.cache_creation_tokens += step.metrics.cache_creation_tokens

    # Duration from final_metrics or from timestamp span
    if traj.final_metrics and traj.final_metrics.duration > 0:
        agg.duration = traj.final_metrics.duration
    elif len(traj.steps) >= 2:
        first_ts = traj.steps[0].timestamp
        last_ts = traj.steps[-1].timestamp
        if first_ts and last_ts:
            agg.duration = max(0, int((last_ts - first_ts).total_seconds()))

    return agg


def _in_date_range(meta: dict, date_from: str | None, date_to: str | None) -> bool:
    """Check if a metadata entry's timestamp falls within the date range."""
    ts = parse_metadata_timestamp(meta)
    if ts is None:
        return False
    date_str = ts.strftime("%Y-%m-%d")
    if date_from and date_str < date_from:
        return False
    return not (date_to and date_str > date_to)


def _compute_token_breakdown(trajectories: list[Trajectory]) -> dict[str, int]:
    """Aggregate token counts by category across all trajectories."""
    prompt = 0
    completion = 0
    cache_read = 0
    cache_write = 0

    for traj in trajectories:
        for step in traj.steps:
            if step.metrics:
                prompt += step.metrics.prompt_tokens
                completion += step.metrics.completion_tokens
                cache_read += step.metrics.cached_tokens
                cache_write += step.metrics.cache_creation_tokens

    return {
        "prompt": prompt,
        "completion": completion,
        "cache_read": cache_read,
        "cache_write": cache_write,
    }


def _compute_tool_frequency(trajectories: list[Trajectory]) -> dict[str, int]:
    """Count tool calls by function name across all trajectories."""
    counts: dict[str, int] = defaultdict(int)
    for traj in trajectories:
        for step in traj.steps:
            for tc in step.tool_calls:
                counts[tc.function_name] += 1
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))


def _compute_step_counts(trajectories: list[Trajectory]) -> dict[str, int]:
    """Count steps by source (user/agent/system) across all trajectories."""
    counts: dict[str, int] = defaultdict(int)
    for traj in trajectories:
        for step in traj.steps:
            counts[step.source.value] += 1
    return dict(counts)


def _count_observation_errors(step: Step, tool_errors: dict[str, int]) -> None:
    """Count error results and attribute them to tool calls."""
    if not step.observation:
        return

    call_map = {tc.tool_call_id: tc.function_name for tc in step.tool_calls}

    for result in step.observation.results:
        if is_error_content(result.content):
            func_name = call_map.get(result.source_call_id or "", "")
            if func_name:
                tool_errors[func_name] += 1
