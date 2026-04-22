"""Sort-mode-aware composite scoring over the catalog search index.

The ranking has two layers:

1. **Tier** (name-match strength): exact-name > all-tokens-are-name-tokens >
   name-substring > other. Tier dominates ordering — a tier-3 item always
   ranks above a tier-2 item, regardless of BM25 composite. This is how
   users expect search boxes to behave ("I typed the name, why isn't it
   first?").
2. **Within-tier composite**: blended BM25 text + profile + quality +
   popularity + recency, weighted per :class:`SortMode`.

Hot path is vectorized with numpy; per-token presence checks use
precomputed posting lists from the index.
"""

import re

import numpy as np

from vibelens.models.enums import AgentExtensionType
from vibelens.services.extensions.search.index import CatalogSearchIndex
from vibelens.services.extensions.search.query import ScoredExtension, SortMode
from vibelens.services.search import score_text_query
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Composite weight vectors: each row is {signal: weight} summing to 1.0.
# Tunable constants; validated by scripts/eval_search.py before ship.
WEIGHTS_BY_MODE: dict[SortMode, dict[str, float]] = {
    SortMode.DEFAULT: {
        "text": 0.30,
        "profile": 0.20,
        "quality": 0.30,
        "popularity": 0.10,
        "recency": 0.10,
    },
    SortMode.PERSONALIZED: {
        "text": 0.20,
        "profile": 0.50,
        "quality": 0.20,
        "popularity": 0.05,
        "recency": 0.05,
    },
    SortMode.QUALITY: {
        "text": 0.20,
        "profile": 0.00,
        "quality": 0.80,
        "popularity": 0.00,
        "recency": 0.00,
    },
    SortMode.RECENT: {
        "text": 0.20,
        "profile": 0.00,
        "quality": 0.00,
        "popularity": 0.00,
        "recency": 0.80,
    },
    # NAME is a special case: alphabetical within tier, no composite blending.
}

_RAW_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Name-match score bands. Higher is better; bands are scaled so that any
# exact match outranks any all-tokens match, which outranks any partial
# token match, which outranks a substring match, which outranks nothing.
_NAME_SCORE_EXACT = 1000
_NAME_SCORE_ALL_TOKENS = 500
_NAME_SCORE_PARTIAL_TOKEN = 10  # per token matched
_NAME_SCORE_SUBSTR = 1


def rank_extensions(
    index: CatalogSearchIndex,
    search_text: str,
    profile_keywords: list[str],
    sort: SortMode,
    type_filter: AgentExtensionType | None = None,
    top_k: int | None = None,
) -> list[ScoredExtension]:
    """Score and rank extensions with tiered name-match + composite blend.

    Args:
        index: The built catalog search index.
        search_text: Raw user-typed query. Empty OK.
        profile_keywords: UserProfile.search_keywords, lowercased upstream.
        sort: Which weight vector to apply.
        type_filter: Optional type filter applied before scoring.
        top_k: Optional cap on returned results.

    Returns:
        Ranked list of :class:`ScoredExtension` sorted descending.
    """
    n = index.num_items()
    if n == 0:
        return []

    selected = _type_mask(index, type_filter, n)
    if not selected.any():
        return []

    has_text = bool(search_text.strip())
    name_scores = _name_match_tiers(index, search_text) if has_text else np.zeros(n, dtype=np.int32)

    text_scores = (
        score_text_query(index.inverted, search_text, expand_last_as_prefix=True)
        if has_text
        else np.zeros(n, dtype=np.float32)
    )

    # When the user typed a query, drop items that match nothing anywhere.
    if has_text:
        matched = (name_scores > 0) | (text_scores > 0)
        selected = selected & matched
        if not selected.any():
            return []

    if sort is SortMode.NAME:
        return _build_results(index, selected, name_scores, text_scores, top_k, alpha_tiebreak=True)

    profile_scores = (
        score_text_query(index.inverted, " ".join(profile_keywords), expand_last_as_prefix=False)
        if profile_keywords
        else np.zeros(n, dtype=np.float32)
    )

    present: set[str] = {"quality", "popularity", "recency"}
    if has_text:
        present.add("text")
    if profile_keywords:
        present.add("profile")
    weights = _effective_weights(WEIGHTS_BY_MODE[sort], present)
    composite = (
        weights["text"] * text_scores
        + weights["profile"] * profile_scores
        + weights["quality"] * index.quality_signal
        + weights["popularity"] * index.popularity_signal
        + weights["recency"] * index.recency_signal
    )

    return _build_results(
        index,
        selected,
        name_scores,
        text_scores,
        top_k,
        composite=composite,
        profile_scores=profile_scores,
        weights=weights,
    )


