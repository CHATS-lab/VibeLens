"""Share service for managing shareable session links via a registry file."""

import json
from datetime import UTC, datetime
from pathlib import Path

from vibelens.models.trajectories import Trajectory
from vibelens.schemas.share import ShareMeta
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Max chars extracted from the first user message for the share title
FIRST_MESSAGE_MAX_LENGTH = 120
# Fallback title when no user message is available
DEFAULT_SHARE_TITLE = "Shared Session"
# JSON file tracking all shared session IDs under share_dir
REGISTRY_FILENAME = "shared.json"


class ShareService:
    """Manages a registry of shared session IDs.

    Shares are tracked in a single ``shared.json`` file under ``share_dir``.
    No trajectory data is copied — shared sessions are loaded from the normal
    trajectory store at read time.
    """

    def __init__(self, share_dir: Path):
        self._dir = share_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._registry_path = self._dir / REGISTRY_FILENAME
        self._registry: dict[str, ShareMeta] = self._load()
        self._last_mtime: float = self._file_mtime()

    def _file_mtime(self) -> float:
        """Return the registry file's modification time, or 0 if missing."""
        try:
            return self._registry_path.stat().st_mtime
        except FileNotFoundError:
            return 0.0

    def _refresh_if_stale(self) -> None:
        """Re-read registry from disk if another process modified it."""
        mtime = self._file_mtime()
        if mtime > self._last_mtime:
            self._registry = self._load()
            self._last_mtime = mtime
            logger.info("Share registry refreshed from disk (%d entries)", len(self._registry))

    def share(self, session_id: str, title: str) -> ShareMeta:
        """Mark a session as shared and persist the registry.

        Args:
            session_id: Session identifier to share.
            title: Display title for the shared session.

        Returns:
            ShareMeta for the newly shared session.
        """
        now = datetime.now(UTC)
        meta = ShareMeta(session_id=session_id, title=title, created_at=now)
        self._registry[session_id] = meta
        self._save()
        logger.info("Shared session %s", session_id)
        return meta

    def unshare(self, session_id: str) -> bool:
        """Remove a session from the shared registry.

        Args:
            session_id: Session identifier to unshare.

        Returns:
            True if the session was shared and is now removed.
        """
        if session_id not in self._registry:
            return False
        del self._registry[session_id]
        self._save()
        logger.info("Unshared session %s", session_id)
        return True

    def is_shared(self, session_id: str) -> bool:
        """Check whether a session is currently shared."""
        self._refresh_if_stale()
        return session_id in self._registry

    def get_meta(self, session_id: str) -> ShareMeta | None:
        """Return share metadata for a session, or None if not shared."""
        self._refresh_if_stale()
        return self._registry.get(session_id)

    def list_shared(self) -> list[ShareMeta]:
        """List all shared sessions sorted by creation time (newest first).

        Returns:
            List of ShareMeta objects.
        """
        self._refresh_if_stale()
        entries = list(self._registry.values())
        entries.sort(key=lambda m: m.created_at, reverse=True)
        return entries

    def _save(self) -> None:
        """Persist the registry to disk and update cached mtime."""
        payload = [m.model_dump(mode="json") for m in self._registry.values()]
        self._registry_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self._last_mtime = self._file_mtime()

    def _load(self) -> dict[str, ShareMeta]:
        """Load the registry from disk."""
        if not self._registry_path.exists():
            return {}
        try:
            raw = json.loads(self._registry_path.read_text(encoding="utf-8"))
            entries = [ShareMeta.model_validate(item) for item in raw]
            return {m.session_id: m for m in entries}
        except (json.JSONDecodeError, ValueError):
            logger.warning("Corrupt share registry at %s, starting fresh", self._registry_path)
            return {}


def extract_title(trajectories: list[Trajectory]) -> str:
    """Extract a display title from the first trajectory's first_message."""
    if not trajectories:
        return DEFAULT_SHARE_TITLE
    first = trajectories[0]
    if first.first_message:
        msg = first.first_message.strip()
        if len(msg) > FIRST_MESSAGE_MAX_LENGTH:
            return msg[:FIRST_MESSAGE_MAX_LENGTH] + "..."
        return msg
    return DEFAULT_SHARE_TITLE
