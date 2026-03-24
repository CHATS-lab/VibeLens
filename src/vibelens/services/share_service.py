"""Share service for creating and managing shareable session links."""

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

from vibelens.models.trajectories import Trajectory
from vibelens.schemas.share import ShareMeta
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

SHARE_TOKEN_BYTES = 12
FIRST_MESSAGE_MAX_LENGTH = 120
DEFAULT_SHARE_TITLE = "Shared session"


class ShareService:
    """Manages shared session snapshots on disk.

    Each share produces two files under ``share_dir``:
    - ``{token}.json``      — full trajectory array (same as export)
    - ``{token}.meta.json`` — lightweight metadata (token, session_id, title, created_at)
    """

    def __init__(self, share_dir: Path):
        self._dir = share_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _data_path(self, token: str) -> Path:
        return self._dir / f"{token}.json"

    def _meta_path(self, token: str) -> Path:
        return self._dir / f"{token}.meta.json"

    def create(self, session_id: str, trajectories: list[Trajectory]) -> ShareMeta:
        """Snapshot a session and return share metadata.

        Args:
            session_id: Original session identifier.
            trajectories: Full trajectory list to snapshot.

        Returns:
            ShareMeta with generated token and extracted title.
        """
        token = secrets.token_urlsafe(SHARE_TOKEN_BYTES)
        title = _extract_title(trajectories)
        now = datetime.now(UTC)

        payload = [t.model_dump(mode="json") for t in trajectories]
        self._data_path(token).write_text(
            json.dumps(payload, indent=2, default=str, ensure_ascii=False),
            encoding="utf-8",
        )

        meta = ShareMeta(token=token, session_id=session_id, title=title, created_at=now)
        self._meta_path(token).write_text(
            meta.model_dump_json(indent=2),
            encoding="utf-8",
        )

        logger.info("Created share %s for session %s", token, session_id)
        return meta

    def load(self, token: str) -> list[dict] | None:
        """Load shared trajectory data by token.

        Args:
            token: Share token to look up.

        Returns:
            Parsed trajectory list, or None if not found.
        """
        path = self._data_path(token)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def load_meta(self, token: str) -> ShareMeta | None:
        """Load share metadata by token.

        Args:
            token: Share token to look up.

        Returns:
            ShareMeta, or None if not found.
        """
        path = self._meta_path(token)
        if not path.exists():
            return None
        return ShareMeta.model_validate_json(path.read_text(encoding="utf-8"))

    def delete(self, token: str) -> bool:
        """Remove a shared session snapshot.

        Args:
            token: Share token to revoke.

        Returns:
            True if files were deleted, False if token not found.
        """
        data_path = self._data_path(token)
        meta_path = self._meta_path(token)
        if not data_path.exists() and not meta_path.exists():
            return False
        data_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        logger.info("Deleted share %s", token)
        return True

    def list_shares(self) -> list[ShareMeta]:
        """List all existing shares sorted by creation time (newest first).

        Returns:
            List of ShareMeta objects.
        """
        shares: list[ShareMeta] = []
        for meta_path in self._dir.glob("*.meta.json"):
            try:
                meta = ShareMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
                shares.append(meta)
            except (json.JSONDecodeError, ValueError):
                logger.warning("Skipping corrupt share metadata: %s", meta_path)
        shares.sort(key=lambda m: m.created_at, reverse=True)
        return shares


def _extract_title(trajectories: list[Trajectory]) -> str:
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
