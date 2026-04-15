"""Demo mode startup — load example trajectories into the store."""

import contextlib
import json
from pathlib import Path

from vibelens.config.settings import Settings
from vibelens.deps import get_settings
from vibelens.ingest.discovery import discover_all_session_files
from vibelens.ingest.parsers import LOCAL_PARSER_CLASSES
from vibelens.ingest.parsers.base import (
    MAX_FIRST_MESSAGE_LENGTH,
    BaseParser,
    _is_meaningful_prompt,
)
from vibelens.ingest.parsers.dataclaw import DataclawParser
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Trajectory
from vibelens.storage.trajectory.disk import INDEX_FILENAME, DiskTrajectoryStore
from vibelens.utils import get_logger

logger = get_logger(__name__)

_ALL_PARSERS: list[type[BaseParser]] = [*LOCAL_PARSER_CLASSES, DataclawParser]


def _has_cached_examples(root: Path) -> bool:
    """Check if previously cached example trajectories exist.

    Args:
        root: DiskStore root directory.

    Returns:
        True if the JSONL index file exists.
    """
    return (root / INDEX_FILENAME).exists()


def load_demo_examples(settings: Settings, store: DiskTrajectoryStore) -> int:
    """Parse configured example paths and save via the disk store.

    On subsequent startups, skips parsing entirely when a cached
    index.jsonl is found in the store root directory.

    Each path can be either a JSON file (array of Trajectory dicts) or
    a directory containing raw session files to auto-detect and parse.

    Args:
        settings: Application settings with example_session_paths.
        store: DiskStore to persist trajectories.

    Returns:
        Number of sessions loaded.
    """
    if _has_cached_examples(store.root):
        store.invalidate_index()
        count = store.session_count()
        logger.info("Skipping parse — %d cached examples found", count)
        return count

    loaded = 0
    for example_path in settings.demo.session_paths:
        if not example_path.exists():
            logger.warning("Example path not found: %s", example_path)
            continue
        logger.info("Loading example from %s", example_path)
        try:
            if example_path.is_dir():
                loaded += _load_directory(example_path, store)
            else:
                loaded += _load_json_file(example_path, store)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load example %s: %s", example_path.name, exc)
    return loaded


def _load_json_file(file_path: Path, store: DiskTrajectoryStore) -> int:
    """Load pre-parsed trajectories from a JSON array file.

    Args:
        file_path: Path to a JSON file containing a trajectory array.
        store: DiskStore to persist trajectories.

    Returns:
        Number of sessions stored.
    """
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        logger.warning("Expected JSON array in %s", file_path.name)
        return 0
    trajectories = [Trajectory(**item) for item in raw]
    return _save_trajectories(trajectories, store)


def _load_directory(dir_path: Path, store: DiskTrajectoryStore) -> int:
    """Discover and parse raw session files from a directory.

    Tries each known parser; falls back to loading pre-parsed
    ATIF trajectory JSON for files that don't match any raw format.

    Args:
        dir_path: Directory containing raw session files or ATIF JSON.
        store: DiskStore to persist parsed trajectories.

    Returns:
        Number of sessions stored.
    """
    session_files = discover_all_session_files(dir_path)
    if not session_files:
        logger.warning("No session files found in %s", dir_path)
        return 0

    loaded = 0
    for file_path in session_files:
        trajectories = _try_parse_with_all(file_path) or _try_load_atif_json(file_path)
        if trajectories:
            loaded += _save_trajectories(trajectories, store)
    return loaded


def _try_parse_with_all(file_path: Path) -> list[Trajectory]:
    """Try parsing a file with each known parser, returning the first success.

    Args:
        file_path: Path to a session file.

    Returns:
        Parsed trajectories, or empty list if no parser succeeds.
    """
    for parser_cls in _ALL_PARSERS:
        try:
            result = parser_cls().parse_file(file_path)
            if result:
                return result
        except Exception:
            continue
    return []


def _try_load_atif_json(file_path: Path) -> list[Trajectory]:
    """Try loading a JSON file as a pre-parsed ATIF trajectory.

    Handles both a single trajectory dict and an array of dicts.
    Returns an empty list if the file is not a valid trajectory.

    Args:
        file_path: Path to a JSON file.

    Returns:
        List of Trajectory objects, empty if not ATIF format.
    """
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Skipping %s: %s", file_path.name, exc)
        return []

    items = raw if isinstance(raw, list) else [raw]
    trajectories: list[Trajectory] = []
    for item in items:
        if not isinstance(item, dict) or "steps" not in item:
            continue
        try:
            traj = Trajectory(**item)
            trajectories.append(traj)
        except (ValueError, TypeError) as exc:
            logger.warning("Invalid trajectory in %s: %s", file_path.name, exc)
    return trajectories