def _type_mask(
    index: CatalogSearchIndex, type_filter: AgentExtensionType | None, n: int
) -> np.ndarray:
    """Return a boolean mask selecting items that pass the optional type filter."""
    if type_filter is None:
        return np.ones(n, dtype=bool)
    mask = index.type_mask.get(type_filter)
    if mask is None:
        return np.zeros(n, dtype=bool)
    return mask.copy()


def _name_match_tiers(index: CatalogSearchIndex, search_text: str) -> np.ndarray:
    """Score every item by how strongly its name matches the query.

    Returns an int32 array where larger values indicate stronger matches:
    exact-name > all-tokens-in-name > substring > partial-token-in-name > 0.
    The score dominates the final sort, so an exact-name match always
    outranks a better-composite item with a weaker name match.
    """
    n = index.num_items()
    scores = np.zeros(n, dtype=np.int32)

    q = search_text.strip().lower()
    if not q:
        return scores

    raw_tokens = [t for t in _RAW_TOKEN_RE.findall(q) if len(t) >= 2]

    # Partial-token band: give credit per token matched (independent of AND).
    if raw_tokens:
        per_token_count = index.name_token_count(raw_tokens).astype(np.int32)
        scores += _NAME_SCORE_PARTIAL_TOKEN * per_token_count

    # Substring band: raw query string appears in the name.
    substr = index.name_contains_query(q)
    scores = np.where(substr, scores + _NAME_SCORE_SUBSTR, scores)

    # All-tokens band: every raw token appears as a whole name token.
    if raw_tokens:
        all_tokens = index.name_token_match(raw_tokens)
        scores = np.where(all_tokens, scores + _NAME_SCORE_ALL_TOKENS, scores)

    # Exact band: the query string exactly equals the name.
    exact = index.exact_name_match(q)
    scores = np.where(exact, scores + _NAME_SCORE_EXACT, scores)

    return scores


def _build_results(
    index: CatalogSearchIndex,
    selected: np.ndarray,
    name_scores: np.ndarray,
    text_scores: np.ndarray,
    top_k: int | None,
    composite: np.ndarray | None = None,
    profile_scores: np.ndarray | None = None,
    weights: dict[str, float] | None = None,
    alpha_tiebreak: bool = False,
) -> list[ScoredExtension]:
    """Sort and materialize the ranked result list.

    When ``alpha_tiebreak`` is True (NAME mode), name_score → alphabetical.
    Otherwise, name_score → composite desc → name asc.
    """
    n = index.num_items()
    if composite is None:
        composite = np.zeros(n, dtype=np.float32)

    # np.lexsort applies keys last-to-first; primary key is name_score (desc).
    if not alpha_tiebreak:
        keys = (index.names_lower_arr, -composite, -name_scores.astype(np.int32))
    else:
        keys = (index.names_lower_arr, -name_scores.astype(np.int32))

    order = np.lexsort(keys)

    limit = top_k if top_k is not None else int(selected.sum())
    results: list[ScoredExtension] = []
    for idx in order:
        if len(results) >= limit:
            break
        if not selected[idx]:
            continue
        item = index.item_at(int(idx))
        breakdown: dict[str, float] = {"text": float(text_scores[idx])}
        if weights is not None and profile_scores is not None:
            breakdown.update(
                {
                    "profile": float(weights["profile"] * profile_scores[idx]),
                    "quality": float(weights["quality"] * index.quality_signal[idx]),
                    "popularity": float(weights["popularity"] * index.popularity_signal[idx]),
                    "recency": float(weights["recency"] * index.recency_signal[idx]),
                }
            )
        results.append(
            ScoredExtension(
                extension_id=item.extension_id,
                composite_score=float(composite[idx]),
                signal_breakdown=breakdown,
            )
        )
    return results


def _effective_weights(
    mode_weights: dict[str, float], present_signals: set[str]
) -> dict[str, float]:
    """Zero out missing-input weights and renormalize the rest to 1.0.

    Thin wrapper around :func:`vibelens.services.search.effective_weights`
    kept here so the call site reads naturally alongside the
    extension-specific WEIGHTS_BY_MODE table.
    """
    from vibelens.services.search import effective_weights as _shared_effective_weights

    return _shared_effective_weights(mode_weights, present_signals=present_signals)
