"""Demo mode startup — load example trajectories into the store."""

import json
from pathlib import Path

from vibelens.config.settings import Settings
from vibelens.ingest.discovery import discover_all_session_files
from vibelens.ingest.fingerprint import parse_auto
from vibelens.ingest.parsers.base import MAX_FIRST_MESSAGE_LENGTH, _is_meaningful_prompt
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Trajectory
from vibelens.storage.disk import DiskStore
from vibelens.utils import get_logger

logger = get_logger(__name__)


def _has_cached_examples(root: Path) -> bool:
    """Check if previously cached example trajectories exist.

    Args:
        root: DiskStore root directory.

    Returns:
        True if at least one .meta.json sidecar file is present.
    """
    if not root.exists():
        return False
    return any(root.glob("*.meta.json"))


def load_demo_examples(settings: Settings, store: DiskStore) -> int:
    """Parse configured example paths and save via the disk store.

    On subsequent startups, skips parsing entirely when cached .meta.json
    files are found in the store root directory.

    Each path can be either a JSON file (array of Trajectory dicts) or
    a directory containing raw session files to auto-detect and parse.

    Args:
        settings: Application settings with example_session_paths.
        store: DiskStore to persist trajectories.

    Returns:
        Number of sessions loaded.
    """
    if _has_cached_examples(store.root):
        cached = list(store.root.glob("*.meta.json"))
        logger.info("Skipping parse — %d cached examples found", len(cached))
        return len(cached)

    loaded = 0
    for example_path in settings.example_session_paths:
        if not example_path.exists():
            logger.warning("Example path not found: %s", example_path)
            continue
        try:
            if example_path.is_dir():
                loaded += _load_directory(example_path, store)
            else:
                loaded += _load_json_file(example_path, store)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load example %s: %s", example_path.name, exc)
    return loaded


def _load_json_file(file_path: Path, store: DiskStore) -> int:
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


def _load_directory(dir_path: Path, store: DiskStore) -> int:
    """Discover and parse raw session files from a directory.

    Tries auto-detection first; falls back to loading pre-parsed
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
        try:
            trajectories = parse_auto(file_path)
        except ValueError:
            trajectories = _try_load_atif_json(file_path)
        if trajectories:
            loaded += _save_trajectories(trajectories, store)
    return loaded


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
        if step.extra and step.extra.get("is_skill_output"):
            continue
        if isinstance(step.message, str) and _is_meaningful_prompt(step.message):
            text = step.message
            if len(text) > MAX_FIRST_MESSAGE_LENGTH:
                text = text[:MAX_FIRST_MESSAGE_LENGTH] + "..."
            traj.first_message = text
            return


def _save_trajectories(trajectories: list[Trajectory], store: DiskStore) -> int:
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
    store.save(main.session_id, trajectories, main.to_summary())
    return 1