def _fix_first_message(traj: Trajectory) -> None:
    """Recompute first_message from steps if current value is not a real user prompt.

    Pre-parsed ATIF files may have stale first_message pointing to system
    or skill content. This scans steps for the first meaningful user prompt.

    Args:
        traj: Trajectory to fix in-place.
    """
    if traj.first_message and _is_meaningful_prompt(traj.first_message):
        return
    for step in traj.steps:
        if step.source != StepSource.USER:
            continue
        if step.extra and (step.extra.get("is_skill_output") or step.extra.get("is_auto_prompt")):
            continue
        if isinstance(step.message, str) and _is_meaningful_prompt(step.message):
            text = step.message
            if len(text) > MAX_FIRST_MESSAGE_LENGTH:
                text = text[:MAX_FIRST_MESSAGE_LENGTH] + "..."
            traj.first_message = text
            return


def _save_trajectories(trajectories: list[Trajectory], store: DiskTrajectoryStore) -> int:
    """Save a list of trajectories to the store.

    Uses the first trajectory's session_id as the storage key
    and its summary as the metadata sidecar.

    Args:
        trajectories: Parsed trajectory objects from one file.
        store: DiskStore to persist.

    Returns:
        1 if stored, 0 if empty.
    """
    if not trajectories:
        return 0
    main = next((t for t in trajectories if not t.parent_trajectory_ref), trajectories[0])
    _fix_first_message(main)
    store.save(trajectories)
    return 1


def seed_example_analyses() -> None:
    """Copy pre-built example analyses into the user's analysis stores.

    Looks for bundled example analyses adjacent to the configured example
    session paths (e.g. examples/recipe-book/friction_analyses/). Only
    copies when the target store is empty to avoid overwriting user data.
    """
    settings = get_settings()
    for example_path in settings.demo.session_paths:
        if not example_path.is_dir():
            continue
        _copy_example_store(
            example_path / "friction_analyses",
            settings.storage.friction_dir,
            "friction",
        )
        _copy_example_store(
            example_path / "personalization",
            settings.storage.personalization_dir,
            "personalization",
        )


def _copy_example_store(src_dir: Path, dst_dir: Path, label: str) -> None:
    """Copy example analysis files from a bundled directory into the user store.

    Appends example entries alongside any existing user analyses. Skips
    individual files that already exist in the destination to avoid
    overwriting user data or duplicating on repeated startups.

    Args:
        src_dir: Bundled example analyses directory.
        dst_dir: User's analysis store directory.
        label: Human-readable label for logging.
    """
    src_index = src_dir / "index.jsonl"
    if not src_dir.is_dir() or not src_index.exists():
        return

    dst_dir.mkdir(parents=True, exist_ok=True)
    copied = _copy_example_json_files(src_dir, dst_dir)
    if copied == 0:
        return

    dst_index = dst_dir / "index.jsonl"
    existing_ids = _read_existing_analysis_ids(dst_index)
    _append_example_index_entries(src_index, dst_index, existing_ids)
    logger.info("Seeded %d example %s analysis files", copied, label)


def _copy_example_json_files(src_dir: Path, dst_dir: Path) -> int:
    """Copy .json analysis files from src to dst, injecting is_example flag.

    Skips files already present in the destination.

    Args:
        src_dir: Source directory with example analyses.
        dst_dir: Destination user store directory.

    Returns:
        Number of files copied.
    """
    copied = 0
    for src_file in src_dir.iterdir():
        if src_file.suffix != ".json" or (dst_dir / src_file.name).exists():
            continue
        with contextlib.suppress(json.JSONDecodeError, OSError):
            data = json.loads(src_file.read_text(encoding="utf-8"))
            data["is_example"] = True
            (dst_dir / src_file.name).write_text(json.dumps(data, indent=2), encoding="utf-8")
            copied += 1
    return copied


def _read_existing_analysis_ids(index_path: Path) -> set[str]:
    """Read analysis_id values from an existing JSONL index file.

    Args:
        index_path: Path to the destination index.jsonl.

    Returns:
        Set of analysis_id strings already present.
    """
    existing_ids: set[str] = set()
    if not index_path.exists():
        return existing_ids
    for line in index_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        with contextlib.suppress(json.JSONDecodeError, ValueError):
            existing_ids.add(json.loads(line).get("analysis_id", ""))
    return existing_ids


def _append_example_index_entries(src_index: Path, dst_index: Path, existing_ids: set[str]) -> None:
    """Append new example entries to the destination index, skipping duplicates.

    Args:
        src_index: Source example index.jsonl.
        dst_index: Destination user index.jsonl.
        existing_ids: Analysis IDs already in the destination.
    """
    new_lines: list[str] = []
    for line in src_index.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        with contextlib.suppress(json.JSONDecodeError, ValueError):
            entry = json.loads(line)
            if entry.get("analysis_id", "") not in existing_ids:
                entry["is_example"] = True
                new_lines.append(json.dumps(entry))

    if new_lines:
        with dst_index.open("a", encoding="utf-8") as f:
            for line in new_lines:
                f.write(line + "\n")
