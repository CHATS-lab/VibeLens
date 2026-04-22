"""Persistent index cache for fast startup.

Serializes session metadata and file mtimes to a JSON file so subsequent
startups skip full index rebuilding when no files have changed.
"""

import contextlib
import json
import time
from pathlib import Path

from vibelens.utils.json import atomic_write_json
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Bump to invalidate all existing caches after schema changes.
# v5: final_metrics.total_cost_usd is now populated during ingest (was
# None for every Claude/Hermes/Codex session prior to this version).
CACHE_VERSION = 5
# User-home path for the persistent session index cache
DEFAULT_CACHE_PATH = Path.home() / ".vibelens" / "session_index.json"

# Fields stripped from each entry before writing the cache. They are
# large (~42% of the file on observed data) and no cache reader
# consults them — anything that needs them falls through to a full
# re-parse of the source session file.
_STRIPPED_AGENT_KEYS: frozenset[str] = frozenset({"tool_definitions"})
_STRIPPED_EXTRA_KEYS: frozenset[str] = frozenset({"system_prompt"})


def _compact_entry(entry: dict) -> dict:
    """Return a copy of entry with heavy, never-read fields stripped.

    Callers must still tolerate missing keys via ``.get()`` — those
    defensive reads already exist today so no call site is affected.
    """
    out = dict(entry)
    agent = out.get("agent")
    if isinstance(agent, dict):
        out["agent"] = {k: v for k, v in agent.items() if k not in _STRIPPED_AGENT_KEYS}
    extra = out.get("extra")
    if isinstance(extra, dict):
        trimmed = {k: v for k, v in extra.items() if k not in _STRIPPED_EXTRA_KEYS}
        out["extra"] = trimmed or None
    return out


def load_cache(cache_path: Path | None = None) -> dict | None:
    """Load the persistent index cache from disk.

    Returns None if the cache file is missing, corrupt, or has an
    incompatible version — triggering a full rebuild.

    Args:
        cache_path: Path to the cache JSON file. Defaults to the
            module-level ``DEFAULT_CACHE_PATH`` (resolved at call time
            so tests can monkeypatch the module attr).

    Returns:
        Cache dict with 'entries', 'file_mtimes', 'path_to_session_id',
        'continuation_map', and 'dropped_paths', or None.
    """
    if cache_path is None:
        cache_path = DEFAULT_CACHE_PATH
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
    dropped_paths: dict[str, int] | None = None,
    cache_path: Path | None = None,
) -> None:
    """Write the index cache to disk.

    Args:
        metadata_cache: session_id -> metadata dict (from model_dump).
        file_mtimes: file_path_str -> mtime_ns for staleness detection.
        continuation_map: current_session_id -> previous_session_id.
        path_to_session_id: file_path_str -> real session_id for index remapping.
        dropped_paths: file_path_str -> mtime_ns for files dropped as empty/invalid.
            Lets the next startup skip re-parsing them as long as their mtime is
            unchanged.
        cache_path: Path to write the cache file. Defaults to the
            module-level ``DEFAULT_CACHE_PATH`` (resolved at call time).
    """
    if cache_path is None:
        cache_path = DEFAULT_CACHE_PATH
    payload = {
        "version": CACHE_VERSION,
        "written_at": time.time(),
        "file_mtimes": file_mtimes,
        "continuation_map": continuation_map,
        "path_to_session_id": path_to_session_id or {},
        "dropped_paths": dropped_paths or {},
        "entries": {sid: _compact_entry(entry) for sid, entry in metadata_cache.items()},
    }
    try:
        atomic_write_json(cache_path, payload, indent=2)
        logger.info("Wrote index cache: %d entries", len(metadata_cache))
    except OSError:
        logger.warning("Failed to write index cache to %s", cache_path)


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
