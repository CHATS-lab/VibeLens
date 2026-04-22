"""Generic field-weighted BM25 inverted index.

Domain-agnostic. Callers build one of these with a pre-tokenized corpus
keyed by field name, plus a weight per field. The index then answers:

  * per-field BM25 scores for a query (numpy array over docs)
  * per-field token-presence bool masks
  * prefix expansion (for autocomplete of the last typed token)
  * vocab membership

Extension-catalog-specific features (quality signal, popularity, recency,
name-token match tiers) live in the domain wrapper, not here.
"""

from collections import defaultdict

import numpy as np
from rank_bm25 import BM25Okapi

# Shortest prefix we expand in ``expand_prefix``. Below this length the
# prefix matches too many tokens to be useful.
_MIN_PREFIX_LEN = 3

# Upper bound on prefix lengths we store, per token. Keeps the prefix map
# from growing quadratically with token length.
_MAX_PREFIX_LEN = 12


class InvertedIndex:
    """Weighted per-field BM25 over a fixed list of pre-tokenized docs.

    Args:
        tokenized_corpus: One row per document. Each row is a dict mapping
            every field name to its token list. Fields missing from a row
            are treated as empty.
        field_weights: Field-name → weight. Zero-weight fields are skipped
            at build time.

    The document ``i`` in the returned bm25/postings arrays corresponds
    to row ``i`` of ``tokenized_corpus`` — callers store their own
    row → doc-id mapping.
    """

    def __init__(
        self, tokenized_corpus: list[dict[str, list[str]]], field_weights: dict[str, float]
    ) -> None:
        self._n = len(tokenized_corpus)
        self._field_weights = dict(field_weights)
        self._bm25: dict[str, BM25Okapi] = {}
        self._vocab: dict[str, set[str]] = {}
        self._postings: dict[str, dict[str, np.ndarray]] = {f: {} for f in field_weights}
        self._prefix_map: dict[str, set[str]] = defaultdict(set)

        if self._n == 0:
            return

        for field, weight in field_weights.items():
            if weight <= 0:
                continue
            tokenized = [row.get(field, []) for row in tokenized_corpus]
            if not any(tokenized):
                continue
            # rank-bm25 rejects corpora where every doc is empty; a sentinel
            # token that never matches a real query keeps its IDF math happy.
            corpus = [t if t else [f"__empty_{field}__"] for t in tokenized]
            self._bm25[field] = BM25Okapi(corpus)
            vocab = {tok for doc in tokenized for tok in doc}
            self._vocab[field] = vocab
            # Invert the corpus in a single pass: token -> sorted array of
            # doc indices that contain the token.
            postings_lists: dict[str, list[int]] = {tok: [] for tok in vocab}
            for doc_i, doc_tokens in enumerate(tokenized):
                for tok in set(doc_tokens):
                    postings_lists[tok].append(doc_i)
            self._postings[field] = {
                tok: np.asarray(hits, dtype=np.int32) for tok, hits in postings_lists.items()
            }

        all_tokens: set[str] = set()
        for vocab in self._vocab.values():
            all_tokens.update(vocab)
        max_prefix_len = min(_MAX_PREFIX_LEN, max((len(t) for t in all_tokens), default=0))
        for tok in all_tokens:
            for n_prefix in range(_MIN_PREFIX_LEN, min(len(tok), max_prefix_len) + 1):
                self._prefix_map[tok[:n_prefix]].add(tok)

    @property
    def num_docs(self) -> int:
        """Number of documents indexed."""
        return self._n

    @property
    def field_weights(self) -> dict[str, float]:
        """Copy of the field-weight configuration used at build time."""
        return dict(self._field_weights)

    def score_field(self, field: str, query_tokens: list[str]) -> np.ndarray:
        """Return BM25 scores of every doc for one field.

        Args:
            field: Indexed field name.
            query_tokens: Already-tokenized query.

        Returns:
            float32 array of length ``num_docs``. Zeros when the field has
            no BM25 or the query is empty.
        """
        bm25 = self._bm25.get(field)
        if bm25 is None or not query_tokens or self._n == 0:
            return np.zeros(self._n, dtype=np.float32)
        return np.asarray(bm25.get_scores(query_tokens), dtype=np.float32)

    def per_field_has_token(self, field: str, token: str) -> np.ndarray:
        """Bool mask: True where ``token`` appears in the doc's ``field`` text.

        Materialized from the sparse postings on demand. O(n) allocation
        but only O(k) writes where k = number of docs containing the token.
        """
        postings = self._postings.get(field, {})
        hits = postings.get(token)
        mask = np.zeros(self._n, dtype=bool)
        if hits is not None and len(hits) > 0:
            mask[hits] = True
        return mask

    def posting_indices(self, field: str, token: str) -> np.ndarray:
        """Sorted int32 array of doc indices containing ``token`` in ``field``.

        Empty array if the token is not in the field's vocabulary.
        """
        postings = self._postings.get(field, {})
        hits = postings.get(token)
        if hits is None:
            return np.empty(0, dtype=np.int32)
        return hits

    def expand_prefix(self, prefix: str) -> list[str]:
        """Return every indexed token starting with ``prefix``.

        Used only on the last token of a user-typed query. The returned
        list is treated as an OR of tokens at scoring time.
        """
        if len(prefix) < _MIN_PREFIX_LEN:
            return []
        return list(self._prefix_map.get(prefix, ()))

    def token_in_any_vocab(self, token: str) -> bool:
        """True when ``token`` matches a term in at least one field vocab."""
        return any(token in vocab for vocab in self._vocab.values())
