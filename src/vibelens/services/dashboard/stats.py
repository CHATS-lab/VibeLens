"""Dashboard aggregate statistics computation.

Pure functions that transform trajectories into dashboard statistics.
Includes single-pass accumulation of period breakdowns, daily/hourly
distributions, model/project/agent counts, and cost estimation.
"""

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from vibelens.llm.normalizer import normalize_model_name
from vibelens.llm.pricing import compute_cost_from_tokens, compute_step_cost
from vibelens.models.dashboard.dashboard import (
    DailyStat,
    DashboardStats,
    PeriodStats,
    ProjectDetail,
)
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Step, Trajectory
from vibelens.utils import get_logger
from vibelens.utils.timestamps import local_date_key, local_tz, parse_metadata_timestamp

logger = get_logger(__name__)

# Placeholder when a session has no model metadata
UNKNOWN_MODEL = "unknown"
# Placeholder for sessions without a project path
NO_PROJECT = "(no project)"


def compute_dashboard_stats(
    trajectories: list[Trajectory], total_sessions: int | None = None
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
    acc = _StatsAccumulator(local_tz())

    for traj in trajectories:
        session = aggregate_session(traj)
        acc.add_session(session)

    session_count = total_sessions if total_sessions is not None else len(trajectories)
    stats = acc.build(session_count)

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info("Dashboard stats computed: %d sessions in %.1fms", session_count, elapsed_ms)
    return stats


def filter_metadata(
    metadata_list: list[dict],
    project_path: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    agent_name: str | None = None,
) -> list[dict]:
    """Filter metadata by project path, date range, and agent name.

    Args:
        metadata_list: Raw metadata list from store.
        project_path: Optional project path filter.
        date_from: Optional start date (YYYY-MM-DD, inclusive).
        date_to: Optional end date (YYYY-MM-DD, inclusive).
        agent_name: Optional agent name filter (e.g. "claude_code", "codex").

    Returns:
        Filtered metadata list.
    """
    result = metadata_list

    if project_path:
        result = [m for m in result if m.get("project_path") == project_path]

    if agent_name:
        result = [m for m in result if (m.get("agent") or {}).get("name") == agent_name]

    if date_from or date_to:
        result = [m for m in result if _in_date_range(m, date_from, date_to)]

    return result


class _StepBucket:
    """One session's contribution to a single local date.

    Populated from per-step timestamps; lets a cross-day session
    distribute messages / tokens / cost across the days its steps
    actually landed on, while session_count / heatmap / peak hours
    stay anchored to ``Trajectory.timestamp`` (the session's creation
    time).
    """

    __slots__ = ("messages", "tokens", "cost_usd")

    def __init__(self) -> None:
        self.messages: int = 0
        self.tokens: int = 0
        self.cost_usd: float = 0.0


class SessionAggregate:
    """Aggregated metrics for a single session."""

    __slots__ = (
        "messages",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
        "tool_calls",
        "duration",
        "model",
        "project",
        "timestamp",
        "agent_name",
        "cost_usd",
        "daily_breakdown",
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
        self.cost_usd: float = 0.0
        # local_date_key -> _StepBucket; None when the aggregator had no
        # usable per-step timestamps (e.g. metadata-only fast path).
        # Populated sums equal the session totals; a single-day session
        # just has one bucket.
        self.daily_breakdown: dict[str, _StepBucket] | None = None


class _DailyAccumulator:
    """Mutable accumulator for daily stat aggregation."""

    __slots__ = (
        "session_count",
        "total_messages",
        "total_tokens",
        "total_duration",
        "total_cost_usd",
    )

    def __init__(self) -> None:
        self.session_count = 0
        self.total_messages = 0
        self.total_tokens = 0
        self.total_duration = 0
        self.total_cost_usd = 0.0


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
        self.year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        self.month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
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
        self.total_cost_usd = 0.0
        self.cost_by_model: dict[str, float] = defaultdict(float)

        self.year = PeriodStats()
        self.month = PeriodStats()
        self.week = PeriodStats()

        self.daily_buckets: dict[str, _DailyAccumulator] = {}
        self.daily_activity: dict[str, int] = defaultdict(int)
        self.model_dist: dict[str, int] = defaultdict(int)
        self.project_dist: dict[str, int] = defaultdict(int)
        self.project_messages: dict[str, int] = defaultdict(int)
        self.project_tokens: dict[str, int] = defaultdict(int)
        self.project_cost: dict[str, float] = defaultdict(float)
        self.agent_dist: dict[str, int] = defaultdict(int)
        self.hourly_dist: dict[int, int] = defaultdict(int)
        self.heatmap: dict[str, int] = defaultdict(int)
        self.projects_seen: set[str] = set()

    def add_session(self, session: SessionAggregate) -> None:
        """Accumulate one session's metrics.

        Session-level dimensions (session_count, daily_activity, hourly,
        heatmap, duration) anchor on ``session.timestamp``. Messages /
        tokens / cost are bucketed per-day from ``session.daily_breakdown``
        so a session spanning yesterday 23:30 → today 00:30 shows
        activity on both daily bars.
        """
        tokens = session.input_tokens + session.output_tokens

        self.total_messages += session.messages
        self.total_input_tokens += session.input_tokens
        self.total_output_tokens += session.output_tokens
        self.total_cache_read_tokens += session.cache_read_tokens
        self.total_cache_creation_tokens += session.cache_creation_tokens
        self.total_tool_calls += session.tool_calls
        self.total_duration += session.duration

        if session.cost_usd > 0:
            self.total_cost_usd += session.cost_usd
            canonical = normalize_model_name(session.model) or session.model
            self.cost_by_model[canonical] += session.cost_usd

        self.model_dist[session.model] += 1
        self.project_dist[session.project] += 1
        self.project_messages[session.project] += session.messages
        self.project_tokens[session.project] += tokens
        self.project_cost[session.project] += session.cost_usd
        self.agent_dist[session.agent_name] += 1
        if session.project != NO_PROJECT:
            self.projects_seen.add(session.project)

        if not session.timestamp:
            return

        session_ts = session.timestamp
        if session_ts.tzinfo is None:
            session_ts = session_ts.replace(tzinfo=timezone.utc)
        local_ts = session_ts.astimezone(self.local_tz)
        creation_key = local_date_key(local_ts)

        # Creation-day-only counters.
        self.daily_activity[creation_key] += 1
        self.hourly_dist[local_ts.hour] += 1
        self.heatmap[f"{local_ts.weekday()}_{local_ts.hour}"] += 1

        # Messages / tokens / cost credited to each breakdown day.
        breakdown = session.daily_breakdown or {}
        for day_key, bucket in breakdown.items():
            day = self.daily_buckets.setdefault(day_key, _DailyAccumulator())
            day.total_messages += bucket.messages
            day.total_tokens += bucket.tokens
            day.total_cost_usd += bucket.cost_usd
        # session_count and duration are session-identity fields: the
        # creation day owns them, regardless of how the activity was split.
        creation_day = self.daily_buckets.setdefault(creation_key, _DailyAccumulator())
        creation_day.session_count += 1
        creation_day.total_duration += session.duration

        # Period stats. Session-identity fields (sessions / duration /
        # tool_calls / token sub-totals) land once on the creation day.
        # Activity fields (messages / tokens / cost) sum every breakdown
        # day inside the period — so a session crossing into the period
        # contributes its in-period activity even if created earlier.
        for period, period_start in (
            (self.year, self.year_start),
            (self.month, self.month_start),
            (self.week, self.week_start),
        ):
            self._accumulate_period(period, period_start, creation_key, session, breakdown)

    def _accumulate_period(
        self,
        period: PeriodStats,
        period_start: datetime,
        creation_key: str,
        session: SessionAggregate,
        breakdown: dict[str, _StepBucket],
    ) -> None:
        """Fold a session's metrics into one period's totals."""
        period_start_key = local_date_key(period_start)
        if creation_key >= period_start_key:
            period.sessions += 1
            period.tool_calls += session.tool_calls
            period.duration += session.duration
            period.input_tokens += session.input_tokens
            period.output_tokens += session.output_tokens
            period.cache_read_tokens += session.cache_read_tokens
            period.cache_creation_tokens += session.cache_creation_tokens

        for day_key, bucket in breakdown.items():
            if day_key < period_start_key:
                continue
            period.messages += bucket.messages
            period.tokens += bucket.tokens
            period.cost_usd += bucket.cost_usd

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
                    total_cost_usd=round(acc.total_cost_usd, 6),
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
            total_cost_usd=round(self.total_cost_usd, 6),
            cost_by_model=dict(self.cost_by_model),
            avg_cost_per_session=round(self.total_cost_usd / safe_div, 6),
            project_count=len(self.projects_seen),
            daily_activity=dict(self.daily_activity),
            daily_stats=daily_stats,
            agent_distribution=dict(self.agent_dist),
            model_distribution=dict(self.model_dist),
            project_distribution=dict(self.project_dist),
            project_details={
                project: ProjectDetail(
                    sessions=self.project_dist[project],
                    messages=self.project_messages[project],
                    tokens=self.project_tokens[project],
                    cost_usd=round(self.project_cost[project], 6),
                )
                for project in self.project_dist
            },
            hourly_distribution=dict(self.hourly_dist),
            weekday_hour_heatmap=dict(self.heatmap),
            timezone=str(self.local_tz),
        )


def compute_dashboard_stats_from_metadata(metadata_list: list[dict]) -> DashboardStats:
    """Compute dashboard stats from enriched metadata without loading trajectories.

    Uses pre-computed final_metrics stored in the metadata cache (populated
    by fast_metrics scanning during index build). This avoids the ~16s cost
    of parsing all session files for dashboard statistics.

    Args:
        metadata_list: Metadata dicts with enriched final_metrics and agent fields.

    Returns:
        DashboardStats with all chart data populated.
    """
    start = time.monotonic()
    acc = _StatsAccumulator(local_tz())

    for meta in metadata_list:
        session = _aggregate_metadata(meta)
        acc.add_session(session)

    stats = acc.build(len(metadata_list))
    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "Dashboard stats from metadata: %d sessions in %.1fms", len(metadata_list), elapsed_ms
    )
    return stats


