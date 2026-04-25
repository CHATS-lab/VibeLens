"""OpenCode CLI backend.

Invokes ``opencode run --format json <message>`` as a subprocess. The new
OpenCode CLI (>= 1.14) uses a subcommand + positional message and emits
NDJSON event records: ``step_start``, ``text``, ``step_finish``, etc.

System prompt: OpenCode does not expose a ``--system`` flag in the ``run``
subcommand. The combined system + user prompt is passed as the message.

Thinking: OpenCode has a native ``--thinking`` boolean (show thinking
blocks) and ``--variant`` for reasoning effort.

References:
    - ``opencode run --help``
"""

from vibelens.llm.backend import InferenceError
from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.llm.inference import BackendType, InferenceRequest, InferenceResult
from vibelens.models.trajectories.metrics import Metrics

_EVENT_TEXT = "text"
_EVENT_STEP_FINISH = "step_finish"


class OpenCodeCliBackend(CliBackend):
    """Run inference via the OpenCode CLI."""

    @property
    def cli_executable(self) -> str:
        return "opencode"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.OPENCODE

    @property
    def supports_freeform_model(self) -> bool:
        return True

    @property
    def supports_native_json(self) -> bool:
        return True

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build opencode run command with the combined prompt as the message arg."""
        message = self._build_prompt(request)
        cmd = [
            self._cli_path or self.cli_executable,
            "run",
            "--format",
            "json",
            "--dangerously-skip-permissions",
        ]
        if self._model:
            cmd.extend(["--model", self._model])
        cmd.append(message)
        return cmd

    def _build_prompt(self, request: InferenceRequest) -> str:
        """Combine system + user into a single message.

        The system prompt (rendered via ``_output_envelope.j2``) already
        embeds the JSON schema, so we skip the backend-side schema
        augmentation that the base class would apply. Appending a second
        copy confuses small models — gpt-5-nano echoed the schema back
        verbatim instead of producing an instance.
        """
        return f"{request.system}\n\n{request.user}"

    def _thinking_args(self) -> list[str]:
        """OpenCode has native ``--thinking`` (show blocks) + ``--variant`` (reasoning effort).

        ``--variant minimal`` is the lowest reasoning level OpenCode core
        currently supports via CLI; a ``none`` variant is requested upstream
        but not yet shipped (https://github.com/sst/opencode/issues/4316).
        For non-reasoning models ``minimal`` is effectively off; for reasoning
        models a reduced reasoning pass still runs.

        The ``--thinking`` boolean only controls visibility of thinking
        blocks in the output, not whether the model thinks.
        """
        if self._config.thinking:
            return ["--thinking", "--variant", "high"]
        return ["--variant", "minimal"]

    def _parse_output(self, output: str, duration_ms: int) -> InferenceResult:
        """Parse OpenCode's NDJSON event stream.

        Text comes from every ``text`` event's ``part.text``. Token usage
        lives on the final ``step_finish`` event's ``part.tokens``.
        """
        text_parts: list[str] = []
        metrics: Metrics | None = None
        for event in self._iter_ndjson_events(output):
            event_type = event.get("type")
            part = event.get("part")
            if not isinstance(part, dict):
                continue
            if event_type == _EVENT_TEXT:
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
            elif event_type == _EVENT_STEP_FINISH:
                tokens = part.get("tokens")
                if isinstance(tokens, dict):
                    cache = tokens.get("cache", {}) if isinstance(tokens.get("cache"), dict) else {}
                    metrics = Metrics(
                        prompt_tokens=tokens.get("input", 0),
                        completion_tokens=tokens.get("output", 0),
                        cache_read_tokens=cache.get("read", 0),
                        cache_write_tokens=cache.get("write", 0),
                    )

        if not text_parts:
            raise InferenceError("opencode NDJSON stream contained no text events")
        if metrics is None:
            metrics = Metrics()
        metrics.duration_ms = duration_ms
        return InferenceResult(text="".join(text_parts).strip(), model=self.model, metrics=metrics)
