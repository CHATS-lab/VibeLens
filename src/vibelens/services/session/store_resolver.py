"""Multi-store resolution for session lookup.

Aggregates results across primary and example stores, implementing the
primary-first-then-fallback-to-examples pattern used by session CRUD,
search, dashboard, and analysis services.
"""

from vibelens.deps import get_example_store, get_store, is_demo_mode


def list_all_metadata() -> list[dict]:
    """Merge metadata from upload store and example store in demo mode.

    In self-use mode, returns metadata from the single LocalStore.
    In demo mode, combines uploads and examples, deduplicating by
    session_id (upload store wins over example store).

    Returns:
        Combined metadata list from all active stores.
    """
    metadata = list(get_store().list_metadata())
    if is_demo_mode():
        seen_ids = {m.get("session_id") for m in metadata}
        for m in get_example_store().list_metadata():
            if m.get("session_id") not in seen_ids:
                metadata.append(m)
    return metadata


def load_from_stores(session_id: str) -> list | None:
    """Load a session from the primary store, falling back to example store.

    Args:
        session_id: Session identifier to look up.

    Returns:
        List of Trajectory objects, or None if not found in any store.
    """
    result = get_store().load(session_id)
    if result is None and is_demo_mode():
        result = get_example_store().load(session_id)
    return result


def get_metadata_from_stores(session_id: str) -> dict | None:
    """Get metadata for a session from any active store.

    Args:
        session_id: Session identifier to look up.

    Returns:
        Metadata dict, or None if not found in any store.
    """
    meta = get_store().get_metadata(session_id)
    if meta is None and is_demo_mode():
        meta = get_example_store().get_metadata(session_id)
    return meta
