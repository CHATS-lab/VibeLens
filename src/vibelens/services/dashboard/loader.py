"""Dashboard service — trajectory loading, caching, and reconciliation."""

import time
from datetime import datetime, timedelta

from vibelens.models.dashboard.dashboard import (
    DashboardStats,
    SessionAnalytics,
    ToolUsageStat,
)
from vibelens.models.trajectories import Trajectory
from vibelens.services.dashboard.analytics import compute_session_analytics
from vibelens.services.dashboard.stats import (
    compute_dashboard_stats,
    compute_dashboard_stats_from_metadata,
    filter_metadata,
)
from vibelens.services.dashboard.tool_usage import compute_tool_usage
from vibelens.services.session.store_resolver import (
    get_metadata_from_stores,
    list_all_metadata,
    load_from_stores,
)
from vibelens.utils import get_logger
from vibelens.utils.timestamps import parse_metadata_timestamp

logger = get_logger(__name__)

# Cache TTL balances freshness with cost of full trajectory loading.
# 1 hour avoids redundant recomputation during normal browsing
# while still reflecting newly uploaded sessions within a reasonable window.
CACHE_TTL_SECONDS = 3600

# Number of sessions to load per batch during cache warming.
# After each batch, the thread sleeps briefly to release the GIL
# so the event loop can serve other requests (friction history, LLM status).
WARM_BATCH_SIZE = 20
WARM_YIELD_SECONDS = 0.01

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
    metadata = list_all_metadata(session_token)
    filtered = filter_metadata(metadata, project_path, date_from, date_to)

    trajectories = []
    for meta in filtered:
        session_id = meta.get("session_id", "")
        if not session_id:
            continue
        try:
            group = load_from_stores(session_id, session_token)
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

    Uses enriched metadata when available to avoid loading full trajectories.
    Falls back to full trajectory loading if metadata lacks enriched metrics.

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

    metadata = list_all_metadata(session_token)
    filtered = filter_metadata(metadata, project_path, date_from, date_to)

    if _has_enriched_metrics(filtered):
        result = compute_dashboard_stats_from_metadata(filtered)
    else:
        trajectories, filtered = load_filtered_trajectories(
            project_path, date_from, date_to, session_token
        )
        result = compute_dashboard_stats(trajectories)
        _reconcile_session_counts(result, trajectories, filtered)

    result.cached_at = datetime.now().astimezone().isoformat()
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
    if get_metadata_from_stores(session_id, session_token) is None:
        return None
    group = load_from_stores(session_id, session_token)
    if not group:
        return None
    return compute_session_analytics(group)


def warm_cache() -> None:
    """Pre-compute global dashboard stats and tool usage into cache.

    Dashboard stats use enriched metadata (fast-scanned token counts)
    to avoid loading full trajectories. Tool usage still requires full
    trajectories since it needs per-tool function names.

    Sessions are loaded in batches of WARM_BATCH_SIZE with brief
    GIL-releasing sleeps between batches so the event loop can serve
    other endpoints (friction history, LLM status) concurrently.
    """
    logger.info("Warming dashboard cache...")
    cache_key_dash = "dash:all:None:None:None"
    cache_key_tools = "tools:all:None:None:None"

    metadata = list_all_metadata(session_token=None)
    filtered = filter_metadata(metadata, None, None, None)

    # Dashboard stats from enriched metadata (no full trajectory loading)
    if _has_enriched_metrics(filtered):
        stats = compute_dashboard_stats_from_metadata(filtered)
        logger.info("Dashboard stats computed from metadata (no file I/O)")
    else:
        trajectories, _meta = load_filtered_trajectories(None, None, None, None)
        stats = compute_dashboard_stats(trajectories)
        _reconcile_session_counts(stats, trajectories, filtered)
    _dashboard_cache[cache_key_dash] = (time.monotonic(), stats)

    # Tool usage requires full trajectories — load in batches to yield GIL
    trajectories = _load_trajectories_yielding(filtered)
    usage = compute_tool_usage(trajectories)
    _tool_usage_cache[cache_key_tools] = (time.monotonic(), usage)

    logger.info("Dashboard cache warmed")


def _load_trajectories_yielding(metadata: list[dict]) -> list[Trajectory]:
    """Load trajectories in batches, sleeping between batches to release the GIL.

    When called from a background thread, the brief sleep between batches
    allows the async event loop to serve other requests. Without this,
    continuous JSON parsing of hundreds of sessions monopolizes the GIL
    and blocks lightweight endpoints like /friction/history and /llm/status.

    Args:
        metadata: Filtered metadata list with session_ids to load.

    Returns:
        List of loaded Trajectory objects.
    """
    trajectories: list[Trajectory] = []

    for i, meta in enumerate(metadata):
        session_id = meta.get("session_id", "")
        if not session_id:
            continue
        try:
            group = load_from_stores(session_id)
            if group:
                traj = group[0]
                if not traj.project_path:
                    traj.project_path = meta.get("project_path")
                trajectories.append(traj)
        except Exception:
            logger.warning("Failed to load session %s during cache warming", session_id)

        # Release the GIL between batches so the event loop can run
        if (i + 1) % WARM_BATCH_SIZE == 0:
            time.sleep(WARM_YIELD_SECONDS)

    return trajectories


def _has_enriched_metrics(metadata: list[dict]) -> bool:
    """Check if metadata has enriched final_metrics from fast scanning.

    Returns True if at least one entry has non-zero token counts,
    indicating the metadata was enriched by fast_metrics scanning.
    """
    for meta in metadata[:10]:
        fm = meta.get("final_metrics") or {}
        if fm.get("total_prompt_tokens") or fm.get("total_completion_tokens"):
            return True
    return False


def invalidate_cache() -> None:
    """Clear all cached dashboard data, forcing recomputation on next request."""
    _dashboard_cache.clear()
    _tool_usage_cache.clear()
    logger.info("Dashboard cache invalidated")


def _reconcile_session_counts(
    stats: DashboardStats, trajectories: list[Trajectory], metadata: list[dict]
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
            stats.project_distribution[project] = stats.project_distribution.get(project, 0) + 1
            stats.daily_activity[date_key] = stats.daily_activity.get(date_key, 0) + 1

    stats.total_sessions = len(metadata)
    stats.this_year.sessions = year_count
    stats.this_month.sessions = month_count
    stats.this_week.sessions = week_count

    safe_div = max(len(metadata), 1)
    stats.avg_messages_per_session = round(stats.total_messages / safe_div, 1)
    stats.avg_tokens_per_session = round(stats.total_tokens / safe_div, 0)
    stats.avg_tool_calls_per_session = round(stats.total_tool_calls / safe_div, 1)
    stats.avg_duration_per_session = round(stats.total_duration / safe_div, 0)
