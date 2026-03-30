"""Stateless upload visibility filtering.

Visibility is determined entirely from session metadata tags:
- ``_upload_id``: present on uploaded sessions, absent on example sessions.
- ``_session_token``: the browser UUID that uploaded the session.

No in-memory state. Every call is a pure function of the metadata.
"""

from vibelens.utils import get_logger

logger = get_logger(__name__)


def filter_visible(summaries: list[dict], session_token: str | None) -> list[dict]:
    """Filter metadata summaries to those visible to the given token.

    Visibility rules:
    1. Token matches ``_session_token`` in metadata -> visible (user's own upload)
    2. No ``_upload_id`` in metadata -> visible (example session)
    3. Otherwise -> hidden (another user's upload)

    When a token owns uploads, only those uploads are shown (not examples).
    When a token has no uploads, only examples are shown.

    Args:
        summaries: List of trajectory summary dicts.
        session_token: Browser tab UUID, or None.

    Returns:
        Filtered list of visible summaries.
    """
    if not session_token:
        result = [s for s in summaries if not s.get("_upload_id")]
        logger.info(
            "filter_visible: no token, returning %d example sessions of %d total",
            len(result),
            len(summaries),
        )
        return result

    owned = [s for s in summaries if s.get("_session_token") == session_token]
    if owned:
        logger.info(
            "filter_visible: token=%s owns %d sessions, returning those",
            session_token[:8],
            len(owned),
        )
        return owned

    result = [s for s in summaries if not s.get("_upload_id")]
    logger.info(
        "filter_visible: token=%s has no uploads, returning %d examples of %d total",
        session_token[:8],
        len(result),
        len(summaries),
    )
    return result


def is_session_visible(meta: dict | None, session_token: str | None) -> bool:
    """Check if a single session is visible to the given token.

    Args:
        meta: Session metadata dict (may contain ``_upload_id``, ``_session_token``).
        session_token: Browser tab UUID, or None.

    Returns:
        True if the session is visible.
    """
    if not meta:
        return False

    upload_id = meta.get("_upload_id")
    token_tag = meta.get("_session_token")

    if not session_token:
        return not upload_id

    if token_tag:
        return token_tag == session_token

    return not upload_id
