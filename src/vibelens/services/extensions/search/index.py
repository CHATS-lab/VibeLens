"""Catalog search index.

Five independent ``BM25Okapi`` instances (one per field), composed at
query time into a weighted per-field BM25 score. Module-level singleton
built lazily and reset when the catalog reloads.

Signals that do not depend on the query (quality, popularity, recency)
are precomputed as numpy arrays at build time so ranking is dominated
by vectorized arithmetic, not Python loops.
"""

import math
import re
import threading
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
from rank_bm25 import BM25Okapi

from vibelens.models.enums import AgentExtensionType
from vibelens.models.extension import AgentExtensionItem
from vibelens.services.extensions.search.tokenizer import _TOKEN_RE, tokenize
from vibelens.utils.log import get_logger
from vibelens.utils.timestamps import parse_iso_timestamp

logger = get_logger(__name__)

# Per-field weights for weighted per-field BM25. Tunable constants.
# Higher weight = match in this field contributes more to the composite.
FIELD_WEIGHTS: dict[str, float] = {
    "name": 5.0,
    "topics": 3.0,
    "author": 2.0,
    "description": 1.0,
    "readme": 0.5,
}

_MIN_PREFIX_LEN = 3
_RECENCY_HALFLIFE_DAYS = 180.0
_MAX_QUALITY_SCORE = 100.0

_SEPARATOR_RE = re.compile(r"[\s_\-]+")


def _normalize_separators(text: str) -> str:
    """Collapse whitespace, hyphens, and underscores into single spaces."""
    return _SEPARATOR_RE.sub(" ", text).strip()


def _field_text(item: AgentExtensionItem, field: str) -> str:
    """Extract the raw text for a given field from a catalog item."""
    if field == "name":
        return item.name or ""
    if field == "topics":
        return " ".join(item.topics)
    if field == "author":
        parts = [item.author or "", item.repo_full_name or ""]
        return " ".join(p for p in parts if p)
    if field == "description":
        parts = [item.description or "", item.repo_description or ""]
        return " ".join(p for p in parts if p)
    if field == "readme":
        return item.readme_description or ""
    return ""


def _recency_decay(updated_at: str | None, now: datetime) -> float:
    """Exponential decay on days-since-updated. Half-life ~125 days."""
    updated = parse_iso_timestamp(updated_at)
    if updated is None:
        return 0.0
    days = max((now - updated).total_seconds() / 86400.0, 0.0)
    return math.exp(-days / _RECENCY_HALFLIFE_DAYS)


