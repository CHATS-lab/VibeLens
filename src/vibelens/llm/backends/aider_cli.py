"""Aider CLI backend.

Invokes ``aider --message - --no-auto-commits --yes --no-stream`` as a
subprocess. Prompt is piped via stdin. ``--yes`` auto-approves all actions
to prevent hanging, and ``--no-stream`` produces clean non-streaming output.

Does not support native JSON output — uses prompt-level schema augmentation.
"""

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.inference import BackendType, InferenceRequest


class AiderCliBackend(CliBackend):
    """Run inference via the Aider CLI."""

    @property
    def cli_executable(self) -> str:
        return "aider"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.AIDER_CLI

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build aider CLI command.

        Args:
            request: Inference request for model settings.

        Returns:
            Command as a list of strings.
        """
        cmd = [
            self._cli_path or self.cli_executable,
            "--message",
            "-",
            "--no-auto-commits",
            "--yes",
            "--no-stream",
        ]
        if self._model:
            cmd.extend(["--model", self._model])
        return cmd
