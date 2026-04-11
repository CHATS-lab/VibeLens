"""Persistent index cache for fast startup.

Serializes session metadata and file mtimes to a JSON file so subsequent
startups skip full index rebuilding. Only files whose mtime changed since
the last cache write are re-parsed.
"""

import contextlib
import json
import time
from pathlib import Path

from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Bump to invalidate all existing caches after schema changes
CACHE_VERSION = 1
# User-home path for the persistent session index cache
DEFAULT_CACHE_PATH = Path.home() / ".vibelens" / "session_index.json"


def load_cache(cache_path: Path = DEFAULT_CACHE_PATH) -> dict | None:
    """Load the persistent index cache from disk.

    Returns None if the cache file is missing, corrupt, or has an
    incompatible version — triggering a full rebuild.

    Args:
        cache_path: Path to the cache JSON file.

    Returns:
        Cache dict with 'entries' and 'continuation_map', or None.
    """
    if not cache_path.exists():
        return None
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        if raw.get("version") != CACHE_VERSION:
            logger.info("Index cache version mismatch, will rebuild")
            return None
        return raw
    except (json.JSONDecodeError, OSError, KeyError):
        logger.debug("Index cache unreadable, will rebuild")
        return None


def save_cache(
    metadata_cache: dict[str, dict],
    file_mtimes: dict[str, float],
    continuation_map: dict[str, str],
    path_to_session_id: dict[str, str] | None = None,
    cache_path: Path = DEFAULT_CACHE_PATH,
) -> None:
    """Write the index cache to disk.

    Args:
        metadata_cache: session_id -> metadata dict (from model_dump).
        file_mtimes: file_path_str -> mtime_ns for staleness detection.
        continuation_map: current_session_id -> previous_session_id.
        path_to_session_id: file_path_str -> real session_id for index remapping.
        cache_path: Path to write the cache file.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "written_at": time.time(),
        "file_mtimes": file_mtimes,
        "continuation_map": continuation_map,
        "path_to_session_id": path_to_session_id or {},
        "entries": metadata_cache,
    }
    try:
        cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Wrote index cache: %d entries", len(metadata_cache))
    except OSError:
        logger.warning("Failed to write index cache to %s", cache_path)


def detect_stale_files(
    file_index: dict[str, tuple[Path, object]], cached_mtimes: dict[str, float]
) -> tuple[set[str], set[str]]:
    """Compare current file mtimes against cached values.

    Args:
        file_index: Current session_id -> (filepath, parser) map.
        cached_mtimes: filepath_str -> mtime from the previous cache.

    Returns:
        Tuple of (stale_session_ids, removed_session_ids).
        stale = files that changed or are new.
        removed = files in cache but no longer on disk.
    """
    stale: set[str] = set()
    current_paths: set[str] = set()

    for sid, (fpath, _parser) in file_index.items():
        path_str = str(fpath)
        current_paths.add(path_str)
        try:
            current_mtime = fpath.stat().st_mtime_ns
        except OSError:
            stale.add(sid)
            continue
        cached_mtime = cached_mtimes.get(path_str)
        if cached_mtime is None or current_mtime != cached_mtime:
            stale.add(sid)

    # Sessions in cache whose files no longer exist
    cached_path_set = set(cached_mtimes.keys())
    removed_paths = cached_path_set - current_paths
    # Map removed paths back to session IDs via the cached entries
    # (caller handles this since we don't have the reverse mapping here)

    return stale, removed_paths


def collect_file_mtimes(file_index: dict[str, tuple[Path, object]]) -> dict[str, float]:
    """Build a filepath -> mtime_ns map from the current file index.

    Args:
        file_index: session_id -> (filepath, parser) map.

    Returns:
        Dict of filepath string -> mtime in nanoseconds.
    """
    mtimes: dict[str, float] = {}
    for _sid, (fpath, _parser) in file_index.items():
        with contextlib.suppress(OSError):
            mtimes[str(fpath)] = fpath.stat().st_mtime_ns
    return mtimes