class CatalogSearchIndex:
    """Weighted per-field BM25 over a fixed list of catalog items."""

    def __init__(self, items: list[AgentExtensionItem]) -> None:
        """Tokenize every field and build one BM25 per field.

        Args:
            items: Catalog items to index. Order is preserved; callers
                use the returned position as the canonical item_idx.
        """
        self._items = items
        self._ids = [item.extension_id for item in items]
        self._id_to_idx = {eid: i for i, eid in enumerate(self._ids)}
        self._bm25: dict[str, BM25Okapi] = {}
        self._vocab: dict[str, set[str]] = {}
        self._prefix_map: dict[str, set[str]] = defaultdict(set)

        n = len(items)
        # Precomputed signal arrays (query-independent).
        self.quality_signal = np.zeros(n, dtype=np.float32)
        self.popularity_signal = np.zeros(n, dtype=np.float32)
        self.recency_signal = np.zeros(n, dtype=np.float32)
        self.type_mask: dict[AgentExtensionType, np.ndarray] = {}

        # Lowercased names for exact/prefix matching and alphabetical sort.
        names_lower_list: list[str] = []
        # Union of raw-tokenized names (pre-stem) for token-boundary name matching.
        name_token_sets: list[set[str]] = []

        # Sparse inverted index: field -> token -> sorted int32 array of
        # document indices containing the token. Much smaller than dense
        # bool arrays when the vocabulary is long-tailed.
        self._postings: dict[str, dict[str, np.ndarray]] = {f: {} for f in FIELD_WEIGHTS}

        if not items:
            self.names_lower_arr = np.empty(0, dtype=object)
            self._name_token_sets = []
            logger.info("catalog search index built over empty catalog")
            return

        now = datetime.now(timezone.utc)
        for i, item in enumerate(items):
            self.quality_signal[i] = min(max(item.quality_score / _MAX_QUALITY_SCORE, 0.0), 1.0)
            self.popularity_signal[i] = min(max(item.popularity, 0.0), 1.0)
            self.recency_signal[i] = _recency_decay(item.updated_at, now)
            raw_name = (item.name or "").lower()
            names_lower_list.append(raw_name)
            name_token_sets.append({t for t in _TOKEN_RE.findall(raw_name) if len(t) >= 2})

        self.names_lower_arr = np.asarray(names_lower_list, dtype=object)
        self._name_token_sets = name_token_sets

        # Per-type boolean masks for O(n) filtering at query time.
        for ext_type in AgentExtensionType:
            mask = np.fromiter(
                (item.extension_type == ext_type for item in items),
                count=n,
                dtype=bool,
            )
            self.type_mask[ext_type] = mask

        for field in FIELD_WEIGHTS:
            try:
                tokenized = [tokenize(_field_text(item, field)) for item in items]
                # rank-bm25 rejects corpora where every doc is empty; guard that.
                if not any(tokenized):
                    logger.warning("field %s has no tokens across catalog; skipping", field)
                    continue
                # Empty docs get a sentinel token that never matches a real query.
                corpus = [t if t else [f"__empty_{field}__"] for t in tokenized]
                self._bm25[field] = BM25Okapi(corpus)
                vocab = {tok for doc in tokenized for tok in doc}
                self._vocab[field] = vocab
                # Invert the corpus: token -> sorted array of item indices.
                # Single pass over (doc, token) pairs, O(total_token_count).
                postings_lists: dict[str, list[int]] = {tok: [] for tok in vocab}
                for doc_i, doc_tokens in enumerate(tokenized):
                    for tok in set(doc_tokens):
                        postings_lists[tok].append(doc_i)
                self._postings[field] = {
                    tok: np.asarray(hits, dtype=np.int32)
                    for tok, hits in postings_lists.items()
                }
            except (ValueError, ZeroDivisionError) as exc:
                logger.warning("failed to build bm25 for field %s: %s", field, exc)

        all_tokens: set[str] = set()
        for vocab in self._vocab.values():
            all_tokens.update(vocab)
        max_prefix_len = min(12, max((len(t) for t in all_tokens), default=0))
        for tok in all_tokens:
            for n_prefix in range(_MIN_PREFIX_LEN, min(len(tok), max_prefix_len) + 1):
                self._prefix_map[tok[:n_prefix]].add(tok)

        logger.info(
            "catalog search index built: %d items, %d fields, %d unique tokens",
            len(items),
            len(self._bm25),
            len(all_tokens),
        )

    def num_items(self) -> int:
        """Return the number of indexed items."""
        return len(self._items)

    def item_at(self, idx: int) -> AgentExtensionItem:
        """Return the item at a given index."""
        return self._items[idx]

    def idx_of(self, extension_id: str) -> int | None:
        """Return the index for ``extension_id`` or None if unknown."""
        return self._id_to_idx.get(extension_id)

    def expand_prefix(self, prefix: str) -> list[str]:
        """Return every indexed token starting with ``prefix``.

        Used only on the last token of a user-typed query. The returned
        list is treated as an OR of tokens at scoring time.
        """
        if len(prefix) < _MIN_PREFIX_LEN:
            return []
        return list(self._prefix_map.get(prefix, ()))

    def token_in_any_vocab(self, token: str) -> bool:
        """True when ``token`` is an exact match in at least one field vocab."""
        return any(token in vocab for vocab in self._vocab.values())

    def score_field(self, field: str, query_tokens: list[str]) -> np.ndarray:
        """Score all items for one field as a numpy array.

        Args:
            field: One of the indexed fields (name, topics, etc.).
            query_tokens: Already-tokenized query.

        Returns:
            Array of length ``num_items``. Zeros if field or tokens empty.
        """
        bm25 = self._bm25.get(field)
        n = len(self._items)
        if bm25 is None or not query_tokens or n == 0:
            return np.zeros(n, dtype=np.float32)
        return np.asarray(bm25.get_scores(query_tokens), dtype=np.float32)

    def per_field_has_token(self, field: str, token: str) -> np.ndarray:
        """Bool mask: True where ``token`` appears in the item's ``field`` text.

        Materialized from the sparse postings on demand. O(n) allocation
        but only O(k) writes where k = number of items containing the token.
        """
        n = len(self._items)
        postings = self._postings.get(field, {})
        hits = postings.get(token)
        mask = np.zeros(n, dtype=bool)
        if hits is not None and len(hits) > 0:
            mask[hits] = True
        return mask

    def posting_indices(self, field: str, token: str) -> np.ndarray:
        """Sorted int32 array of item indices containing ``token`` in ``field``.

        Empty array if the token isn't in the field's vocabulary.
        """
        postings = self._postings.get(field, {})
        hits = postings.get(token)
        if hits is None:
            return np.empty(0, dtype=np.int32)
        return hits

    def exact_name_match(self, query: str) -> np.ndarray:
        """Bool mask: item.name equals query ignoring case and separators.

        "mcp server", "mcp-server", and "mcp_server" all match a name of
        "mcp-server". Separator-insensitivity avoids punishing users for
        typing a space where the canonical form uses a dash.
        """
        q = _normalize_separators(query.strip().lower())
        n = len(self._items)
        if not q or n == 0:
            return np.zeros(n, dtype=bool)
        return np.asarray(
            [_normalize_separators(name) == q for name in self.names_lower_arr],
            dtype=bool,
        )

    def name_token_match(self, raw_tokens: list[str]) -> np.ndarray:
        """Bool mask: every raw (pre-stem) query token is a name token.

        Stronger than "name contains substring": uses word boundaries so
        that `paper-writing` matches `paper-writing` and `paper-writer` but
        not items where the letters appear mid-word.
        """
        n = len(self._items)
        if not raw_tokens or n == 0:
            return np.zeros(n, dtype=bool)
        mask = np.ones(n, dtype=bool)
        for tok in raw_tokens:
            if not tok:
                continue
            per = np.fromiter(
                (tok in toks for toks in self._name_token_sets), count=n, dtype=bool
            )
            mask &= per
            if not mask.any():
                return mask
        return mask

    def name_token_count(self, raw_tokens: list[str]) -> np.ndarray:
        """Count per item: how many raw query tokens are whole name tokens.

        Used for partial-tier scoring — an item whose name contains 2 of 3
        query tokens outranks one with 0 but not one with all 3.
        """
        n = len(self._items)
        if not raw_tokens or n == 0:
            return np.zeros(n, dtype=np.int16)
        counts = np.zeros(n, dtype=np.int16)
        for tok in raw_tokens:
            if not tok:
                continue
            for i, toks in enumerate(self._name_token_sets):
                if tok in toks:
                    counts[i] += 1
        return counts

    def name_contains_query(self, query: str) -> np.ndarray:
        """Bool mask: raw (post-cleanup) query string appears in item name.

        Lets 'paper-writ' match 'paper-writing', even though the stemmed
        tokens don't align exactly.
        """
        q = query.strip().lower()
        n = len(self._items)
        if len(q) < 3 or n == 0:
            return np.zeros(n, dtype=bool)
        return np.asarray([q in name for name in self.names_lower_arr], dtype=bool)


# Module-level singleton for the main-catalog index.
_index: CatalogSearchIndex | None = None
_index_lock = threading.Lock()


def get_index() -> CatalogSearchIndex:
    """Return the current index, building it from the catalog if needed.

    Raises:
        ValueError: If the catalog is unavailable.
    """
    global _index  # noqa: PLW0603
    if _index is not None:
        return _index
    # Import lazily to avoid a circular edge at import time.
    from vibelens.storage.extension.catalog import load_catalog

    with _index_lock:
        if _index is not None:
            return _index
        catalog = load_catalog()
        if catalog is None:
            raise ValueError("No catalog available")
        _index = CatalogSearchIndex(catalog.items)
        return _index


def reset_index() -> None:
    """Drop the cached index; next ``get_index()`` rebuilds from disk."""
    global _index  # noqa: PLW0603
    with _index_lock:
        _index = None


def warm_index() -> None:
    """Build the index now. Swallows ValueError when no catalog is loaded yet."""
    try:
        get_index()
    except ValueError:
        logger.info("catalog not yet available; search index will build lazily")
