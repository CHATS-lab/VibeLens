"""Disk-based trajectory storage.

Persists parsed trajectories as JSON files on disk.
Each session gets a ``{session_id}.json`` file with the full trajectory
group. A single ``index.jsonl`` file per directory holds one summary
line per session for fast listing without opening every JSON file.

Uses rglob to discover all ``index.jsonl`` files under the root
directory, so sessions saved to subdirectories (e.g. by upload service)
are found automatically.
"""

import json
import shutil
from pathlib import Path

from vibelens.ingest.parsers.parsed import ParsedTrajectoryParser
from vibelens.models.trajectories import Trajectory
from vibelens.storage.conversation.base import TrajectoryStore
from vibelens.utils import get_logger

logger = get_logger(__name__)

INDEX_FILENAME = "index.jsonl"


class DiskStore(TrajectoryStore):
    """File-system trajectory store.

    Saves and loads trajectories as JSON files under a single root
    directory. The ``_build_index`` method discovers all ``index.jsonl``
    files via rglob, including those in upload subdirectories.

    Inherits concrete read methods (list_metadata, load, exists, etc.)
    from TrajectoryStore.
    """

    def __init__(self, root: Path, default_tags: dict | None = None) -> None:
        super().__init__()
        self._root = root
        self._parser = ParsedTrajectoryParser()
        self._default_tags = default_tags or {}

    @property
    def root(self) -> Path:
        """Base directory for stored sessions."""
        return self._root

    def initialize(self) -> None:
        """Create the root directory."""
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, trajectories: list[Trajectory]) -> None:
        """Write a trajectory group to disk and append to the JSONL index.

        Args:
            trajectories: Related trajectories (main + sub-agents).
        """
        main = trajectories[0]
        session_id = main.session_id
        summary = main.to_summary()

        if self._default_tags:
            summary.update(self._default_tags)

        self._root.mkdir(parents=True, exist_ok=True)

        full_path = self._root / f"{session_id}.json"
        full_data = [t.model_dump(mode="json") for t in trajectories]
        full_path.write_text(
            json.dumps(full_data, indent=2, default=str, ensure_ascii=False), encoding="utf-8"
        )

        # Append summary to the JSONL index (atomic per-line append)
        index_path = self._root / INDEX_FILENAME
        with open(index_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary, default=str, ensure_ascii=False) + "\n")

        logger.info(
            "DiskStore.save: session=%s file=%s index=%s tags=%s",
            session_id,
            full_path,
            index_path,
            self._default_tags,
        )

        # Incremental cache update (skip full rebuild)
        if self._metadata_cache is not None:
            self._metadata_cache[session_id] = summary
            self._index[session_id] = (full_path, self._parser)
            if self._all_metadata is not None:
                self._all_metadata.append(summary)

    def copy_to_dir(self, session_id: str, dest_dir: Path) -> None:
        """Copy a session's .json file to the given directory.

        Args:
            session_id: Session to copy.
            dest_dir: Destination directory (must already exist).

        Raises:
            FileNotFoundError: If session does not exist on disk.
        """
        self._ensure_index()
        entry = self._index.get(session_id)
        if not entry:
            raise FileNotFoundError(f"Session not found: {session_id}")
        source = entry[0]
        shutil.copy2(str(source), str(dest_dir / f"{session_id}.json"))

    def _build_index(self) -> None:
        """Build metadata index by reading all index.jsonl files recursively."""
        self._index = {}
        self._metadata_cache = {}
        self._all_metadata = []

        if not self._root.exists():
            logger.info("DiskStore._build_index: root does not exist: %s", self._root)
            return

        # Sort so newer upload directories (timestamp-prefixed names) are
        # read last and win the session_id dedup for get_metadata()/load().
        index_files = sorted(self._root.rglob(INDEX_FILENAME))
        logger.info(
            "DiskStore._build_index: root=%s found %d index files", self._root, len(index_files)
        )

        for index_path in index_files:
            parent_dir = index_path.parent
            entries = _iter_jsonl(index_path)
            logger.info("DiskStore._build_index: %s has %d entries", index_path, len(entries))
            for line in entries:
                sid = line.get("session_id")
                if not sid:
                    continue
                self._metadata_cache[sid] = line
                self._index[sid] = (parent_dir / f"{sid}.json", self._parser)
                self._all_metadata.append(line)

        logger.info("DiskStore._build_index: total sessions indexed: %d", len(self._index))


def _iter_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file and return parsed dicts, skipping invalid lines.

    Args:
        path: Path to the JSONL file.

    Returns:
        List of parsed JSON dicts.
    """
    results: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    results.append(json.loads(stripped))
                except json.JSONDecodeError:
                    logger.warning("Skipping invalid JSON line in %s", path.name)
    except OSError as exc:
        logger.warning("Cannot read index file %s: %s", path, exc)
    return results
