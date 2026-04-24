"""Kimi CLI backend.

Invokes ``kimi --print --final-message-only`` as a subprocess.
``--print`` enables non-interactive mode with auto-approval, and
``--final-message-only`` skips intermediate tool output for clean results.

Does not support native JSON output — uses prompt-level schema augmentation.

System prompt: Kimi supports ``--agent-file <path>`` pointing to a YAML
agent definition with a ``system_prompt_path`` field. However, this requires
creating two temp files (agent YAML + system prompt .md) and declaring
tool configurations, making it too fragile for single-shot inference.
System and user prompts are combined in stdin instead.

References:
    - Agent customization: https://moonshotai.github.io/kimi-cli/en/customization/agents.html
    - CLI reference: https://moonshotai.github.io/kimi-cli/en/reference/kimi-command.html
"""

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.llm.inference import BackendType, InferenceRequest, InferenceResult


class KimiCliBackend(CliBackend):
    """Run inference via the Kimi CLI."""

    @property
    def cli_executable(self) -> str:
        return "kimi"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.KIMI

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

    def _thinking_args(self) -> list[str]:
        """Kimi thinking: explicit boolean toggle."""
        if self._config.thinking:
            return ["--thinking"]
        return ["--no-thinking"]

    def _parse_output(self, output: str, duration_ms: int) -> InferenceResult:
        """Return raw stdout as plain text (``--final-message-only`` yields plain text)."""
        return self._parse_plain_text(output, duration_ms)
