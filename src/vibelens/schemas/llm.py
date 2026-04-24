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
        default="anthropic/claude-haiku-4-5",
        description="Model in litellm format (e.g. 'anthropic/claude-haiku-4-5').",
    )
    base_url: str | None = Field(
        default=None, description="Custom base URL (auto-resolved from provider if None)."
    )
    timeout: int = Field(default=300, description="Timeout in seconds.")
    max_output_tokens: int = Field(default=10000, description="Max output tokens.")
    thinking: bool = Field(
        default=False,
        description="Enable extended thinking / reasoning mode for supported backends.",
    )
