"""LiteLLM-based inference backend.

Unified backend for all LLM providers via litellm. Replaces vendor-specific
HTTP handling (Anthropic, OpenAI) with a single implementation that supports
any provider litellm can route to.

File named litellm_backend.py (not litellm.py) to avoid shadowing the package.
"""

import time
from collections.abc import AsyncIterator

import litellm

from vibelens.config.llm_config import LLMConfig, resolve_base_url
from vibelens.llm.backend import (
    InferenceBackend,
    InferenceError,
    InferenceRateLimitError,
    InferenceTimeoutError,
)
from vibelens.models.inference import BackendType, InferenceRequest, InferenceResult, TokenUsage
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Suppress litellm's verbose default logging
litellm.suppress_debug_info = True


class LiteLLMBackend(InferenceBackend):
    """Inference backend using litellm for multi-provider LLM access.

    Supports any model/provider that litellm can route to. Model names
    use litellm's provider-prefixed format (e.g. 'anthropic/claude-sonnet-4-5').
    """

    def __init__(self, config: LLMConfig, model_override: str | None = None):
        """Initialize LiteLLM backend from LLMConfig.

        Args:
            config: Full LLM configuration.
            model_override: Override the model from config (used for legacy alias rewriting).
        """
        self._config = config
        self._model = model_override or config.model
        self._base_url = resolve_base_url(config)

    async def generate(self, request: InferenceRequest) -> InferenceResult:
        """Send a non-streaming completion request via litellm.

        Args:
            request: Provider-agnostic inference request.

        Returns:
            InferenceResult with generated text and usage.

        Raises:
            InferenceTimeoutError: On request timeout.
            InferenceRateLimitError: On 429 responses.
            InferenceError: On other API errors.
        """
        messages = _build_messages(request)
        kwargs = self._build_kwargs(request)

        start_ms = _now_ms()
        try:
            response = await litellm.acompletion(messages=messages, **kwargs)
        except litellm.exceptions.Timeout as exc:
            raise InferenceTimeoutError(f"Request timed out: {exc}") from exc
        except litellm.exceptions.AuthenticationError as exc:
            raise InferenceError(f"Authentication failed — check your API key: {exc}") from exc
        except litellm.exceptions.RateLimitError as exc:
            raise InferenceRateLimitError(f"Rate limited: {exc}") from exc
        except litellm.exceptions.APIError as exc:
            raise InferenceError(f"LiteLLM API error: {exc}") from exc
        duration_ms = _now_ms() - start_ms

        text = response.choices[0].message.content or ""
        usage = _parse_usage(response)
        cost = _extract_cost(response)

        return InferenceResult(
            text=text,
            model=response.model or self._model,
            usage=usage,
            cost_usd=cost,
            duration_ms=duration_ms,
        )

    async def generate_stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        """Stream generated text via litellm.

        Args:
            request: Provider-agnostic inference request.

        Yields:
            Text chunks as they arrive.
        """
        messages = _build_messages(request)
        kwargs = self._build_kwargs(request)

        try:
            response = await litellm.acompletion(messages=messages, stream=True, **kwargs)
            async for chunk in response:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        except litellm.exceptions.Timeout as exc:
            raise InferenceTimeoutError(f"Stream timed out: {exc}") from exc
        except litellm.exceptions.AuthenticationError as exc:
            raise InferenceError(f"Authentication failed — check your API key: {exc}") from exc
        except litellm.exceptions.RateLimitError as exc:
            raise InferenceRateLimitError(f"Rate limited: {exc}") from exc
        except litellm.exceptions.APIError as exc:
            raise InferenceError(f"LiteLLM stream error: {exc}") from exc

    async def is_available(self) -> bool:
        """Check if the API key is configured."""
        return bool(self._config.api_key)

    @property
    def backend_id(self) -> BackendType:
        """Return the backend type identifier."""
        return BackendType.LITELLM

    def _build_kwargs(self, request: InferenceRequest) -> dict:
        """Build keyword arguments for litellm.acompletion."""
        cfg = self._config
        kwargs: dict = {
            "model": self._model,
            "api_key": cfg.api_key,
            "max_tokens": request.max_tokens or cfg.max_tokens,
            "temperature": request.temperature,
            "timeout": request.timeout or cfg.timeout,
        }
        if self._base_url:
            kwargs["api_base"] = self._base_url
        if request.json_schema:
            kwargs["response_format"] = {"type": "json_object"}
        return kwargs


def _build_messages(request: InferenceRequest) -> list[dict]:
    """Build the messages list from an InferenceRequest."""
    return [
        {"role": "system", "content": request.system},
        {"role": "user", "content": request.user},
    ]


def _parse_usage(response) -> TokenUsage | None:
    """Extract token usage from a litellm response."""
    usage = getattr(response, "usage", None)
    if not usage:
        return None
    return TokenUsage(
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
    )


def _extract_cost(response) -> float | None:
    """Extract cost from litellm response using litellm's built-in pricing."""
    try:
        cost = litellm.completion_cost(completion_response=response)
        return round(cost, 6) if cost else None
    except Exception:
        return None


def _now_ms() -> int:
    """Return current time in milliseconds."""
    return int(time.monotonic() * 1000)
