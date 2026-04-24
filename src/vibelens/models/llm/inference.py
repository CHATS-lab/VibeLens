"""Inference request and result models for LLM backends."""

from pathlib import Path

from pydantic import BaseModel, Field

from vibelens.models.trajectories.metrics import Metrics
from vibelens.utils.compat import StrEnum


class BackendType(StrEnum):
    """Inference backend type identifier."""

    LITELLM = "litellm"
    AIDER = "aider"
    AMP = "amp"
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    CURSOR = "cursor"
    GEMINI = "gemini"
    KIMI = "kimi"
    OPENCODE = "opencode"
    OPENCLAW = "openclaw"
    MOCK = "mock"
    DISABLED = "disabled"

    @classmethod
    def _missing_(cls, value: object) -> "BackendType | None":
        """Resolve legacy backend names from persisted analysis results."""
        if isinstance(value, str):
            resolved = _BACKEND_LEGACY_ALIASES.get(value)
            if resolved:
                return cls(resolved)
        return None


_BACKEND_LEGACY_ALIASES: dict[str, str] = {
    "anthropic-api": "litellm",
    "openai-api": "litellm",
    "claude-cli": "claude_code",
    "codex-cli": "codex",
    "gemini-cli": "gemini",
    "gemini_cli": "gemini",
    "cursor-cli": "cursor",
    "kimi-cli": "kimi",
    "openclaw-cli": "openclaw",
    "opencode-cli": "opencode",
    "aider-cli": "aider",
    "amp-cli": "amp",
}


class InferenceRequest(BaseModel):
    """Provider-agnostic LLM inference request.

    Callers construct this with prompt content and generation parameters.
    Backend implementations translate it into provider-specific wire format.
    """

    system: str = Field(description="System prompt setting the LLM's role and constraints.")
    user: str = Field(description="User prompt content to generate a response for.")
    max_tokens: int = Field(default=4096, description="Maximum number of output tokens.")
    temperature: float = Field(
        default=1.0, description="Sampling temperature (1.0 = deterministic)."
    )
    timeout: int | None = Field(
        default=None, description="Request timeout in seconds. None uses the backend default."
    )
    json_schema: dict | None = Field(
        default=None,
        description="JSON schema for structured output constraint. None for free-form text.",
    )
    analysis_cwd: Path | None = Field(
        default=None,
        description=(
            "Working directory for CLI subprocess backends. When set, the backend "
            "spawns its child process with this cwd so per-call side files land in "
            "a caller-controlled location. None uses the backend default."
        ),
    )


class InferenceResult(BaseModel):
    """Result from an LLM inference call.

    Returned by all backend implementations regardless of transport.
    """

    text: str = Field(description="Generated text content.")
    model: str = Field(description="Model identifier that produced this result.")
    metrics: Metrics = Field(
        default_factory=Metrics,
        description="Token usage, cost, and timing for this inference call.",
    )
