"""OpenCode CLI backend.

Invokes ``opencode -p - -q -f json`` as a subprocess. Prompt is piped via
stdin. ``-q`` suppresses the interactive spinner for scripted usage, and
``-f json`` returns structured JSON output.
"""

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.inference import BackendType, InferenceRequest


class OpenCodeCliBackend(CliBackend):
    """Run inference via the OpenCode CLI."""

    @property
    def cli_executable(self) -> str:
        return "opencode"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.OPENCODE_CLI

    @property
    def supports_native_json(self) -> bool:
        return True

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build opencode CLI command.

        Args:
            request: Inference request (unused beyond base class).

        Returns:
            Command as a list of strings.
        """
        return [self._cli_path or self.cli_executable, "-p", "-", "-q", "-f", "json"]
