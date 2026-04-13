"""Recommendation API request/response schemas."""

from pydantic import BaseModel, Field


class RecommendationAnalyzeRequest(BaseModel):
    """Request body for starting a recommendation analysis."""

    session_ids: list[str] = Field(description="Session IDs to analyze for recommendations.")


class CatalogStatusResponse(BaseModel):
    """Response for catalog status check."""

    version: str = Field(description="Catalog version date.")
    item_count: int = Field(description="Number of items in the catalog.")
    schema_version: int = Field(description="Catalog schema version.")