def _aggregate_metadata(meta: dict) -> SessionAggregate:
    """Extract aggregate metrics from a single metadata dict.

    Reads the enriched ``final_metrics`` and ``agent`` fields the ingest
    index cache already populated — avoids loading the full trajectory.
    Every metric is credited to the session's creation day (the fast
    path has no step-level granularity), but the output still matches
    the full-trajectory shape so ``add_session`` has one code path.
    """
    agg = SessionAggregate()
    agg.project = meta.get("project_path") or NO_PROJECT
    agg.agent_name = (meta.get("agent") or {}).get("name") or "unknown"
    agg.timestamp = parse_metadata_timestamp(meta)

    model = (meta.get("agent") or {}).get("model_name")
    if _is_real_model(model):
        agg.model = model

    final_metrics = meta.get("final_metrics") or {}
    agg.input_tokens = final_metrics.get("total_prompt_tokens") or 0
    agg.output_tokens = final_metrics.get("total_completion_tokens") or 0
    agg.cache_read_tokens = final_metrics.get("total_cache_read") or 0
    agg.cache_creation_tokens = final_metrics.get("total_cache_write") or 0
    agg.tool_calls = final_metrics.get("tool_call_count") or 0
    agg.messages = final_metrics.get("total_steps") or 0
    agg.duration = final_metrics.get("duration") or 0

    if agg.model != UNKNOWN_MODEL:
        cost = compute_cost_from_tokens(
            agg.model,
            agg.input_tokens,
            agg.output_tokens,
            agg.cache_read_tokens,
            agg.cache_creation_tokens,
        )
        if cost is not None:
            agg.cost_usd = cost

    day = _to_local_date_key(agg.timestamp)
    if day:
        bucket = _StepBucket()
        bucket.messages = agg.messages
        bucket.tokens = agg.input_tokens + agg.output_tokens
        bucket.cost_usd = agg.cost_usd
        agg.daily_breakdown = {day: bucket}
    return agg


