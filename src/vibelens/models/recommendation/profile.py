"""User profile model extracted from session analysis."""

from pydantic import BaseModel, Field


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
