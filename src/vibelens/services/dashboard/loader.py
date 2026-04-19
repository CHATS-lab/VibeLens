"""Dashboard service — trajectory loading, caching, and reconciliation."""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

from cachetools import TTLCache

from vibelens.models.dashboard.dashboard import (
    DashboardStats,
    SessionAnalytics,
    SessionToolUsage,
    ToolUsageStat,
)
from vibelens.models.trajectories import Trajectory
from vibelens.services.dashboard.analytics import compute_session_analytics
from vibelens.services.dashboard.stats import (
    compute_dashboard_stats,
    compute_dashboard_stats_from_metadata,
    filter_metadata,
)
from vibelens.services.dashboard.tool_usage import (
    aggregate_tool_usage,
    compute_per_session_tool_usage,
    compute_tool_usage,
)
from vibelens.services.dashboard.tool_usage_cache import (
    load_cache as load_tool_usage_cache,
)
from vibelens.services.dashboard.tool_usage_cache import (
    save_cache as save_tool_usage_cache,
)
from vibelens.services.inference_shared import CACHE_MAXSIZE, CACHE_TTL_SECONDS
from vibelens.services.session.store_resolver import (
    get_metadata_from_stores,
    list_all_metadata,
    load_from_stores,
)
from vibelens.utils import get_logger
from vibelens.utils.timestamps import parse_metadata_timestamp

logger = get_logger(__name__)

# Thread pool size for parallel session loading during cache warming.
# Each load is I/O-bound (JSONL file read + JSON parsing), so we use
# many more threads than CPU cores to maximize I/O overlap.
WARM_MAX_WORKERS = min((os.cpu_count() or 4) * 4, 32)

_dashboard_cache: TTLCache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL_SECONDS)
_tool_usage_cache: TTLCache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL_SECONDS)

# Warming progress visible to the status API.
# Updated atomically by _load_sessions_parallel; read by get_warming_status().
_warming_progress: dict = {"total": 0, "loaded": 0, "done": True}


