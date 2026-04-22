"""Session search result type."""

from dataclasses import dataclass


@dataclass(slots=True)
class ScoredSession:
    """Single ranked session in a search response.

    Attributes:
        session_id: The matched session identifier.
        composite_score: BM25F composite within the session_id tier.
            Zero when the result came from Tier 1 (metadata fallback)
            or when scoring produced a zero.
    """

    session_id: str
    composite_score: float
