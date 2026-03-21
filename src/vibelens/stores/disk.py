"""Disk-based trajectory storage.

Persists parsed trajectories as JSON files on disk.
Each session gets two files:
  - {session_id}.json       full trajectory group (list[Trajectory])
  - {session_id}.meta.json  main trajectory without steps (fast listing)
"""

import json
import shutil
from pathlib import Path

from vibelens.models.trajectories import Trajectory
from vibelens.stores.base import TrajectoryStore
from vibelens.utils import get_logger

logger = get_logger(__name__)


class DiskStore(TrajectoryStore):
    """File-system trajectory store.

    Implements TrajectoryStore for read operations and provides write methods
    for saving parsed trajectories.

    Pre-loaded example sessions live under ``root`` (e.g.
    ``datasets/redteam/parsed/``).  User uploads are stored under a
    separate ``upload_root`` (e.g. ``datasets/``) so each upload gets
    a clean top-level directory like ``datasets/{upload_id}/``.

    Args:
        root: Base directory for pre-loaded example sessions.
        upload_root: Base directory for user uploads. Defaults to root.
    """

    def __init__(self, root: Path, upload_root: Path | None = None) -> None:
        self._root = root
        self._upload_root = upload_root or root
        self._token_uploads: dict[str, set[str]] = {}

    @property
    def root(self) -> Path:
        """Base directory for pre-loaded example sessions."""
        return self._root

    @property
    def upload_root(self) -> Path:
        """Base directory for user uploads."""
        return self._upload_root

    def initialize(self) -> None:
        """Create the root directory."""
        self._root.mkdir(parents=True, exist_ok=True)

    def register_upload(self, session_token: str, upload_id: str) -> None:
        """Associate an upload subdirectory with a browser session token.

        Args:
            session_token: Browser tab UUID from X-Session-Token header.
            upload_id: Upload subdirectory name under root.
        """
        self._token_uploads.setdefault(session_token, set()).add(upload_id)

    def save(
        self,
        session_id: str,
        trajectories: list[Trajectory],
        summary: dict,
        subdir: str | None = None,
    ) -> None:
        """Write a trajectory group to disk as .json and .meta.json.

        When ``subdir`` is provided (user upload), the full trajectory
        goes into ``{upload_root}/{subdir}/parsed/`` and the lightweight
        meta sidecar stays at ``{upload_root}/{subdir}/``.

        Args:
            session_id: Storage key (typically the main trajectory's session_id).
            trajectories: Related trajectories (main + sub-agents).
            summary: Pre-built summary dict for the meta sidecar file.
            subdir: Optional subdirectory under upload_root (e.g. an upload_id).
        """
        if subdir:
            meta_dir = self._upload_root / subdir
            full_dir = meta_dir / "parsed"
        else:
            meta_dir = self._root
            full_dir = self._root

        meta_dir.mkdir(parents=True, exist_ok=True)
        full_dir.mkdir(parents=True, exist_ok=True)

        full_path = full_dir / f"{session_id}.json"
        meta_path = meta_dir / f"{session_id}.meta.json"

        full_data = [t.model_dump(mode="json") for t in trajectories]
        full_path.write_text(
            json.dumps(full_data, indent=2, default=str, ensure_ascii=False), encoding="utf-8"
        )

        meta_path.write_text(
            json.dumps(summary, indent=2, default=str, ensure_ascii=False), encoding="utf-8"
        )

    def list_metadata(self, session_token: str | None = None) -> list[dict]:
        """Read .meta.json files scoped by session token.

        Root-level meta files (demo examples) are always included.
        Upload subdirectories under upload_root are only included when
        the token owns them.

        Args:
            session_token: Browser tab token. None returns root-level only.

        Returns:
            List of trajectory summary dicts (no steps), unsorted.
        """
        summaries: list[dict] = []

        # Root-level files are always visible (demo examples)
        for meta_file in self._root.glob("*.meta.json"):
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                summaries.append(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping corrupt meta file %s: %s", meta_file.name, exc)

        # Upload subdirectories under upload_root: only include if token owns them
        allowed_uploads = self._token_uploads.get(session_token, set()) if session_token else set()
        if self._upload_root.exists():
            for upload_dir in self._upload_root.iterdir():
                if not upload_dir.is_dir() or upload_dir.name.startswith("."):
                    continue
                if upload_dir.name not in allowed_uploads:
                    continue
                for meta_file in upload_dir.glob("*.meta.json"):
                    try:
                        data = json.loads(meta_file.read_text(encoding="utf-8"))
                        summaries.append(data)
                    except (json.JSONDecodeError, OSError) as exc:
                        logger.warning("Skipping corrupt meta file %s: %s", meta_file.name, exc)

        return summaries

    def load(self, session_id: str, session_token: str | None = None) -> list[Trajectory] | None:
        """Load a full trajectory group from disk, scoped by session token.

        Root-level sessions are always accessible. Upload subdirectory sessions
        require the token to own the upload.

        Args:
            session_id: Main session identifier.
            session_token: Browser tab token for upload access control.

        Returns:
            List of Trajectory objects, or None if not found.
        """
        full_path = self._find_session_file(session_id, session_token)
        if not full_path:
            return None
        try:
            raw = json.loads(full_path.read_text(encoding="utf-8"))
            return [Trajectory(**item) for item in raw]
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning("Failed to load trajectory %s: %s", session_id, exc)
            return None

    def list_projects(self) -> list[str]:
        """Extract unique project paths from all metadata files.

        Returns:
            Sorted list of project path strings.
        """
        summaries = self.list_metadata()
        return sorted({s["project_path"] for s in summaries if s.get("project_path")})

    def copy_to_dir(
        self, session_id: str, dest_dir: Path, session_token: str | None = None
    ) -> None:
        """Copy a session's .json file to the given directory.

        Args:
            session_id: Session to copy.
            dest_dir: Destination directory (must already exist).
            session_token: Browser tab token for upload access control.

        Raises:
            FileNotFoundError: If session does not exist on disk.
        """
        source = self._find_session_file(session_id, session_token)
        if not source:
            raise FileNotFoundError(f"Session not found: {session_id}")
        dest = dest_dir / f"{session_id}.json"
        shutil.copy2(str(source), str(dest))

    def _find_session_file(self, session_id: str, session_token: str | None = None) -> Path | None:
        """Locate a session JSON file, respecting token-based access control.

        Root-level files (demo examples) are always accessible. Upload
        subdirectory files under upload_root require the token to own
        the upload directory.

        Args:
            session_id: Session identifier to search for.
            session_token: Browser tab token for upload access control.

        Returns:
            Path to the session file, or None if not found/accessible.
        """
        root_path = self._root / f"{session_id}.json"
        if root_path.exists():
            return root_path

        allowed_uploads = self._token_uploads.get(session_token, set()) if session_token else set()
        if self._upload_root.exists():
            for upload_dir in self._upload_root.iterdir():
                if not upload_dir.is_dir() or upload_dir.name.startswith("."):
                    continue
                if upload_dir.name not in allowed_uploads:
                    continue
                candidate = upload_dir / "parsed" / f"{session_id}.json"
                if candidate.exists():
                    return candidate

        return None
