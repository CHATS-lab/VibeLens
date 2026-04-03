"""OpenClaw CLI backend.

Invokes ``openclaw --message -`` as a subprocess. Prompt is piped via stdin.
Uses the ACP protocol for communication. Supports model override via
``--model``.

Does not support native JSON output — uses prompt-level schema augmentation.
"""

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.inference import BackendType, InferenceRequest


class OpenClawCliBackend(CliBackend):
    """Run inference via the OpenClaw CLI."""

    @property
    def cli_executable(self) -> str:
        return "openclaw"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.OPENCLAW_CLI

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build openclaw CLI command.

        Args:
            request: Inference request for model settings.

        Returns:
            Command as a list of strings.
        """
        cmd = [self._cli_path or self.cli_executable, "--message", "-"]
        if self._model:
            cmd.extend(["--model", self._model])
        return cmd
