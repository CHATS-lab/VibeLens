"""Shared cost estimate response schema for all LLM analysis features."""

from pydantic import BaseModel, Field


class CostEstimateResponse(BaseModel):
    """Pre-flight cost estimate returned before running any LLM analysis."""

    model: str = Field(description="Model that will be used for analysis.")
    batch_count: int = Field(description="Number of LLM batches planned.")
    total_input_tokens: int = Field(description="Total input tokens across all calls.")
    total_output_tokens_budget: int = Field(description="Max output token budget.")
    cost_min_usd: float = Field(description="Optimistic cost estimate in USD.")
    cost_max_usd: float = Field(description="Pessimistic cost estimate in USD.")
    pricing_found: bool = Field(description="Whether model pricing was found.")
    formatted_cost: str = Field(description="Human-readable cost range string.")
