"""Retrieval backends for the recommendation pipeline.

Provides pluggable search over the catalog. Default is KeywordRetrieval
(TF-IDF cosine similarity via scikit-learn).
"""

from abc import ABC, abstractmethod

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from vibelens.models.extension import AgentExtensionItem
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class RetrievalBackend(ABC):
    """Abstract retrieval backend for catalog search."""

    @abstractmethod
    def build_index(self, items: list[AgentExtensionItem]) -> None:
        """Build search index from catalog items.

        Args:
            items: Full catalog item list.
        """

    @abstractmethod
    def search(self, query: str, top_k: int) -> list[tuple[AgentExtensionItem, float]]:
        """Search the catalog for items matching query.

        Args:
            query: Search query string (e.g. joined search_keywords).
            top_k: Maximum number of results to return.

        Returns:
            List of (ExtensionItem, relevance_score) tuples, sorted by score descending.
        """


class KeywordRetrieval(RetrievalBackend):
    """TF-IDF cosine similarity retrieval.

    Pre-computes TF-IDF vectors from item name + description + topics.
    Query is vectorized and compared via cosine similarity.
    """

    def __init__(self) -> None:
        self._vectorizer = TfidfVectorizer(stop_words="english", max_features=10_000)
        self._items: list[AgentExtensionItem] = []
        self._tfidf_matrix = None

    def build_index(self, items: list[AgentExtensionItem]) -> None:
        """Build TF-IDF index from catalog items.

        Args:
            items: Catalog items to index.
        """
        self._items = items
        if not items:
            self._tfidf_matrix = None
            return

        documents = [
            f"{item.name} {item.description or ''} {' '.join(item.topics)}" for item in items
        ]
        self._tfidf_matrix = self._vectorizer.fit_transform(documents)
        logger.info(
            "Built TF-IDF index: %d items, %d features", len(items), self._tfidf_matrix.shape[1]
        )

    def search(self, query: str, top_k: int) -> list[tuple[AgentExtensionItem, float]]:
        """Search catalog using TF-IDF cosine similarity.

        Args:
            query: Space-separated search keywords.
            top_k: Maximum results to return.

        Returns:
            Ranked (ExtensionItem, score) pairs.
        """
        if not query.strip() or self._tfidf_matrix is None:
            return []

        query_vec = self._vectorizer.transform([query])
        similarities = cosine_similarity(query_vec, self._tfidf_matrix).flatten()

        top_indices = similarities.argsort()[::-1][:top_k]
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score > 0.0:
                results.append((self._items[idx], score))
        return results
