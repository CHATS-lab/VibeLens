"""Inference request and result models for LLM backends."""

from enum import StrEnum

from pydantic import BaseModel, Field


class BackendType(StrEnum):
    """Inference backend type identifier."""

    LITELLM = "litellm"
    CLAUDE_CLI = "claude-cli"
    CODEX_CLI = "codex-cli"
    GEMINI_CLI = "gemini-cli"
    CURSOR_CLI = "cursor-cli"
    KIMI_CLI = "kimi-cli"
    OPENCLAW_CLI = "openclaw-cli"
    OPENCODE_CLI = "opencode-cli"
    AIDER_CLI = "aider-cli"
    AMP_CLI = "amp-cli"
    MOCK = "mock"
    DISABLED = "disabled"


class TokenUsage(BaseModel):
    """Token counts for an inference request."""

    input_tokens: int = Field(default=0, description="Number of input tokens consumed.")
    output_tokens: int = Field(default=0, description="Number of output tokens generated.")


class InferenceRequest(BaseModel):
    """Provider-agnostic LLM inference request.

    Callers construct this with prompt content and generation parameters.
    Backend implementations translate it into provider-specific wire format.
    """

    system: str = Field(description="System prompt setting the LLM's role and constraints.")
    user: str = Field(description="User prompt content to generate a response for.")
    max_tokens: int = Field(default=4096, description="Maximum number of output tokens.")
    temperature: float = Field(
        default=0.0, description="Sampling temperature (0.0 = deterministic)."
    )
    timeout: int | None = Field(
        default=None, description="Request timeout in seconds. None uses the backend default."
    )
    json_schema: dict | None = Field(
        default=None,
        description="JSON schema for structured output constraint. None for free-form text.",
    )


class InferenceResult(BaseModel):
    """Result from an LLM inference call.

    Returned by all backend implementations regardless of transport.
    """

    text: str = Field(description="Generated text content.")
    model: str = Field(description="Model identifier that produced this result.")
    usage: TokenUsage | None = Field(default=None, description="Token usage statistics.")
    cost_usd: float | None = Field(
        default=None,
        description="Estimated cost in USD. None for free backends (CLI subscriptions).",
    )
    duration_ms: int = Field(default=0, description="Wall-clock generation time in milliseconds.")
