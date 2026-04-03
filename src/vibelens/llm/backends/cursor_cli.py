"""Cursor CLI backend.

Invokes ``cursor -p -o json`` as a subprocess. Prompt is piped via stdin.
``-p`` enables headless print mode, ``-o json`` returns a JSON envelope,
and ``--model`` selects the inference model.
"""

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.inference import BackendType, InferenceRequest


class CursorCliBackend(CliBackend):
    """Run inference via the Cursor CLI."""

    @property
    def cli_executable(self) -> str:
        return "cursor"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.CURSOR_CLI

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
