"""Generic helpers for composing BM25F scores into a ranked result set.

The extension catalog and session search paths differ in *what* they want
to sort on (name-tier vs session_id-tier) but share the underlying
mechanics: tokenize, split required-vs-prefix, AND-match across required
tokens, weighted-BM25 score the union, normalize.

Every function here operates on an :class:`InvertedIndex` and primitive
numpy arrays. No domain types leak in — callers do their own tier
computation and final lexsort.
"""

import numpy as np

from vibelens.services.search.inverted_index import InvertedIndex
from vibelens.services.search.tokenizer import tokenize


def score_text_query(
    index: InvertedIndex, text: str, expand_last_as_prefix: bool, max_prefix_expansions: int = 10
) -> np.ndarray:
    """Score every doc against the tokenized query, summed across fields.

    AND semantics: every required (non-prefix) query token must appear
    somewhere in the doc. Prefix-expanded last tokens contribute as OR.
    Docs failing the AND match are scored zero. The returned array is
    normalized to [0, 1] by dividing by the max score.

    Args:
        index: The built inverted index.
        text: Raw user-typed query.
        expand_last_as_prefix: When True and the last token is unknown to
            every field vocab, expand it as a prefix and treat the
            expansions as OR alternatives.
        max_prefix_expansions: Cap on the number of prefix expansions to
            keep. Prevents a short prefix from blowing up scoring work.

    Returns:
        float32 array of length ``index.num_docs``. All zeros when the
        query tokenizes empty, the index is empty, or nothing matches.
    """
    n = index.num_docs
    raw_tokens = tokenize(text)
    if not raw_tokens or n == 0:
        return np.zeros(n, dtype=np.float32)

    required_tokens, optional_tokens = split_required_and_prefix(
        index, text, raw_tokens, expand_last_as_prefix, max_prefix_expansions
    )

    match_mask = and_match_mask(index, required_tokens, n)
    if not match_mask.any():
        return np.zeros(n, dtype=np.float32)

    if optional_tokens:
        optional_mask = or_match_mask(index, optional_tokens, n)
        match_mask &= optional_mask
        if not match_mask.any():
            return np.zeros(n, dtype=np.float32)

    scoring_tokens = required_tokens + optional_tokens
    combined = np.zeros(n, dtype=np.float32)
    for field, weight in index.field_weights.items():
        if weight <= 0:
            continue
        combined += weight * index.score_field(field, scoring_tokens)
    combined = np.where(match_mask, combined, 0.0)

    max_score = float(combined.max()) if combined.size else 0.0
    if max_score <= 0:
        return np.zeros(n, dtype=np.float32)
    return combined / max_score


def split_required_and_prefix(
    index: InvertedIndex,
    raw_text: str,
    tokens: list[str],
    expand_last_as_prefix: bool,
    max_prefix_expansions: int = 10,
) -> tuple[list[str], list[str]]:
    """Split tokens into (required-AND, optional-OR-prefix-expansions).

    If the user hasn't finished typing the last token (no trailing space),
    and the last token isn't already in a vocab, expand it as a prefix.
    Otherwise, every token is required.
    """
    if not expand_last_as_prefix or raw_text.endswith((" ", "\t", "\n")) or not tokens:
        return tokens, []
    last = tokens[-1]
    if index.token_in_any_vocab(last):
        return tokens, []
    expansions = index.expand_prefix(last)
    if not expansions:
        return tokens, []
    return tokens[:-1], expansions[:max_prefix_expansions]


def and_match_mask(index: InvertedIndex, tokens: list[str], n: int) -> np.ndarray:
    """Bool mask: docs where every token appears in at least one field."""
    mask = np.ones(n, dtype=bool)
    for tok in tokens:
        per_token = np.zeros(n, dtype=bool)
        for field in index.field_weights:
            per_token |= index.per_field_has_token(field, tok)
        mask &= per_token
        if not mask.any():
            return mask
    return mask


def or_match_mask(index: InvertedIndex, tokens: list[str], n: int) -> np.ndarray:
    """Bool mask: docs where at least one of ``tokens`` appears anywhere."""
    mask = np.zeros(n, dtype=bool)
    for tok in tokens:
        for field in index.field_weights:
            mask |= index.per_field_has_token(field, tok)
    return mask


def effective_weights(
    mode_weights: dict[str, float], present_signals: set[str] | None = None
) -> dict[str, float]:
    """Zero out missing-signal weights and renormalize the rest to 1.0.

    Args:
        mode_weights: Configured weights, signal → weight.
        present_signals: Signal names whose inputs are non-empty. When a
            signal is absent from this set, its weight is zeroed before
            renormalization. Pass ``None`` to keep every weight as-is.

    Returns:
        Dict with the same keys as ``mode_weights``, summing to 1.0
        (or uniform when every weight zeroed out).
    """
    weights = dict(mode_weights)
    if present_signals is not None:
        for k in list(weights):
            if k not in present_signals:
                weights[k] = 0.0
    total = sum(weights.values())
    if total <= 0:
        return {k: 1.0 / len(weights) for k in weights}
    return {k: v / total for k, v in weights.items()}
