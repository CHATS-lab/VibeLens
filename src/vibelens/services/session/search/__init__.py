"""Two-tier session search with ranked results.

Public API mirrors the previous ``services.session.search`` module so
callers in ``app.py``, ``api/sessions.py``, and
``services/upload/processor.py`` flip over with a single import change.
The response shape *does* change: ``search_sessions`` now returns
:class:`ScoredSession` pairs, not a flat list of session ids.
"""

from vibelens.services.session.search.index import SessionSearchIndex
from vibelens.services.session.search.query import ScoredSession

# Module-level singleton: one search index per process, shared by every
# caller of build_search_index / search_sessions / refresh_search_index.
_index = SessionSearchIndex()


def build_search_index(session_token: str | None = None) -> None:
    """Build Tier 1 (metadata) search index. Fast, for startup."""
    _index.build_from_metadata(session_token)


def build_full_search_index(session_token: str | None = None) -> None:
    """Build Tier 2 (full text) search index. Slow, for background."""
    _index.build_full(session_token)


def search_sessions(
    query: str,
    session_token: str | None = None,
    top_k: int | None = None,
) -> list[ScoredSession]:
    """Search sessions. Returns BM25F-ranked ``ScoredSession`` entries.

    When Tier 2 is ready, ranking uses the session_id tier plus BM25F
    composite. Before Tier 2 finishes building (the first ~24 s after
    startup), results fall back to Tier 1 substring matching over
    session_id + first_message, with score ``0.0`` placeholders so the
    response shape is stable.

    Args:
        query: Raw user query. Empty returns ``[]``.
        session_token: Browser tab token for demo-mode per-tab scoping.
        top_k: Optional cap on returned results.

    Returns:
        Ordered list of matches, best first. Empty list when nothing
        matches or when the query is empty.
    """
    if not query:
        return []

    hits = _index.search_full(query, top_k=top_k)
    if hits is None:
        # Tier 2 not ready yet — fall back to metadata substring match.
        hits = _index.search_metadata(query)
        if top_k is not None:
            hits = hits[:top_k]
    return [ScoredSession(session_id=sid, composite_score=score) for sid, score in hits]


def invalidate_search_index() -> None:
    """Clear Tier 2, preserving Tier 1 metadata index."""
    _index.invalidate()


def add_sessions_to_index(session_ids: list[str], session_token: str | None = None) -> None:
    """Incrementally add new sessions to the search index after upload."""
    _index.add_sessions(session_ids, session_token)


def refresh_search_index(session_token: str | None = None) -> None:
    """Incremental diff-based refresh for periodic background task."""
    _index.refresh(session_token)


def get_session_index() -> SessionSearchIndex:
    """Return the module-level singleton index. Exposed for tests."""
    return _index


__all__ = [
    "ScoredSession",
    "SessionSearchIndex",
    "add_sessions_to_index",
    "build_full_search_index",
    "build_search_index",
    "get_session_index",
    "invalidate_search_index",
    "refresh_search_index",
    "search_sessions",
]