def load_filtered_trajectories(
    project_path: str | None,
    date_from: str | None,
    date_to: str | None,
    session_token: str | None,
    agent_name: str | None = None,
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
        agent_name: Optional agent name filter.

    Returns:
        Tuple of (loaded trajectories, filtered metadata list).
    """
    metadata = list_all_metadata(session_token)
    filtered = filter_metadata(metadata, project_path, date_from, date_to, agent_name)
    trajectories = _load_and_enrich_trajectories(filtered, session_token)
    return trajectories, filtered


def get_dashboard_stats(
    project_path: str | None,
    date_from: str | None,
    date_to: str | None,
    session_token: str | None,
    agent_name: str | None = None,
) -> DashboardStats:
    """Compute dashboard stats with caching and session count reconciliation.

    Uses enriched metadata when available to avoid loading full trajectories.
    Falls back to full trajectory loading if metadata lacks enriched metrics.

    Args:
        project_path: Optional project path filter.
        date_from: Optional start date (YYYY-MM-DD).
        date_to: Optional end date (YYYY-MM-DD).
        session_token: Browser tab token for upload scoping.
        agent_name: Optional agent name filter.

    Returns:
        DashboardStats with all chart data.
    """
    cache_key = (
        f"dash:{project_path or 'all'}:{date_from}:{date_to}:{session_token}:{agent_name or 'all'}"
    )
    if cache_key in _dashboard_cache:
        return _dashboard_cache[cache_key]

    metadata = list_all_metadata(session_token)
    filtered = filter_metadata(metadata, project_path, date_from, date_to, agent_name)

    if _has_enriched_metrics(filtered):
        result = compute_dashboard_stats_from_metadata(filtered)
    else:
        trajectories, filtered = load_filtered_trajectories(
            project_path, date_from, date_to, session_token, agent_name
        )
        result = compute_dashboard_stats(trajectories)
        _reconcile_session_counts(result, trajectories, filtered)

    result.cached_at = datetime.now().astimezone().isoformat()
    _dashboard_cache[cache_key] = result
    return result


def get_tool_usage(
    project_path: str | None,
    date_from: str | None,
    date_to: str | None,
    session_token: str | None,
    agent_name: str | None = None,
) -> list[ToolUsageStat]:
    """Compute per-tool usage statistics with caching.

    Args:
        project_path: Optional project path filter.
        date_from: Optional start date (YYYY-MM-DD).
        date_to: Optional end date (YYYY-MM-DD).
        session_token: Browser tab token for upload scoping.
        agent_name: Optional agent name filter.

    Returns:
        ToolUsageStat list sorted by call_count descending.
    """
    cache_key = (
        f"tools:{project_path or 'all'}:{date_from}:{date_to}:{session_token}:{agent_name or 'all'}"
    )
    if cache_key in _tool_usage_cache:
        return _tool_usage_cache[cache_key]

    trajectories, _meta = load_filtered_trajectories(
        project_path, date_from, date_to, session_token, agent_name
    )
    result = compute_tool_usage(trajectories)
    _tool_usage_cache[cache_key] = result
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


def get_warming_status() -> dict:
    """Return current cache warming progress for the status API.

    Returns:
        Dict with total, loaded, and done fields.
    """
    return dict(_warming_progress)


def warm_cache() -> None:
    """Pre-compute global dashboard stats and tool usage into cache.

    Dashboard stats are computed from enriched metadata (fast-scanned token
    counts) without loading full trajectories.

    Tool usage now uses a per-session persisted cache: only sessions whose
    source-file mtime changed since the last warm are reloaded. On warm
    restarts where nothing changed, this completes in ~50ms (load JSON +
    aggregate). On cold start, the cache is empty and we recompute from
    scratch — same wall-clock cost as the legacy single-pass.
    """
    _warming_progress.update(total=0, loaded=0, done=False)
    logger.info("Warming dashboard cache...")
    cache_key_dash = "dash:all:None:None:None:all"
    cache_key_tools = "tools:all:None:None:None:all"

    metadata = list_all_metadata(session_token=None)
    filtered = filter_metadata(metadata, None, None, None)

    if _has_enriched_metrics(filtered):
        stats = compute_dashboard_stats_from_metadata(filtered)
        logger.info("Dashboard stats computed from metadata (no file I/O)")
    else:
        trajectories, _meta = load_filtered_trajectories(None, None, None, None)
        stats = compute_dashboard_stats(trajectories)
        _reconcile_session_counts(stats, trajectories, filtered)
    _dashboard_cache[cache_key_dash] = stats

    cached_entries = load_tool_usage_cache()
    current_targets = _build_tool_usage_targets(filtered)
    stale_or_missing = {
        sid: mtime
        for sid, mtime in current_targets.items()
        if cached_entries.get(sid) is None
        or cached_entries[sid].content_mtime_ns != mtime
    }
    drop_sids = set(cached_entries) - set(current_targets)

    if drop_sids:
        for sid in drop_sids:
            cached_entries.pop(sid, None)

    if stale_or_missing:
        logger.info(
            "Tool-usage warming: %d/%d sessions need recompute",
            len(stale_or_missing),
            len(current_targets),
        )
        _recompute_into_cache(cached_entries, stale_or_missing)
    else:
        logger.info("Tool-usage warming: cache hit, no recompute needed")

    save_tool_usage_cache(cached_entries)

    _tool_usage_cache[cache_key_tools] = aggregate_tool_usage(cached_entries)

    _warming_progress["done"] = True
    logger.info("Dashboard cache warmed")


def _build_tool_usage_targets(metadata: list[dict]) -> dict[str, int]:
    """Stat each session's source file and return session_id -> mtime_ns.

    Sessions whose filepath is missing or unstat-able are skipped — they
    won't appear in the cache and any prior entry will be dropped on the
    next warm.
    """
    targets: dict[str, int] = {}
    for meta in metadata:
        sid = meta.get("session_id")
        fpath = meta.get("filepath")
        if not sid or not fpath:
            continue
        try:
            targets[sid] = Path(fpath).stat().st_mtime_ns
        except OSError:
            continue
    return targets


def _recompute_into_cache(
    entries: dict, stale_or_missing: dict[str, int]
) -> None:
    """Load each stale session's trajectory and update its entry.

    Mutates ``entries`` in place and ticks ``_warming_progress``. Reuses
    :func:`_load_one_session` which wraps the existing load_from_stores
    error handling.
    """
    items = list(stale_or_missing.items())
    total = len(items)
    _warming_progress.update(total=total, loaded=0)
    done_count = 0

    with ThreadPoolExecutor(max_workers=WARM_MAX_WORKERS) as pool:
        futures = {
            pool.submit(_load_one_session, {"session_id": sid}, sid, None): (sid, mtime)
            for sid, mtime in items
        }
        for future in as_completed(futures):
            sid, mtime = futures[future]
            done_count += 1
            _warming_progress["loaded"] = done_count
            try:
                traj = future.result()
            except Exception:
                logger.warning("Tool-usage warm: failed to load %s", sid, exc_info=True)
                traj = None
            if traj is None:
                entries[sid] = SessionToolUsage(content_mtime_ns=mtime, no_trajectory=True)
            else:
                entries[sid] = compute_per_session_tool_usage(traj, content_mtime_ns=mtime)
            if done_count % 50 == 0 or done_count == total:
                logger.info(
                    "Tool-usage warming progress: %d/%d sessions",
                    done_count,
                    total,
                )


def _load_and_enrich_trajectories(
    metadata: list[dict], session_token: str | None, parallel: bool = False
) -> list[Trajectory]:
    """Load trajectories from metadata, enriching project_path from skeleton data.

    When ``parallel=True``, uses a thread pool to load sessions concurrently.
    Each session load is I/O-bound (JSONL file read + JSON parsing), so
    threads provide near-linear speedup.

    Args:
        metadata: Filtered metadata list with session_ids to load.
        session_token: Browser tab token for upload scoping.
        parallel: If True, load sessions using a thread pool.

    Returns:
        List of loaded Trajectory objects.
    """
    valid_metadata = [(meta, meta.get("session_id", "")) for meta in metadata]
    valid_metadata = [(meta, sid) for meta, sid in valid_metadata if sid]
    total = len(valid_metadata)

    if not valid_metadata:
        return []

    if not parallel:
        return _load_sessions_sequential(valid_metadata, session_token, total)
    return _load_sessions_parallel(valid_metadata, session_token, total)


def _load_one_session(meta: dict, session_id: str, session_token: str | None) -> Trajectory | None:
    """Load a single session and enrich its project_path.

    Args:
        meta: Metadata dict for the session.
        session_id: Session identifier.
        session_token: Browser tab token for upload scoping.

    Returns:
        Enriched Trajectory, or None on failure.
    """
    try:
        group = load_from_stores(session_id, session_token)
        if group:
            traj = group[0]
            if not traj.project_path:
                traj.project_path = meta.get("project_path")
            return traj
    except Exception:
        logger.warning("Failed to load session %s, skipping", session_id, exc_info=True)
    return None


def _load_sessions_sequential(
    valid_metadata: list[tuple[dict, str]], session_token: str | None, total: int
) -> list[Trajectory]:
    """Load sessions one at a time (used for non-warming requests)."""
    trajectories: list[Trajectory] = []
    for meta, sid in valid_metadata:
        traj = _load_one_session(meta, sid, session_token)
        if traj:
            trajectories.append(traj)
    return trajectories


def _load_sessions_parallel(
    valid_metadata: list[tuple[dict, str]], session_token: str | None, total: int
) -> list[Trajectory]:
    """Load sessions concurrently using a thread pool."""
    _warming_progress.update(total=total, loaded=0)
    trajectories: list[Trajectory] = []
    done_count = 0

    with ThreadPoolExecutor(max_workers=WARM_MAX_WORKERS) as pool:
        futures = {
            pool.submit(_load_one_session, meta, sid, session_token): sid
            for meta, sid in valid_metadata
        }
        for future in as_completed(futures):
            done_count += 1
            _warming_progress["loaded"] = done_count
            traj = future.result()
            if traj:
                trajectories.append(traj)
            if done_count % 50 == 0 or done_count == total:
                logger.info("Cache warming progress: %d/%d sessions loaded", done_count, total)

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
