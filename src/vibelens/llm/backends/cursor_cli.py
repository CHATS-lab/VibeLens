"""Cursor CLI backend.

Invokes ``cursor -p -o json`` as a subprocess. Prompt is piped via stdin.
``-p`` enables headless print mode, ``-o json`` returns a JSON envelope,
and ``--model`` selects the inference model.

System prompt: Cursor has no CLI flag for system prompts. Customization
is file-based only (``.cursor/rules/`` directory, legacy ``.cursorrules``),
requiring persistent project files unsuitable for per-invocation overrides.
System and user prompts are combined in stdin.

Envelope shape (per Cursor docs):

    {"type": "result", "result": "<text>", "duration_ms": <int>, ...}

Cursor's CLI does not surface token usage or cost in the envelope.

References:
    - Output format: https://cursor.com/docs/cli/reference/output-format
    - CLI parameters: https://cursor.com/docs/cli/reference/parameters
    - Rules system: https://cursor.com/docs/rules
"""

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.llm.inference import BackendType, InferenceRequest, InferenceResult
from vibelens.models.trajectories.metrics import Metrics


class CursorCliBackend(CliBackend):
    """Run inference via the Cursor CLI."""

    @property
    def cli_executable(self) -> str:
        return "cursor"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.CURSOR

    @property
    def supports_native_json(self) -> bool:
        return True

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build cursor CLI command.

        Args:
            request: Inference request for model settings.

        Returns:
            Command as a list of strings.
        """
        cmd = [self._cli_path or self.cli_executable, "-p", "-o", "json"]
        if self._model:
            cmd.extend(["--model", self._model])
        return cmd

    def _thinking_args(self) -> list[str]:
        """Cursor reasoning effort: medium when thinking, omit when not."""
        if self._config.thinking:
            return ["--reasoning-effort", "medium"]
        return []

    def _parse_output(self, output: str, duration_ms: int) -> InferenceResult:
        """Parse Cursor's single-JSON envelope (text only, no usage)."""
        return self._parse_single_json(output, duration_ms, self._extract)

    def _extract(self, data: dict) -> tuple[str, Metrics | None, str]:
        """Pull the ``result`` string; Cursor reports no usage or cost."""
        return str(data.get("result", "")), None, self.model