def _is_real_model(name: str | None) -> bool:
    """Check if a model name is a real model (not a placeholder).

    Some parsers emit placeholder names like "<unknown>" when the model
    field is absent or unrecognizable. The ``<`` prefix filters these
    so dashboard model distribution only shows real identifiers.
    """
    if not name:
        return False
    return not name.startswith("<")


def aggregate_session(traj: Trajectory) -> SessionAggregate:
    """Extract aggregate metrics from a single trajectory.

    Walks every step once to produce session-level totals and a
    per-local-date breakdown of messages / tokens / cost. The breakdown
    lets a cross-day session split its activity across the days its
    steps actually landed on; session_count / heatmap / peak hours and
    duration still anchor to ``traj.timestamp`` at the caller.

    Per-step cost is read from ``step.metrics.cost_usd`` when populated
    (ingest writes it there for every agent step) and computed on the
    fly otherwise — lets ad-hoc tests or alternative Trajectory builders
    still get correct aggregates.
    """
    agg = SessionAggregate()
    agg.project = traj.project_path or NO_PROJECT
    agg.timestamp = traj.timestamp
    agg.agent_name = (traj.agent.name if traj.agent else None) or "unknown"
    session_model = traj.agent.model_name if traj.agent else None
    agg.model = _resolve_model(session_model, traj.steps)

    # Local-date fallback for steps that lack their own timestamp.
    fallback_date = _to_local_date_key(traj.timestamp)

    breakdown: dict[str, _StepBucket] = {}
    any_cost_found = False
    for step in traj.steps:
        agg.tool_calls += len(step.tool_calls)
        is_message = step.source != StepSource.SYSTEM
        if is_message:
            agg.messages += 1

        tokens_this_step = 0
        cost_this_step = 0.0
        if step.metrics:
            metrics = step.metrics
            agg.input_tokens += metrics.prompt_tokens
            agg.output_tokens += metrics.completion_tokens
            agg.cache_read_tokens += metrics.cached_tokens
            agg.cache_creation_tokens += metrics.cache_creation_tokens
            tokens_this_step = metrics.prompt_tokens + metrics.completion_tokens
            step_cost = metrics.cost_usd
            if step_cost is None:
                step_cost = compute_step_cost(step, session_model)
            if step_cost is not None:
                cost_this_step = step_cost
                any_cost_found = True

        day = _to_local_date_key(step.timestamp) or fallback_date
        if day and (is_message or tokens_this_step or cost_this_step):
            bucket = breakdown.setdefault(day, _StepBucket())
            bucket.messages += int(is_message)
            bucket.tokens += tokens_this_step
            bucket.cost_usd += cost_this_step

    if any_cost_found:
        agg.cost_usd = sum(b.cost_usd for b in breakdown.values())
    agg.daily_breakdown = breakdown or None
    agg.duration = _session_duration(traj)
    return agg


