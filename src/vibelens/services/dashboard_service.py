"""Dashboard service — trajectory loading, caching, export, and reconciliation."""

import csv
import io
import json
import time
from datetime import datetime, timedelta

from fastapi.responses import StreamingResponse

from vibelens.analysis.dashboard_service import (
    compute_dashboard_stats,
    compute_session_analytics,
    compute_tool_usage,
    filter_metadata,
)
from vibelens.deps import get_store
from vibelens.models.analysis.behavior import ToolUsageStat
from vibelens.models.analysis.dashboard import DashboardStats, SessionAnalytics
from vibelens.models.trajectories import Trajectory
from vibelens.utils import get_logger
from vibelens.utils.timestamps import parse_metadata_timestamp

logger = get_logger(__name__)

# Cache TTL balances freshness with cost of full trajectory loading.
# 5 minutes is long enough to survive repeated dashboard refreshes
# but short enough to pick up newly uploaded sessions promptly.
CACHE_TTL_SECONDS = 300

_dashboard_cache: dict[str, tuple[float, DashboardStats]] = {}
_tool_usage_cache: dict[str, tuple[float, list[ToolUsageStat]]] = {}


def load_filtered_trajectories(
    project_path: str | None, date_from: str | None, date_to: str | None, session_token: str | None
) -> tuple[list[Trajectory], list[dict]]:
    """Load all trajectories matching the filters.

    Enriches loaded trajectories with project_path from skeleton metadata
    when the full parse fails to extract it. Returns both the trajectory
    list and the filtered metadata list (for accurate session counts).

    Args:
        project_path: Optional project path filter.
        date_from: Optional start date (YYYY-MM-DD).
        date_to: Optional end date (YYYY-MM-DD).
        session_token: Browser tab token for upload scoping.

    Returns:
        Tuple of (loaded trajectories, filtered metadata list).
    """
    store = get_store()
    metadata = store.list_metadata(session_token=session_token)
    filtered = filter_metadata(metadata, project_path, date_from, date_to)

    trajectories = []
    for meta in filtered:
        session_id = meta.get("session_id", "")
        if not session_id:
            continue
        try:
            group = store.load(session_id, session_token=session_token)
            if group:
                traj = group[0]
                # Enrich project_path from skeleton metadata when full
                # parse fails to extract it (cwd not in first N entries)
                if not traj.project_path:
                    traj.project_path = meta.get("project_path")
                trajectories.append(traj)
        except Exception:
            logger.warning("Failed to load session %s, skipping", session_id)

    return trajectories, filtered


def get_dashboard_stats(
    project_path: str | None, date_from: str | None, date_to: str | None, session_token: str | None
) -> DashboardStats:
    """Compute dashboard stats with caching and session count reconciliation.

    Args:
        project_path: Optional project path filter.
        date_from: Optional start date (YYYY-MM-DD).
        date_to: Optional end date (YYYY-MM-DD).
        session_token: Browser tab token for upload scoping.

    Returns:
        DashboardStats with all chart data.
    """
    cache_key = f"dash:{project_path or 'all'}:{date_from}:{date_to}:{session_token}"
    cached = _dashboard_cache.get(cache_key)
    if cached:
        cached_time, cached_result = cached
        if (time.monotonic() - cached_time) < CACHE_TTL_SECONDS:
            return cached_result

    trajectories, filtered_metadata = load_filtered_trajectories(
        project_path, date_from, date_to, session_token
    )
    result = compute_dashboard_stats(trajectories)
    _reconcile_session_counts(result, trajectories, filtered_metadata)
    _dashboard_cache[cache_key] = (time.monotonic(), result)
    return result


def get_tool_usage(
    project_path: str | None, date_from: str | None, date_to: str | None, session_token: str | None
) -> list[ToolUsageStat]:
    """Compute per-tool usage statistics with caching.

    Args:
        project_path: Optional project path filter.
        date_from: Optional start date (YYYY-MM-DD).
        date_to: Optional end date (YYYY-MM-DD).
        session_token: Browser tab token for upload scoping.

    Returns:
        ToolUsageStat list sorted by call_count descending.
    """
    cache_key = f"tools:{project_path or 'all'}:{date_from}:{date_to}:{session_token}"
    cached = _tool_usage_cache.get(cache_key)
    if cached:
        cached_time, cached_result = cached
        if (time.monotonic() - cached_time) < CACHE_TTL_SECONDS:
            return cached_result

    trajectories, _meta = load_filtered_trajectories(
        project_path, date_from, date_to, session_token
    )
    result = compute_tool_usage(trajectories)
    _tool_usage_cache[cache_key] = (time.monotonic(), result)
    return result


def get_session_analytics(session_id: str, session_token: str | None) -> SessionAnalytics | None:
    """Compute detailed analytics for a single session.

    Args:
        session_id: Main session identifier.
        session_token: Browser tab token for upload scoping.

    Returns:
        SessionAnalytics, or None if session not found.
    """
    group = get_store().load(session_id, session_token=session_token)
    if not group:
        return None
    return compute_session_analytics(group)


