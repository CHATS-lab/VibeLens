"""Multi-store resolution for session lookup.

Aggregates results across per-user upload stores and the example store,
implementing store-level isolation so each user only sees their own uploads.

In self-use mode, delegates to the single LocalStore via get_store().
In demo mode, iterates the user's registered upload stores (from the
upload registry in deps.py) plus the shared example store.
"""

from vibelens.deps import get_example_store, get_store, get_upload_stores, is_demo_mode
from vibelens.utils import get_logger

logger = get_logger(__name__)


def list_all_metadata(session_token: str | None = None) -> list[dict]:
    """Return metadata visible to the given session_token.

    In self-use mode, returns metadata from the single LocalStore.
    In demo mode:
      - If the user has upload stores, returns only their uploaded sessions.
      - Otherwise, returns example sessions.

    Args:
        session_token: Browser tab UUID for per-user isolation.

    Returns:
        Combined metadata list from the user's active stores.
    """
    if not is_demo_mode():
        return list(get_store().list_metadata())

    user_stores = get_upload_stores(session_token)
    if user_stores:
        metadata: list[dict] = []
        seen_ids: set[str] = set()
        for store in user_stores:
            for m in store.list_metadata():
                sid = m.get("session_id")
                if sid and sid not in seen_ids:
                    metadata.append(m)
                    seen_ids.add(sid)
        logger.info(
            "list_all_metadata: token=%s has %d upload sessions from %d stores",
            session_token[:8] if session_token else "none",
            len(metadata),
            len(user_stores),
        )
        return metadata

    # No uploads for this token — return example sessions
    metadata = list(get_example_store().list_metadata())
    logger.info(
        "list_all_metadata: token=%s has no uploads, returning %d examples",
        session_token[:8] if session_token else "none",
        len(metadata),
    )
    return metadata


def load_from_stores(session_id: str, session_token: str | None = None) -> list | None:
    """Load a session from the user's stores, falling back to example store.

    Args:
        session_id: Session identifier to look up.
        session_token: Browser tab UUID for per-user isolation.

    Returns:
        List of Trajectory objects, or None if not found in any store.
    """
    if not is_demo_mode():
        return get_store().load(session_id)

    # Search user's upload stores first
    for store in get_upload_stores(session_token):
        result = store.load(session_id)
        if result is not None:
            return result

    # Fall back to example store
    return get_example_store().load(session_id)


def get_metadata_from_stores(session_id: str, session_token: str | None = None) -> dict | None:
    """Get metadata for a session from the user's stores or examples.

    Args:
        session_id: Session identifier to look up.
        session_token: Browser tab UUID for per-user isolation.

    Returns:
        Metadata dict, or None if not found in any accessible store.
    """
    if not is_demo_mode():
        return get_store().get_metadata(session_id)

    # Search user's upload stores first
    for store in get_upload_stores(session_token):
        meta = store.get_metadata(session_id)
        if meta is not None:
            return meta

    # Fall back to example store
    return get_example_store().get_metadata(session_id)
