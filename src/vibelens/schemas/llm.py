"""LLM configuration request schemas."""

from pydantic import BaseModel, Field

from vibelens.models.llm.inference import BackendType


class LLMConfigureRequest(BaseModel):
    """Request body for runtime LLM backend configuration."""

    backend: BackendType = Field(default=BackendType.LITELLM, description="Backend type.")
    api_key: str = Field(
        default="", description="API key for the LLM provider. Empty to keep existing key."
    )
    model: str = Field(
        default="anthropic/claude-sonnet-4-5",
        description="Model in litellm format (e.g. 'anthropic/claude-sonnet-4-5').",
    )
    base_url: str | None = Field(
        default=None, description="Custom base URL (auto-resolved from provider if None)."
    )
    timeout: int = Field(default=120, description="Timeout in seconds.")
    max_tokens: int = Field(default=4096, description="Max output tokens.")