def export_dashboard_csv(
    project_path: str | None,
    date_from: str | None,
    date_to: str | None,
    session_token: str | None,
    timestamp: str,
) -> StreamingResponse:
    """Build CSV export from filtered trajectories.

    Args:
        project_path: Optional project path filter.
        date_from: Optional start date (YYYY-MM-DD).
        date_to: Optional end date (YYYY-MM-DD).
        session_token: Browser tab token for upload scoping.
        timestamp: YYYYMMDDHHMMSS string for the filename.

    Returns:
        StreamingResponse with CSV content.
    """
    trajectories, _meta = load_filtered_trajectories(
        project_path, date_from, date_to, session_token
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "session_id",
            "project_path",
            "model",
            "timestamp",
            "duration_s",
            "input_tokens",
            "output_tokens",
            "tool_calls",
            "messages",
        ]
    )

    for traj in trajectories:
        row = _build_csv_row(traj)
        writer.writerow(row)

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="vibelens-dashboard-{timestamp}.csv"',
        },
    )


def export_dashboard_json(
    project_path: str | None,
    date_from: str | None,
    date_to: str | None,
    session_token: str | None,
    timestamp: str,
) -> StreamingResponse:
    """Build JSON export with dashboard stats.

    Args:
        project_path: Optional project path filter.
        date_from: Optional start date (YYYY-MM-DD).
        date_to: Optional end date (YYYY-MM-DD).
        session_token: Browser tab token for upload scoping.
        timestamp: YYYYMMDDHHMMSS string for the filename.

    Returns:
        StreamingResponse with JSON content.
    """
    trajectories, _meta = load_filtered_trajectories(
        project_path, date_from, date_to, session_token
    )
    stats = compute_dashboard_stats(trajectories)
    payload = json.dumps(stats.model_dump(mode="json"), indent=2, ensure_ascii=False)

    return StreamingResponse(
        iter([payload]),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="vibelens-dashboard-{timestamp}.json"',
        },
    )


def _reconcile_session_counts(
    stats: DashboardStats,
    trajectories: list[Trajectory],
    metadata: list[dict],
) -> None:
    """Override session counts to include sessions that failed to parse.

    The sidebar shows all metadata entries (from skeleton parsing), but
    some sessions fail to load as full trajectories. Without reconciliation,
    the dashboard would show fewer sessions than the sidebar — confusing
    users who see N sessions listed but only M < N in the stats. This
    recomputes period counts from metadata timestamps and adds failed
    sessions to project_distribution and daily_activity.

    Args:
        stats: DashboardStats to mutate in place.
        trajectories: Successfully parsed trajectories.
        metadata: Filtered metadata list (matches sidebar count).
    """
    local_tz = datetime.now().astimezone().tzinfo
    now = datetime.now(tz=local_tz)
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    parsed_ids = {t.session_id for t in trajectories}

    year_count = month_count = week_count = 0
    for meta in metadata:
        ts = parse_metadata_timestamp(meta)
        if ts is None:
            continue
        local_ts = ts.astimezone(local_tz)
        if local_ts >= year_start:
            year_count += 1
        if local_ts >= month_start:
            month_count += 1
        if local_ts >= week_start:
            week_count += 1

        # Add failed-to-parse sessions to distributions so counts match
        session_id = meta.get("session_id", "")
        if session_id and session_id not in parsed_ids:
            project = meta.get("project_path") or "(no project)"
            date_key = local_ts.strftime("%Y-%m-%d")
            stats.project_distribution[project] = (
                stats.project_distribution.get(project, 0) + 1
            )
            stats.daily_activity[date_key] = (
                stats.daily_activity.get(date_key, 0) + 1
            )

    stats.total_sessions = len(metadata)
    stats.this_year.sessions = year_count
    stats.this_month.sessions = month_count
    stats.this_week.sessions = week_count

    safe_div = max(len(metadata), 1)
    stats.avg_messages_per_session = round(stats.total_messages / safe_div, 1)
    stats.avg_tokens_per_session = round(stats.total_tokens / safe_div, 0)
    stats.avg_tool_calls_per_session = round(stats.total_tool_calls / safe_div, 1)
    stats.avg_duration_per_session = round(stats.total_duration / safe_div, 0)


def _build_csv_row(traj: Trajectory) -> list:
    """Build a single CSV row from a trajectory."""
    input_tok = 0
    output_tok = 0
    tool_count = 0
    for step in traj.steps:
        if step.metrics:
            input_tok += step.metrics.prompt_tokens
            output_tok += step.metrics.completion_tokens
        tool_count += len(step.tool_calls)

    duration = 0
    if traj.final_metrics and traj.final_metrics.duration > 0:
        duration = traj.final_metrics.duration
    elif len(traj.steps) >= 2:
        first_ts = traj.steps[0].timestamp
        last_ts = traj.steps[-1].timestamp
        if first_ts and last_ts:
            duration = max(0, int((last_ts - first_ts).total_seconds()))

    model = (traj.agent.model_name if traj.agent else None) or ""
    if not model:
        for step in traj.steps:
            if step.model_name:
                model = step.model_name
                break

    return [
        traj.session_id,
        traj.project_path or "",
        model,
        traj.timestamp.isoformat() if traj.timestamp else "",
        duration,
        input_tok,
        output_tok,
        tool_count,
        len(traj.steps),
    ]
