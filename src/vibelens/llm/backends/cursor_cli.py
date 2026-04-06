"""Cursor CLI backend.

Invokes ``cursor -p -o json`` as a subprocess. Prompt is piped via stdin.
``-p`` enables headless print mode, ``-o json`` returns a JSON envelope,
and ``--model`` selects the inference model.

System prompt: Cursor has no CLI flag for system prompts. Customization
is file-based only (``.cursor/rules/`` directory, legacy ``.cursorrules``),
requiring persistent project files unsuitable for per-invocation overrides.
System and user prompts are combined in stdin.

References:
    - CLI parameters: https://cursor.com/docs/cli/reference/parameters
    - Rules system: https://cursor.com/docs/rules
"""

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.llm.inference import BackendType, InferenceRequest

CURSOR_CLI_MODELS = [
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "gpt-5.4",
    "gemini-2.5-pro",
]
CURSOR_CLI_DEFAULT_MODEL = "claude-sonnet-4-6"


class CursorCliBackend(CliBackend):
    """Run inference via the Cursor CLI."""

    @property
    def cli_executable(self) -> str:
        return "cursor"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.CURSOR_CLI

    @property
    def available_models(self) -> list[str]:
        return CURSOR_CLI_MODELS

    @property
    def default_model(self) -> str | None:
        return CURSOR_CLI_DEFAULT_MODEL

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
