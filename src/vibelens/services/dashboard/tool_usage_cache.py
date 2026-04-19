"""Persistent per-session tool-usage cache.

Stores ``{session_id: SessionToolUsage}`` so the dashboard's tool-usage
warming step can skip re-loading trajectories on warm restarts. Only
sessions whose source-file mtime has changed (or that are new since the
previous warm) need to be recomputed.
"""

import json
import time
from pathlib import Path

from pydantic import ValidationError

from vibelens.models.dashboard.dashboard import SessionToolUsage
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

CACHE_VERSION = 1
DEFAULT_CACHE_PATH = Path.home() / ".vibelens" / "tool_usage_cache.json"


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


def save_cache(
    entries: dict[str, SessionToolUsage], cache_path: Path | None = None
) -> None:
    """Write the tool-usage cache to disk atomically.

    Args:
        entries: session_id -> SessionToolUsage to persist.
        cache_path: Override path. Defaults to module-level
            ``DEFAULT_CACHE_PATH``.
    """
    if cache_path is None:
        cache_path = DEFAULT_CACHE_PATH
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "written_at": time.time(),
        "entries": {sid: entry.model_dump(mode="json") for sid, entry in entries.items()},
    }
    tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    try:
        tmp_path.write_text(json.dumps(payload), encoding="utf-8")
        tmp_path.replace(cache_path)
        logger.info("Wrote tool-usage cache: %d entries", len(entries))
    except OSError:
        logger.warning("Failed to write tool-usage cache to %s", cache_path)
