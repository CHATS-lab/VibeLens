"""Unified catalog search: weighted per-field BM25 with sort-mode blending.

Public API:

* :func:`rank_catalog` — rank catalog items for an :class:`ExtensionQuery`.
* :func:`get_index`, :func:`reset_index`, :func:`warm_index` — index lifecycle.
* :class:`SortMode`, :class:`ExtensionQuery`, :class:`ScoredExtension` — types.
* :func:`coerce_legacy_sort` — translate deprecated sort values.

Consumers: ``services/extensions/catalog.py`` (browse UI) and
``services/recommendation/engine.py`` (L3 of the recommendation pipeline).
"""

from vibelens.services.extensions.search.index import (
    CatalogSearchIndex,
    get_index,
    reset_index,
    warm_index,
)
from vibelens.services.extensions.search.query import (
    ExtensionQuery,
    ScoredExtension,
    SortMode,
    coerce_legacy_sort,
)
from vibelens.services.extensions.search.scorer import rank_extensions


def rank_catalog(query: ExtensionQuery, top_k: int | None = None) -> list[ScoredExtension]:
    """Rank catalog extensions for the given query.

    Filters by ``extension_type`` (if set), then scores and ranks the
    remaining items per :attr:`ExtensionQuery.sort`. When the user
    typed a non-empty ``search_text``, items whose text score is zero
    are dropped — a search box is a filter, not just a reorder.

    Args:
        query: Search query with text, profile, sort, and type filter.
        top_k: Optional cap on the returned list length.

    Returns:
        Ranked list of :class:`ScoredExtension`.

    Raises:
        ValueError: If the catalog is unavailable.
    """
    index = get_index()
    profile_keywords = _extract_profile_keywords(query)
    return rank_extensions(
        index=index,
        search_text=query.search_text,
        profile_keywords=profile_keywords,
        sort=query.sort,
        type_filter=query.extension_type,
        top_k=top_k,
    )


def _extract_profile_keywords(query: ExtensionQuery) -> list[str]:
    """Extract lowercased profile keywords, or empty if no usable profile."""
    if query.profile is None:
        return []
    raw = query.profile.search_keywords or []
    return [kw.strip().lower() for kw in raw if kw and kw.strip()]


__all__ = [
    "CatalogSearchIndex",
    "ExtensionQuery",
    "ScoredExtension",
    "SortMode",
    "coerce_legacy_sort",
    "get_index",
    "rank_catalog",
    "reset_index",
    "warm_index",
]
