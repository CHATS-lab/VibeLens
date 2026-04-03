"""Kimi CLI backend.

Invokes ``kimi --print --final-message-only`` as a subprocess.
``--print`` enables non-interactive mode with auto-approval, and
``--final-message-only`` skips intermediate tool output for clean results.

Does not support native JSON output — uses prompt-level schema augmentation.
"""

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.inference import BackendType, InferenceRequest


class KimiCliBackend(CliBackend):
    """Run inference via the Kimi CLI."""

    @property
    def cli_executable(self) -> str:
        return "kimi"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.KIMI_CLI

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build kimi CLI command.

        Args:
            request: Inference request for model settings.

        Returns:
            Command as a list of strings.
        """
        cmd = [self._cli_path or self.cli_executable, "--print", "--final-message-only"]
        if self._model:
            cmd.extend(["--model", self._model])
        return cmd
