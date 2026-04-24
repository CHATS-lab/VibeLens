"""Amp CLI backend.

Invokes ``amp --headless --stream-json`` as a subprocess. Prompt is piped
via stdin. ``--headless`` enables non-interactive mode, and ``--stream-json``
produces structured NDJSON event output (one JSON object per line).

System prompt: Amp has no CLI flag for system prompts. The
``amp.systemPrompt`` config key is documented as "SDK use only", and
``AGENTS.md`` files provide project-level context but require persistent
files. System and user prompts are combined in stdin.

NDJSON event stream (per ``--stream-json`` docs)::

    {"type": "initial", ...}
    {"type": "assistant", "message": {
        "role": "assistant",
        "content": [{"type": "text", "text": "..."}],
        "usage": {
            "input_tokens": <int>,
            "output_tokens": <int>,
            "cache_creation_input_tokens": <int>,
            "cache_read_input_tokens": <int>
        }
    }}
    {"type": "result", "result": "<aggregate text>"}

References:
    - Owner's manual: https://ampcode.com/manual
    - Streaming JSON format: https://ampcode.com/news/streaming-json
"""

from vibelens.llm.backend import InferenceError
from vibelens.llm.backends.cli_base import CliBackend
from vibelens.llm.usage import metrics_from_anthropic_usage
from vibelens.models.llm.inference import BackendType, InferenceRequest, InferenceResult
from vibelens.models.trajectories.metrics import Metrics

# NDJSON event type labels emitted by ``amp --stream-json``
EVENT_ASSISTANT = "assistant"
EVENT_RESULT = "result"


class AmpCliBackend(CliBackend):
    """Run inference via the Amp CLI."""

    @property
    def cli_executable(self) -> str:
        return "amp"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.AMP

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build amp CLI command.

        Args:
            request: Inference request (unused beyond base class).

        Returns:
            Command as a list of strings.
        """
        return [self._cli_path or self.cli_executable, "--headless", "--stream-json"]

    def _parse_output(self, output: str, duration_ms: int) -> InferenceResult:
        """Parse Amp's NDJSON event stream.

        Prefers the last ``assistant`` event's ``message.content[*].text``
        plus its ``usage``. Falls back to a trailing ``result`` event's
        ``result`` string if no assistant event was seen.

        Args:
            output: Raw NDJSON stdout from amp.
            duration_ms: Elapsed time in milliseconds.

        Returns:
            Parsed InferenceResult.
        """
        last_assistant: dict | None = None
        last_result_text: str | None = None
        for event in self._iter_ndjson_events(output):
            event_type = event.get("type")
            if event_type == EVENT_ASSISTANT:
                last_assistant = event
            elif event_type == EVENT_RESULT:
                fallback = event.get("result")
                if isinstance(fallback, str):
                    last_result_text = fallback

        text = ""
        metrics: Metrics | None = None
        if last_assistant:
            message = last_assistant.get("message", {})
            if isinstance(message, dict):
                text = _join_content_text(message.get("content", []))
                usage_data = message.get("usage")
                if isinstance(usage_data, dict):
                    metrics = metrics_from_anthropic_usage(usage_data)
        if not text and last_result_text is not None:
            text = last_result_text

        if not text:
            raise InferenceError("amp NDJSON stream contained no assistant text or result event")

        if metrics is None:
            metrics = Metrics()
        metrics.duration_ms = duration_ms
        return InferenceResult(text=text, model=self.model, metrics=metrics)


def _join_content_text(content: object) -> str:
    """Concatenate ``text`` fields from Anthropic-style content blocks."""
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            block_text = block.get("text")
            if isinstance(block_text, str):
                parts.append(block_text)
    return "".join(parts)
