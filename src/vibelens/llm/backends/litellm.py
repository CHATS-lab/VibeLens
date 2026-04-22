"""LiteLLM-based inference backend.

Unified backend for all LLM providers via litellm. Replaces vendor-specific
HTTP handling (Anthropic, OpenAI) with a single implementation that supports
any provider litellm can route to.
"""

from collections.abc import AsyncIterator

import litellm

from vibelens.config.settings import InferenceConfig
from vibelens.llm.backend import (
    InferenceBackend,
    InferenceError,
    InferenceRateLimitError,
    InferenceTimeoutError,
)
from vibelens.llm.providers import resolve_base_url
from vibelens.models.llm.inference import BackendType, InferenceRequest, InferenceResult
from vibelens.models.trajectories.metrics import Metrics
from vibelens.utils.log import get_logger
from vibelens.utils.timestamps import monotonic_ms

logger = get_logger(__name__)

# Suppress litellm's verbose default logging
litellm.suppress_debug_info = True


class LiteLLMBackend(InferenceBackend):
    """Inference backend using litellm for multi-provider LLM access.

    Supports any model/provider that litellm can route to. Model names
    use litellm's provider-prefixed format (e.g. 'anthropic/claude-sonnet-4-5').
    """

    def __init__(self, config: InferenceConfig, model_override: str | None = None):
        """Initialize LiteLLM backend from InferenceConfig.

        Args:
            config: Inference configuration.
            model_override: Override the model from config (used for legacy alias rewriting).
        """
        self._config = config
        self._model = model_override or config.model
        self._base_url = resolve_base_url(config)

    @property
    def model(self) -> str:
        """Return configured LiteLLM model name."""
        return self._model or "unknown"

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

        start_ms = monotonic_ms()
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
        duration_ms = monotonic_ms() - start_ms

        text = response.choices[0].message.content or ""
        metrics = _parse_metrics(response)
        metrics.cost_usd = _extract_cost(response)
        metrics.duration_ms = duration_ms

        logger.info(
            "LiteLLM inference complete: model=%s duration_ms=%d in_tokens=%d out_tokens=%d",
            response.model or self._model,
            duration_ms,
            metrics.prompt_tokens,
            metrics.completion_tokens,
        )

        return InferenceResult(text=text, model=response.model or self._model, metrics=metrics)

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
            "max_tokens": request.max_tokens or cfg.max_output_tokens,
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


def _parse_metrics(response) -> Metrics:
    """Extract token usage from a litellm response into a Metrics.

    Token bookkeeping matches the parser-side convention (see
    ``vibelens.ingest.parsers.base._compute_final_metrics``):

    - ``prompt_tokens`` holds only the non-cached input portion.
    - Anthropic-style cache fields (``cache_read_input_tokens``,
      ``cache_creation_input_tokens``) are captured separately.
    - OpenAI-style ``prompt_tokens_details.cached_tokens`` is used as a
      fallback when the provider is OpenAI-compatible.

    LiteLLM normalizes provider usage dicts into the response object,
    but cache fields may live at the top level or nested under
    ``prompt_tokens_details``, so both locations are checked.
    """
    usage = getattr(response, "usage", None)
    if not usage:
        return Metrics()
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
    if not cache_read:
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cache_read = getattr(details, "cached_tokens", 0) or 0
    # When the provider reports cache tokens nested inside prompt_tokens
    # (OpenAI convention), subtract them so prompt_tokens stays "new-only".
    if cache_read and cache_read <= prompt_tokens:
        prompt_tokens -= cache_read
    return Metrics(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cache_read,
        cache_creation_tokens=cache_create,
    )


def _extract_cost(response) -> float | None:
    """Extract cost from litellm response using litellm's built-in pricing."""
    try:
        cost = litellm.completion_cost(completion_response=response)
        return round(cost, 6) if cost else None
    except (ValueError, litellm.exceptions.NotFoundError):
        return None
