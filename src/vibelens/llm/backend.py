"""InferenceBackend ABC and inference exceptions.

Defines the transport abstraction for LLM text generation.
Implementations handle wire protocol details (HTTP, subprocess, stdio).
Callers handle prompt construction and response parsing.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from vibelens.models.inference import InferenceRequest, InferenceResult


class InferenceError(Exception):
    """Base exception for inference failures."""


class InferenceTimeoutError(InferenceError):
    """Raised when an inference request exceeds the configured timeout."""


class InferenceRateLimitError(InferenceError):
    """Raised when the backend returns a rate-limit response."""


class InferenceBackend(ABC):
    """Transport layer for LLM text generation.

    Implementations handle the wire protocol (HTTP, subprocess, stdio).
    Callers handle prompt construction and response parsing.

    Subclasses must implement:
        - generate() — synchronous completion
        - is_available() — can the backend accept requests right now
        - backend_id — unique identifier string for this backend type
    """

    @abstractmethod
    async def generate(self, request: InferenceRequest) -> InferenceResult:
        """Send a prompt and return the generated text.

        Args:
            request: Provider-agnostic inference request.

        Returns:
            InferenceResult with generated text and metadata.

        Raises:
            InferenceError: On any generation failure.
            InferenceTimeoutError: When the request exceeds timeout.
            InferenceRateLimitError: When rate-limited by the provider.
        """

    async def generate_stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        """Stream generated text token-by-token.

        Default implementation falls back to non-streaming generate().
        HTTP backends override this for true SSE streaming.

        Args:
            request: Provider-agnostic inference request.

        Yields:
            Text chunks as they are generated.
        """
        result = await self.generate(request)
        yield result.text

    @abstractmethod
    async def is_available(self) -> bool:
        """Check whether the backend can accept requests.

        Returns:
            True if the backend is ready to generate.
        """

    @property
    @abstractmethod
    def backend_id(self) -> str:
        """Unique identifier for this backend type (e.g. 'claude-cli', 'anthropic-api')."""
