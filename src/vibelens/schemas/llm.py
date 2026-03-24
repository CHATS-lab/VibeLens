"""LLM configuration request schemas."""

from pydantic import BaseModel, Field


class LLMConfigureRequest(BaseModel):
    """Request body for runtime LLM backend configuration."""

    api_key: str = Field(description="API key for the LLM provider.")
    model: str = Field(
        default="anthropic/claude-sonnet-4-5",
        description="Model in litellm format (e.g. 'anthropic/claude-sonnet-4-5').",
    )
