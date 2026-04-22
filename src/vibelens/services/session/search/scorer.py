"""Session-specific ranking: session_id tier + BM25F composite.

Two layers:

1. **session_id tier** — dominates. Exact match (case-insensitive) beats
   first-segment prefix match beats tier 0.
2. **Within-tier composite** — BM25F across the four session fields,
   normalized to [0, 1], AND semantics over required tokens.

Final sort: ``(tier desc, composite desc, session_timestamp desc)``.
Recency is the tiebreaker so equally-scored sessions surface the most
recent one first.
"""

from dataclasses import dataclass

import numpy as np

from vibelens.services.search import InvertedIndex, score_text_query
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Tier bands. The spread is intentional — any tier-2 entry outranks any
# tier-1 entry regardless of composite.
_TIER_EXACT = 2
_TIER_PREFIX = 1
_TIER_NONE = 0


@dataclass(slots=True)
class RankableView:
    """Read-only snapshot of the session index needed to rank one query.

    Bundled so the ranking entry point keeps a compact signature. Constructed
    fresh per query because the inverted index and sid lookup maps are
    cheap to reference (no copies) but the underlying arrays must be
    in-scope for the duration of the call.
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


def score_query(view: RankableView, query: str, top_k: int | None) -> list[tuple[str, float]]:
    """Rank every doc for ``query`` and return ``(session_id, score)`` pairs."""
    n = view.inverted.num_docs
    cleaned = query.strip()
    if n == 0 or not cleaned:
        return []

    tiers = _compute_tiers(cleaned, n, view.id_exact, view.id_prefix)
    composite = score_text_query(view.inverted, cleaned, expand_last_as_prefix=True)

    # Drop zero-everywhere docs: neither in a sid tier nor text-matched.
    matched = (tiers > _TIER_NONE) | (composite > 0.0)
    if not matched.any():
        return []

    # lexsort uses the LAST key as primary. We want:
    #   primary   tier desc
    #   secondary composite desc
    #   tertiary  timestamp desc
    # Encode desc by negating (tiers is int, composite/ts are float).
    order_idx = np.lexsort((-view.timestamps, -composite, -tiers.astype(np.int32)))

    limit = top_k if top_k is not None else int(matched.sum())
    results: list[tuple[str, float]] = []
    for idx in order_idx:
        if len(results) >= limit:
            break
        if not matched[idx]:
            continue
        results.append((view.order[idx], float(composite[idx])))
    return results


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