def _resolve_model(session_model: str | None, steps: list[Step]) -> str:
    """Pick the best real model name from the trajectory.

    Prefers the session-level ``agent.model_name``; falls back to the
    first step whose ``model_name`` is a real identifier (parsers emit
    ``<unknown>`` placeholders that we skip).
    """
    if _is_real_model(session_model):
        return session_model
    for step in steps:
        if _is_real_model(step.model_name):
            return step.model_name
    return UNKNOWN_MODEL


def _session_duration(traj: Trajectory) -> int:
    """Session wall-clock duration in seconds.

    Uses ``final_metrics.duration`` when the parser recorded it (avoids
    recomputing what ingest already knows), otherwise spans the first
    and last step timestamps.
    """
    if traj.final_metrics and traj.final_metrics.duration > 0:
        return traj.final_metrics.duration
    if len(traj.steps) >= 2:
        first_ts = traj.steps[0].timestamp
        last_ts = traj.steps[-1].timestamp
        if first_ts and last_ts:
            return max(0, int((last_ts - first_ts).total_seconds()))
    return 0


def _to_local_date_key(timestamp: datetime | None) -> str | None:
    """``YYYY-MM-DD`` in local tz, or ``None`` when ``timestamp`` is missing."""
    if timestamp is None:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return local_date_key(timestamp.astimezone(local_tz()))


def _in_date_range(meta: dict, date_from: str | None, date_to: str | None) -> bool:
    """Check if a metadata entry's timestamp falls within the date range.

    The date key is resolved in the local timezone so filters match the
    day labels used in the daily/hourly aggregations.
    """
    ts = parse_metadata_timestamp(meta)
    if ts is None:
        return False
    date_str = local_date_key(ts)
    if date_from and date_str < date_from:
        return False
    return not (date_to and date_str > date_to)
