"""Per-tool usage statistics computation.

Aggregates tool call counts, per-session averages, and error rates
across trajectories for the dashboard tool usage breakdown. Also
hosts the persistent per-session cache used by warm restarts.
"""

import json
import time
from collections import defaultdict
from pathlib import Path

from pydantic import ValidationError

from vibelens.models.dashboard.dashboard import SessionToolUsage, ToolUsageStat
from vibelens.models.trajectories import Step, Trajectory
from vibelens.utils import get_logger
from vibelens.utils.json import atomic_write_json

logger = get_logger(__name__)

CACHE_VERSION = 1
DEFAULT_CACHE_PATH = Path.home() / ".vibelens" / "tool_usage_cache.json"


def compute_per_session_tool_usage(traj: Trajectory, content_mtime_ns: int) -> SessionToolUsage:
    """Count tool invocations and observation errors for a single trajectory.

    Args:
        traj: Fully loaded Trajectory.
        content_mtime_ns: mtime of the source file (recorded in the result so
            future warm restarts can decide whether to recompute).

    Returns:
        SessionToolUsage with tool_counts and error_counts populated.
    """
    tool_counts: dict[str, int] = defaultdict(int)
    error_counts: dict[str, int] = defaultdict(int)

    for step in traj.steps:
        for tc in step.tool_calls:
            tool_counts[tc.function_name] += 1
        if step.observation:
            _count_observation_errors(step, error_counts)

    return SessionToolUsage(
        content_mtime_ns=content_mtime_ns,
        tool_counts=dict(tool_counts),
        error_counts=dict(error_counts),
        no_trajectory=False,
    )


def aggregate_tool_usage(entries: dict[str, SessionToolUsage]) -> list[ToolUsageStat]:
    """Aggregate per-session tool-usage records into the dashboard stat list.

    Skips entries flagged ``no_trajectory``. ``avg_per_session`` is averaged
    over the count of valid sessions, matching the legacy
    :func:`compute_tool_usage` denominator.

    Args:
        entries: session_id -> SessionToolUsage.

    Returns:
        ToolUsageStat list sorted by call_count descending.
    """
    valid_entries = [e for e in entries.values() if not e.no_trajectory]
    session_count = len(valid_entries)
    if session_count == 0:
        return []

    tool_counts: dict[str, int] = defaultdict(int)
    error_counts: dict[str, int] = defaultdict(int)
    for entry in valid_entries:
        for name, count in entry.tool_counts.items():
            tool_counts[name] += count
        for name, count in entry.error_counts.items():
            error_counts[name] += count

    stats = []
    for tool_name, count in tool_counts.items():
        errors = error_counts.get(tool_name, 0)
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


def compute_tool_usage(trajectories: list[Trajectory]) -> list[ToolUsageStat]:
    """Compute per-tool usage statistics from full trajectories.

    Legacy single-pass aggregator; kept for callers that load trajectories
    directly. New code paths should prefer
    :func:`compute_per_session_tool_usage` + :func:`aggregate_tool_usage`
    so per-session results can be cached.

    Args:
        trajectories: Fully loaded Trajectory objects.

    Returns:
        ToolUsageStat list sorted by call_count descending.
    """
    entries = {
        traj.session_id: compute_per_session_tool_usage(traj, content_mtime_ns=0)
        for traj in trajectories
    }
    return aggregate_tool_usage(entries)


def _count_observation_errors(step: Step, tool_errors: dict[str, int]) -> None:
    """Count error results and attribute them to tool calls."""
    if not step.observation:
        return

    call_map = {tc.tool_call_id: tc.function_name for tc in step.tool_calls}

    for result in step.observation.results:
        if result.is_error:
            func_name = call_map.get(result.source_call_id or "", "")
            if func_name:
                tool_errors[func_name] += 1


def load_cache(cache_path: Path | None = None) -> dict[str, SessionToolUsage]:
    """Load the persistent tool-usage cache from disk.

    Returns an empty dict if the cache file is missing, corrupt, or has
    an incompatible version. Callers can treat that as "everything stale"
    and recompute from scratch.

    Args:
        cache_path: Override path. Defaults to module-level
            ``DEFAULT_CACHE_PATH``, resolved at call time.

    Returns:
        session_id -> SessionToolUsage mapping.
    """
    if cache_path is None:
        cache_path = DEFAULT_CACHE_PATH
    if not cache_path.exists():
        return {}
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.debug("Tool-usage cache unreadable, will rebuild")
        return {}
    if raw.get("version") != CACHE_VERSION:
        logger.info("Tool-usage cache version mismatch, will rebuild")
        return {}

    entries: dict[str, SessionToolUsage] = {}
    for sid, payload in raw.get("entries", {}).items():
        try:
            entries[sid] = SessionToolUsage.model_validate(payload)
        except ValidationError:
            logger.debug("Skipping unparseable tool-usage cache entry for %s", sid)
            continue
    return entries


def save_cache(entries: dict[str, SessionToolUsage], cache_path: Path | None = None) -> None:
    """Write the tool-usage cache to disk atomically.

    Args:
        entries: session_id -> SessionToolUsage to persist.
        cache_path: Override path. Defaults to module-level
            ``DEFAULT_CACHE_PATH``.
    """
    if cache_path is None:
        cache_path = DEFAULT_CACHE_PATH
    payload = {
        "version": CACHE_VERSION,
        "written_at": time.time(),
        "entries": {sid: entry.model_dump(mode="json") for sid, entry in entries.items()},
    }
    try:
        atomic_write_json(cache_path, payload)
        logger.info("Wrote tool-usage cache: %d entries", len(entries))
    except OSError:
        logger.warning("Failed to write tool-usage cache to %s", cache_path)
