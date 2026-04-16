"""Sender-side donation history reader.

Each row in {settings.donation.dir}/sent.jsonl carries a
``session_token_hash`` field so that multi-user demo servers can
expose only the entries belonging to the requesting browser. Raw
session tokens are never persisted.
"""

import hashlib
import json
from pathlib import Path

from vibelens.deps import get_settings
from vibelens.schemas.session import DonationHistoryEntry
from vibelens.services.donation import SENDER_INDEX_FILENAME
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


def hash_token(token: str) -> str:
    """Return the sha256 hex digest of ``token``.

    Args:
        token: Raw browser session token.

    Returns:
        64-character hex digest used as an equality key in the history file.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def sender_index_path() -> Path:
    """Return the path to the sender-side history file."""
    return get_settings().donation.dir / SENDER_INDEX_FILENAME


def list_for_token(token: str | None, limit: int = 100) -> list[DonationHistoryEntry]:
    """Return donations associated with ``token``, newest first.

    Empty or missing tokens never match any entry (privacy-safe default).
    Missing history file → empty list. Malformed lines are skipped with a
    log warning.

    Args:
        token: Raw session token from the ``X-Session-Token`` header.
        limit: Maximum number of entries to return.

    Returns:
        DonationHistoryEntry objects ordered by ``donated_at`` descending.
    """
    if not token:
        return []

    path = sender_index_path()
    if not path.exists():
        return []

    target_hash = hash_token(token)
    matched: list[DonationHistoryEntry] = []

    with open(path, encoding="utf-8") as fh:
        for raw_line in fh:
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                logger.warning("Skipping invalid line in %s", path.name)
                continue
            if data.get("session_token_hash") != target_hash:
                continue
            try:
                entry = DonationHistoryEntry.model_validate(
                    {
                        "donation_id": data["donation_id"],
                        "session_count": data["session_count"],
                        "donated_at": data["donated_at"],
                    }
                )
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed entry in %s: %s", path.name, exc)
                continue
            matched.append(entry)

    matched.sort(key=lambda e: e.donated_at, reverse=True)
    return matched[:limit]
