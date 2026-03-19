"""Demo mode startup — load example trajectories into the store."""

import json
from pathlib import Path

from vibelens.config.settings import Settings
from vibelens.ingest.discovery import discover_all_session_files
from vibelens.ingest.fingerprint import parse_auto
from vibelens.models.trajectories import Trajectory
from vibelens.stores.disk import DiskStore
from vibelens.utils import get_logger

logger = get_logger(__name__)


def load_demo_examples(settings: Settings, store: DiskStore) -> int:
    """Parse configured example paths and save via the disk store.

    Each path can be either a JSON file (array of Trajectory dicts) or
    a directory containing raw session files to auto-detect and parse.

    Args:
        settings: Application settings with example_session_paths.
        store: DiskStore to persist trajectories.

    Returns:
        Number of sessions loaded.
    """
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

    Args:
        dir_path: Directory containing raw session files.
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
            if trajectories:
                loaded += _save_trajectories(trajectories, store)
        except ValueError as exc:
            logger.warning("Skipping %s: %s", file_path.name, exc)
    return loaded


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
    store.save(main.session_id, trajectories, main.to_summary())
    return 1
