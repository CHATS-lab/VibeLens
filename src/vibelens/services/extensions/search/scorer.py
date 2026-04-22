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
from vibelens.services.extensions.search.index import FIELD_WEIGHTS, CatalogSearchIndex
from vibelens.services.extensions.search.query import ScoredExtension, SortMode
from vibelens.services.extensions.search.tokenizer import tokenize
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
    name_scores = (
        _name_match_tiers(index, search_text) if has_text else np.zeros(n, dtype=np.int32)
    )

    text_scores = (
        _score_text_query(index, search_text, expand_last_as_prefix=True)
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
        return _build_results(
            index, selected, name_scores, text_scores, top_k, alpha_tiebreak=True
        )

    profile_scores = (
        _score_text_query(index, " ".join(profile_keywords), expand_last_as_prefix=False)
        if profile_keywords
        else np.zeros(n, dtype=np.float32)
    )

    weights = _effective_weights(
        mode_weights=WEIGHTS_BY_MODE[sort],
        has_text=has_text,
        has_profile=bool(profile_keywords),
    )
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
    *,
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
    mode_weights: dict[str, float], has_text: bool, has_profile: bool
) -> dict[str, float]:
    """Zero out missing-input weights and renormalize the rest to 1.0."""
    weights = dict(mode_weights)
    if not has_text:
        weights["text"] = 0.0
    if not has_profile:
        weights["profile"] = 0.0
    total = sum(weights.values())
    if total <= 0:
        return {k: 1.0 / len(weights) for k in weights}
    return {k: v / total for k, v in weights.items()}


def _score_text_query(
    index: CatalogSearchIndex, text: str, expand_last_as_prefix: bool
) -> np.ndarray:
    """Score every item against the tokenized query, summed across fields.

    AND semantics: every required (non-prefix) query token must appear
    somewhere in the item. Prefix-expanded last tokens contribute as OR.
    Items failing the AND match are scored zero.
    """
    n = index.num_items()
    raw_tokens = tokenize(text)
    if not raw_tokens or n == 0:
        return np.zeros(n, dtype=np.float32)

    required_tokens, optional_tokens = _split_required_and_prefix(
        index, text, raw_tokens, expand_last_as_prefix
    )

    match_mask = _and_match_mask(index, required_tokens, n)
    if not match_mask.any():
        return np.zeros(n, dtype=np.float32)

    if optional_tokens:
        optional_mask = _or_match_mask(index, optional_tokens, n)
        match_mask &= optional_mask
        if not match_mask.any():
            return np.zeros(n, dtype=np.float32)

    scoring_tokens = required_tokens + optional_tokens
    combined = np.zeros(n, dtype=np.float32)
    for field, weight in FIELD_WEIGHTS.items():
        combined += weight * index.score_field(field, scoring_tokens)
    combined = np.where(match_mask, combined, 0.0)

    max_score = float(combined.max()) if combined.size else 0.0
    if max_score <= 0:
        return np.zeros(n, dtype=np.float32)
    return combined / max_score


def _split_required_and_prefix(
    index: CatalogSearchIndex,
    raw_text: str,
    tokens: list[str],
    expand_last_as_prefix: bool,
) -> tuple[list[str], list[str]]:
    """Split tokens into (required-AND, optional-OR-prefix-expansions)."""
    if not expand_last_as_prefix or raw_text.endswith((" ", "\t", "\n")) or not tokens:
        return tokens, []
    last = tokens[-1]
    if index.token_in_any_vocab(last):
        return tokens, []
    expansions = index.expand_prefix(last)
    if not expansions:
        return tokens, []
    return tokens[:-1], expansions[:10]


def _and_match_mask(
    index: CatalogSearchIndex, tokens: list[str], n: int
) -> np.ndarray:
    """Bool mask: items where every token appears in at least one field."""
    mask = np.ones(n, dtype=bool)
    for tok in tokens:
        per_token = np.zeros(n, dtype=bool)
        for field in FIELD_WEIGHTS:
            per_token |= index.per_field_has_token(field, tok)
        mask &= per_token
        if not mask.any():
            return mask
    return mask


def _or_match_mask(
    index: CatalogSearchIndex, tokens: list[str], n: int
) -> np.ndarray:
    """Bool mask: items where at least one of ``tokens`` appears anywhere."""
    mask = np.zeros(n, dtype=bool)
    for tok in tokens:
        for field in FIELD_WEIGHTS:
            mask |= index.per_field_has_token(field, tok)
    return mask
