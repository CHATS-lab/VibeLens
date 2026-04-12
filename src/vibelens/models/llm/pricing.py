"""Pricing model for LLM cost computation."""

from pydantic import BaseModel, ConfigDict, Field


class ModelPricing(BaseModel):
    """Per-million-token pricing for an LLM model (USD)."""

    model_config = ConfigDict(frozen=True)

    input_per_mtok: float = Field(description="Cost per million input tokens in USD.")
    output_per_mtok: float = Field(description="Cost per million output tokens in USD.")
    cache_read_per_mtok: float = Field(
        description="Cost per million cache-read input tokens in USD."
    )
    cache_write_per_mtok: float = Field(
        description="Cost per million cache-write input tokens in USD."
    )
