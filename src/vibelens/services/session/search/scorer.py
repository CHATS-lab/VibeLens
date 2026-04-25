"""Session-specific ranking: tier + BM25F + phrase bonus + recency.

The within-tier composite combines four signals:

1. **Strict-AND BM25F composite** — every query token (post-tokenize, so
   already stopword-stripped) must appear in some field. Normalized to
   [0, 1]. Mid-typing fallback retries with the trailing word stripped
   when the initial AND fails.
2. **Composite floor** — tier-0 docs scoring below FLOOR_FRAC * top are
   zeroed. Tier-1/2 docs are exempt; the highest tier-0 composite is
   always preserved (top-1 guarantee).
3. **Phrase bonus** — additive, runs on a *broader* candidate set than
   strict AND (soft-AND with one missing token allowed for queries of
   3+ tokens). Tries the full query first, then trailing-word truncation,
   then leading-word truncation. Each fallback is gated to multi-word
   substrings only.
4. **Recency decay** — exponential decay on the BM25F composite (not on
   phrase bonus). Verbatim phrase matches stay findable across time;
   weak BM25-only matches lose ground to recent ones.

Final score: ``composite * recency + phrase``.
Sort: ``(tier desc, final desc, timestamp desc)``.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

import numpy as np

from vibelens.services.search import InvertedIndex, score_text_query, tokenize
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Tier bands. The spread is intentional — any tier-2 entry outranks any
# tier-1 entry regardless of composite.
_TIER_EXACT: Final = 2
_TIER_PREFIX: Final = 1
_TIER_NONE: Final = 0

# Phrase bonus per field (additive). The session_id field is intentionally
# absent — sid matches already ride the tier system.
PHRASE_BONUS_WEIGHTS: Final[dict[str, float]] = {
    "user_prompts": 1.5,
    "agent_messages": 0.7,
    "tool_calls": 0.3,
}

# Minimum post-tokenize token count required before the phrase bonus
# fires. Single-token queries rely on BM25 alone; treating one word as a
# "phrase" would just reward token presence, which BM25 already handles.
PHRASE_MIN_TOKENS: Final = 2

# Composite floor as a fraction of the top tier-0 composite. Tier-1/2
# docs (session_id matches) are exempt; the highest-composite tier-0 doc
# is always kept (top-1 guarantee).
FLOOR_FRAC: Final = 0.10

# Soft-AND admits a doc to the phrase candidate set if it matches at
# least (N - SOFT_AND_MISS_BUDGET) of N tokens. Strict-AND is enforced
# for shorter queries (N < SOFT_AND_MIN_LEN) so 2-token queries don't
# devolve into OR semantics.
SOFT_AND_MIN_LEN: Final = 3
SOFT_AND_MISS_BUDGET: Final = 1

# Exponential recency decay applied to the BM25F composite (not to phrase
# bonus). MIN_RECENCY floors the multiplier so very old sessions remain
# findable, just demoted relative to recent ones.
RECENCY_HALF_LIFE_DAYS: Final = 60.0
MIN_RECENCY: Final = 0.3


@dataclass(slots=True)
class RankableView:
    """Read-only snapshot of the session index needed to rank one query.

    Bundled so the ranking entry point keeps a compact signature. Constructed
    fresh per query; the inverted index, sid lookup maps, and raw_text_lookup
    closure all reference index state without copying.
    """

    inverted: InvertedIndex
    # doc_idx -> session_id, length num_docs.
    order: list[str]
    # Parallel float64 epoch-seconds per doc. -inf for sessions with no
    # recorded timestamp; makes them sort last under the recency tiebreaker.
    timestamps: np.ndarray
    # Lowercased session_id -> doc idx. O(1) exact-match lookup.
    id_exact: dict[str, int]
    # Leading dash-delimited segment -> list of doc idxs in that prefix band.
    id_prefix: dict[str, list[int]]
    # Lookup raw lowercased text by (doc_idx, field). Closure over the
    # index entries; avoids materializing per-field text arrays per query.
    raw_text_lookup: Callable[[int, str], str]


def score_query(view: RankableView, query: str, top_k: int | None) -> list[tuple[str, float]]:
    """Rank every doc for ``query`` and return ``(session_id, score)`` pairs."""
    num_docs = view.inverted.num_docs
    query_text = query.strip()
    if num_docs == 0 or not query_text:
        return []

    tiers = _compute_tiers(query_text, num_docs, view.id_exact, view.id_prefix)
    composite = score_text_query(view.inverted, query_text, expand_last_as_prefix=True)

    # Mid-typing fallback: when an unfinished trailing word (e.g. "explc")
    # is unknown to the vocab AND too short for prefix expansion, strict
    # AND drops every doc. Retry with the trailing word stripped.
    if not composite.any() and " " in query_text:
        truncated = query_text.rsplit(" ", 1)[0]
        composite = score_text_query(view.inverted, truncated, expand_last_as_prefix=True)

    composite = _apply_composite_floor(composite, tiers)

    # Soft-AND admits docs missing one query token to the phrase candidate
    # set. The phrase substring test is itself a strong filter, so this
    # rescues docs blocked by strict AND on a typo without polluting
    # results with false positives.
    candidates = (
        _soft_and_mask(view.inverted, query_text)
        | (tiers > _TIER_NONE)
        | (composite > 0.0)
    )
    phrase_bonus = _phrase_bonuses(query_text, view.raw_text_lookup, num_docs, candidates)

    # Recency decays composite only — verbatim phrase matches stay
    # findable across time; weak BM25-only matches lose ground to recent.
    recency_factor = _recency_factor(view.timestamps)
    final_score = composite * recency_factor + phrase_bonus

    matched = (tiers > _TIER_NONE) | (final_score > 0.0)
    if not matched.any():
        return []

    # lexsort: last key is primary. (tier, final, ts) all descending.
    sort_order = np.lexsort((-view.timestamps, -final_score, -tiers.astype(np.int32)))
    matched_in_order = sort_order[matched[sort_order]]
    limit = top_k if top_k is not None else len(matched_in_order)
    return [
        (view.order[idx], float(final_score[idx]))
        for idx in matched_in_order[:limit]
    ]


def _apply_composite_floor(composite: np.ndarray, tiers: np.ndarray) -> np.ndarray:
    """Zero tier-0 composites below FLOOR_FRAC * top_tier0_composite.

    Tier-1/2 docs are exempt — their composite passes through unchanged.
    The single highest-composite tier-0 doc is always retained (top-1
    guarantee), even when below the floor in absolute terms.
    """
    tier_zero_mask = tiers == _TIER_NONE
    if not tier_zero_mask.any():
        return composite

    tier_zero_composite = np.where(tier_zero_mask, composite, 0.0)
    top_composite = float(tier_zero_composite.max())
    if top_composite <= 0.0:
        return composite

    # Top-1 guarantee is automatic: composite[argmax] == top_composite,
    # always >= threshold (= FLOOR_FRAC * top_composite).
    threshold = FLOOR_FRAC * top_composite
    keep_mask = (~tier_zero_mask) | (composite >= threshold)
    return np.where(keep_mask, composite, 0.0)


def _soft_and_mask(inverted: InvertedIndex, query: str) -> np.ndarray:
    """Bool mask: docs matching enough of the query tokens for phrase candidacy.

    For queries shorter than SOFT_AND_MIN_LEN, returns all-False (relying
    on the strict-AND composite path alone). Otherwise admits docs that
    match at least (N - SOFT_AND_MISS_BUDGET) of N tokens. This rescues
    docs that are missing exactly one token (typos, partial recalls) so
    the phrase substring test gets a chance to match them.
    """
    n = inverted.num_docs
    tokens = tokenize(query)
    if n == 0 or len(tokens) < SOFT_AND_MIN_LEN:
        return np.zeros(n, dtype=bool)

    match_counts = np.zeros(n, dtype=np.int32)
    for token in tokens:
        per_token_mask = np.zeros(n, dtype=bool)
        for field in inverted.field_weights:
            per_token_mask |= inverted.per_field_has_token(field, token)
        match_counts += per_token_mask.astype(np.int32)
    return match_counts >= (len(tokens) - SOFT_AND_MISS_BUDGET)


def _phrase_bonuses(
    query: str,
    raw_text_lookup: Callable[[int, str], str],
    n: int,
    candidates: np.ndarray,
) -> np.ndarray:
    """Per-doc additive phrase bonus for substring matches in indexed fields.

    Tries the full query first, then trailing-truncated (drops unfinished
    last word), then leading-truncated (drops typo'd first word). Returns
    at the first non-empty result. Truncation fallbacks gated to
    multi-word substrings — single-word fallbacks would degrade to
    per-token presence, which BM25 already covers.
    """
    bonuses = np.zeros(n, dtype=np.float32)
    if len(tokenize(query)) < PHRASE_MIN_TOKENS:
        return bonuses

    for needle in _phrase_substrings_to_try(query.strip().lower()):
        bonuses = _substring_bonuses(needle, raw_text_lookup, n, candidates)
        if bonuses.any():
            return bonuses
    return bonuses


def _phrase_substrings_to_try(needle: str):
    """Yield the full needle, then trim-trailing, then trim-leading.

    Each yielded substring is multi-word; single-word truncations are
    skipped because they're already covered by BM25 token matching.
    """
    yield needle
    if " " not in needle:
        return
    trailing = needle.rsplit(" ", 1)[0]
    if " " in trailing:
        yield trailing
    leading = needle.split(" ", 1)[1]
    if " " in leading:
        yield leading


def _substring_bonuses(
    needle: str, raw_text_lookup: Callable[[int, str], str], n: int, candidates: np.ndarray
) -> np.ndarray:
    """Sum per-field bonuses for each candidate doc whose field text contains needle.

    Iterates only the candidate set (typically tens of docs) to keep
    substring work proportional to the BM25/soft-AND survivor pool, not
    the full corpus.
    """
    bonuses = np.zeros(n, dtype=np.float32)
    for doc_idx in np.flatnonzero(candidates):
        for field, weight in PHRASE_BONUS_WEIGHTS.items():
            if needle in raw_text_lookup(int(doc_idx), field):
                bonuses[doc_idx] += weight
    return bonuses


def _recency_factor(timestamps: np.ndarray) -> np.ndarray:
    """Exponential decay multiplier in [MIN_RECENCY, 1.0] per doc.

    Sessions without a timestamp (-inf) reach MIN_RECENCY via the floor:
    ``exp(-inf) = 0``, then ``max(0, MIN_RECENCY) = MIN_RECENCY``.
    """
    now = datetime.now(timezone.utc).timestamp()
    age_days = np.maximum((now - timestamps) / 86400.0, 0.0)
    decayed = np.exp(-age_days / RECENCY_HALF_LIFE_DAYS)
    return np.maximum(decayed, MIN_RECENCY).astype(np.float32)


def _compute_tiers(
    query: str, n: int, id_exact: dict[str, int], id_prefix: dict[str, list[int]]
) -> np.ndarray:
    """Return an ``int16`` array marking each doc's session_id tier.

    First-segment prefix band: only triggers on the leading dash-delimited
    segment of a session_id. ``"abc"`` matches sid ``"abc-de-..."`` but not
    ``"xy-abc-..."``. Catches the common case of typing the first ~5 chars
    of a sid displayed in the UI.
    """
    tiers = np.zeros(n, dtype=np.int16)
    lowered = query.lower()

    exact_idx = id_exact.get(lowered)
    if exact_idx is not None:
        tiers[exact_idx] = _TIER_EXACT

    leading_segment = lowered.split("-", 1)[0]
    for idx in id_prefix.get(leading_segment, ()):
        if tiers[idx] == _TIER_NONE:
            tiers[idx] = _TIER_PREFIX
    return tiers
