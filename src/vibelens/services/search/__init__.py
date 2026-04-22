"""Shared search core.

Domain-agnostic building blocks for field-weighted BM25 search:

  * :func:`tokenize` — consistent lowercase/stopword/stem tokenization.
  * :class:`InvertedIndex` — per-field BM25 + postings + prefix map.
  * Ranking helpers in ``ranking.py`` compose these into scored results.

The extension catalog and session search packages are thin wrappers that
add domain-specific signals (quality/recency for catalog, session_id
tier for sessions) on top of this core.
"""

from vibelens.services.search.inverted_index import InvertedIndex
from vibelens.services.search.ranking import (
    and_match_mask,
    effective_weights,
    or_match_mask,
    score_text_query,
    split_required_and_prefix,
)
from vibelens.services.search.tokenizer import tokenize

__all__ = [
    "InvertedIndex",
    "and_match_mask",
    "effective_weights",
    "or_match_mask",
    "score_text_query",
    "split_required_and_prefix",
    "tokenize",
]
