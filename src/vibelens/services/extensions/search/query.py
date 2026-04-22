"""Extension-query model, sort modes, and scored-result type."""

from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from vibelens.models.enums import AgentExtensionType
from vibelens.models.personalization.recommendation import UserProfile


class SortMode(str, Enum):
    """Ranking mode for catalog search.

    Each mode corresponds to a fixed weight vector over the five signals
    {text, profile, quality, popularity, recency}. See scorer.py for the
    concrete weights. NAME is a special alphabetical-only path.
    """

    DEFAULT = "default"
    PERSONALIZED = "personalized"
    QUALITY = "quality"
    NAME = "name"
    RECENT = "recent"


class ExtensionQuery(BaseModel):
    """Catalog search input: user text + optional profile + sort + type filter."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    search_text: str = Field(
        default="", description="User-typed search box text. Empty means browse mode."
    )
    profile: UserProfile | None = Field(
        default=None, description="Loaded profile for personalized ranking; None if unavailable."
    )
    sort: SortMode = Field(default=SortMode.DEFAULT, description="Weight vector to apply.")
    extension_type: AgentExtensionType | None = Field(
        default=None, description="Optional extension-type filter applied before scoring."
    )


@dataclass(slots=True)
class ScoredExtension:
    """An extension with its composite score and per-signal breakdown.

    A dataclass (not pydantic) because this is an internal scoring result,
    not a schema that needs validation. At 28K items, pydantic construction
    adds ~25ms per query; dataclass instantiation is negligible.
    """

    extension_id: str
    composite_score: float
    signal_breakdown: dict[str, float] = field(default_factory=dict)


def coerce_legacy_sort(raw: str) -> SortMode:
    """Coerce deprecated sort values to the current enum.

    ``popularity`` and ``relevance`` were removed in favor of DEFAULT and
    PERSONALIZED, respectively. Unknown values default to DEFAULT.
    """
    raw = (raw or "").strip().lower()
    if raw == "popularity":
        return SortMode.DEFAULT
    if raw == "relevance":
        return SortMode.PERSONALIZED
    try:
        return SortMode(raw)
    except ValueError:
        return SortMode.DEFAULT
