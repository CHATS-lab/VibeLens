"""Persistent index cache for fast startup.

Serializes session metadata to a JSON file so subsequent startups skip
full index rebuilding when no sessions have changed. Per-session mtime
tracking lets multi-session-per-file formats (OpenCode, Kilo) detect
which exact session changed without re-parsing the whole file.
"""

import contextlib
import json
import time
from pathlib import Path

from vibelens.utils.json import atomic_write_json
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# v16 drops the legacy ``file_mtimes`` / ``path_to_session_id`` /
# ``continuation_map`` top-level fields. Per-session mtime is now embedded
# inside each entry (``session_mtime_ns``), so multi-session-per-file
# formats can detect per-session changes without a separate side table.
# v17 promotes ``is_compaction`` (Step) and ``is_skill`` (ToolCall) from
# polymorphic ``extra`` dicts to typed first-class fields. Cached entries
# from v16 still carry the old values inside ``extra`` and would render
# without the typed flag set, so we force a rebuild.
CACHE_VERSION = 17

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
        Cache dict with 'entries' and 'dropped_paths', or None.
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
    dropped_paths: dict[str, list[int]] | None = None,
    cache_path: Path | None = None,
) -> None:
    """Write the index cache to disk.

    Each entry in ``metadata_cache`` must already carry ``filepath`` and
    ``session_mtime_ns`` keys — callers stamp these before passing the
    dict in. There's no longer a separate side table for either.

    Args:
        metadata_cache: session_id -> metadata dict. Each entry must
            include ``filepath`` (str) and ``session_mtime_ns`` (int) for
            staleness detection on next startup.
        dropped_paths: file_path_str -> ``[mtime_ns, size]`` for files
            dropped as empty/invalid. Lets the next startup skip
            re-parsing them as long as their stat tuple is unchanged.
        cache_path: Path to write the cache file. Defaults to the
            module-level ``DEFAULT_CACHE_PATH`` (resolved at call time).
    """
    if cache_path is None:
        cache_path = DEFAULT_CACHE_PATH
    payload = {
        "version": CACHE_VERSION,
        "written_at": time.time(),
        "dropped_paths": dropped_paths or {},
        "entries": {sid: _compact_entry(entry) for sid, entry in metadata_cache.items()},
    }
    try:
        atomic_write_json(cache_path, payload, indent=2)
        logger.info("Wrote index cache: %d entries", len(metadata_cache))
    except OSError:
        logger.warning("Failed to write index cache to %s", cache_path)


def collect_file_mtimes(file_index: dict[str, tuple[Path, object]]) -> dict[str, list[int]]:
    """Build a filepath -> ``[mtime_ns, size]`` map from the current file index.

    Used only for the ``dropped_paths`` table now (live sessions track
    per-session mtime inside each cache entry).

    Args:
        file_index: session_id -> (filepath, parser) map.

    Returns:
        Dict of filepath string -> ``[mtime_ns, size_bytes]``.
    """
    stats: dict[str, list[int]] = {}
    for _sid, (fpath, _parser) in file_index.items():
        with contextlib.suppress(OSError):
            st = fpath.stat()
            stats[str(fpath)] = [st.st_mtime_ns, st.st_size]
    return stats
