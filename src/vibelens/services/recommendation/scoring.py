"""Multi-signal weighted scoring for recommendation candidates.

Combines retrieval relevance, quality, platform match, popularity,
and composability into a final score per candidate.
"""

from vibelens.models.recommendation.catalog import CatalogItem
from vibelens.models.recommendation.profile import UserProfile

# Signal weights from spec
WEIGHT_RELEVANCE = 0.40
WEIGHT_QUALITY = 0.25
WEIGHT_PLATFORM_MATCH = 0.20
WEIGHT_POPULARITY = 0.10
WEIGHT_COMPOSABILITY = 0.05

# Maximum quality score from catalog
MAX_QUALITY_SCORE = 100.0

# Normalize LLM-generated platform names to canonical catalog values.
# Profile may use "claude-code" (hyphen) while catalog uses "claude_code" (underscore).
PLATFORM_ALIASES: dict[str, str] = {
    "claude-code": "claude_code",
    "claude_code": "claude_code",
    "codex": "codex",
    "gemini": "gemini",
    "gemini-cli": "gemini",
    "gemini_cli": "gemini",
    "openclaw": "openclaw",
    "dataclaw": "dataclaw",
}


def _score_quality(item: CatalogItem) -> float:
    """Normalize quality score to 0.0-1.0 range.

    Args:
        item: Catalog item with quality_score (0-100).

    Returns:
        Normalized quality score.
    """
    return min(item.quality_score / MAX_QUALITY_SCORE, 1.0)


def _normalize_platform(name: str) -> str:
    """Normalize a platform name to its canonical catalog form.

    Args:
        name: Raw platform name from profile or catalog.

    Returns:
        Canonical platform name, or original lowercased if no alias exists.
    """
    return PLATFORM_ALIASES.get(name.lower(), name.lower())


def _score_platform_match(item: CatalogItem, profile: UserProfile) -> float:
    """Binary platform match: 1.0 if any user platform matches, else 0.0.

    Normalizes both profile and catalog platform names to handle
    naming variants (e.g. "claude-code" vs "claude_code").

    Args:
        item: Catalog item with platforms list.
        profile: User profile with agent_platforms.

    Returns:
        1.0 or 0.0.
    """
    user_platforms = {_normalize_platform(p) for p in profile.agent_platforms}
    item_platforms = {_normalize_platform(p) for p in item.platforms}
    return 1.0 if user_platforms & item_platforms else 0.0


def _score_popularity(item: CatalogItem) -> float:
    """Return pre-normalized popularity score.

    Args:
        item: Catalog item with popularity (0.0-1.0).

    Returns:
        Popularity score.
    """
    return min(max(item.popularity, 0.0), 1.0)


def score_candidates(
    candidates: list[tuple[CatalogItem, float]], profile: UserProfile, top_k: int = 15
) -> list[tuple[CatalogItem, float]]:
    """Score and rank retrieval candidates using weighted signals.

    Args:
        candidates: (CatalogItem, relevance_score) pairs from retrieval.
        profile: User profile for platform matching.
        top_k: Number of top results to return.

    Returns:
        Top-k (CatalogItem, composite_score) pairs sorted by score descending.
    """
    scored: list[tuple[CatalogItem, float]] = []

    for item, relevance in candidates:
        composite = (
            WEIGHT_RELEVANCE * relevance
            + WEIGHT_QUALITY * _score_quality(item)
            + WEIGHT_PLATFORM_MATCH * _score_platform_match(item, profile)
            + WEIGHT_POPULARITY * _score_popularity(item)
            + WEIGHT_COMPOSABILITY * 0.0  # Composability uses pre-computed pairs (future)
        )
        scored.append((item, composite))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_k]
