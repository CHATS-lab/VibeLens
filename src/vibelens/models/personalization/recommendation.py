"""Recommendation pipeline models — catalog, profile, rationale, and ranked items."""

from pydantic import BaseModel, Field

from vibelens.models.enums import AgentExtensionType
from vibelens.models.personalization.constants import DESCRIPTION_RATIONALE


class RecommendationItem(BaseModel):
    """A catalog item surfaced by the recommendation pipeline."""

    extension_id: str = Field(description="Unique identifier.")
    extension_type: AgentExtensionType = Field(description="Classified type.")
    name: str = Field(description="Display name.")
    repo_name: str = Field(description="GitHub owner/repo.")
    source_url: str = Field(description="GitHub URL.")
    updated_at: str = Field(description="Last commit ISO timestamp.")
    description: str = Field(description="Plain language, 1-2 sentences.")
    tags: list[str] = Field(description="Searchable tags.")
    stars: int = Field(default=0, description="GitHub star count.")
    forks: int = Field(default=0, description="GitHub fork count.")
    license: str = Field(default="", description="Repository license identifier (e.g. MIT).")
    language: str = Field(default="", description="Primary repository language.")
    install_command: str | None = Field(default=None, description="CLI install command.")


class UserProfile(BaseModel):
    """Aggregated user profile from L2 profile generation.

    Captures the user's development context, workflow style, and recurring
    friction points. Used by L3 retrieval for scoring and L4 for rationale.
    """

    domains: list[str] = Field(description="Development domains, e.g. web-dev, data-pipeline.")
    languages: list[str] = Field(description="Programming languages, e.g. python, typescript.")
    frameworks: list[str] = Field(description="Frameworks/libraries, e.g. fastapi, react.")
    agent_platforms: list[str] = Field(description="Agent platforms used, e.g. claude-code, codex.")
    bottlenecks: list[str] = Field(
        description="Recurring friction points, e.g. repeated test failures, slow CI."
    )
    workflow_style: str = Field(
        description="Characteristic workflow style, e.g. iterative debugger, prefers small commits."
    )
    search_keywords: list[str] = Field(
        description="20-30 catalog-friendly search terms derived from session content."
    )


class RationaleItem(BaseModel):
    """LLM-generated rationale for a single candidate."""

    item_id: str = Field(description="RecommendationItem reference.")
    rationale: str = Field(description=DESCRIPTION_RATIONALE)
    relevance: float = Field(
        description="How closely the item matches the user's stack and bottlenecks (0.0-1.0)."
    )


class RationaleOutput(BaseModel):
    """LLM output for L4 rationale generation."""

    rationales: list[RationaleItem] = Field(description="Per-candidate personalized rationales.")


class RankedRecommendationItem(BaseModel):
    """A ranked recommendation with catalog data, rationale, and scores."""

    item: RecommendationItem = Field(description="Catalog item data (built by service, not LLM).")
    rationale: str = Field(description=DESCRIPTION_RATIONALE)
    scores: dict[str, float] = Field(
        default_factory=dict, description="Signal scores, e.g. relevance, quality, popularity."
    )
