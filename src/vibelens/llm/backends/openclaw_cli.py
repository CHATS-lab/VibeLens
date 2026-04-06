"""OpenClaw CLI backend.

Invokes ``openclaw --message -`` as a subprocess. Prompt is piped via stdin.
Uses the ACP protocol for communication. Supports model override via
``--model``.

Does not support native JSON output — uses prompt-level schema augmentation.

System prompt: OpenClaw has no CLI flag for system prompts. It uses a
bootstrap file system (``SOUL.md``, ``AGENTS.md``, ``IDENTITY.md``, etc.)
that is live-reloaded from the workspace directory before each API call.
These require persistent project files unsuitable for per-invocation
overrides. System and user prompts are combined in stdin.

References:
    - System prompt docs: https://docs.openclaw.ai/concepts/system-prompt
"""

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.llm.inference import BackendType, InferenceRequest

OPENCLAW_CLI_MODELS = [
    "deepseek-v3",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "claude-haiku-4-5",
    "claude-sonnet-4-6",
    "gpt-5.4-mini",
    "gpt-5.4",
]
OPENCLAW_CLI_DEFAULT_MODEL = "deepseek-v3"


class OpenClawCliBackend(CliBackend):
    """Run inference via the OpenClaw CLI."""

    @property
    def cli_executable(self) -> str:
        return "openclaw"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.OPENCLAW_CLI

    @property
    def available_models(self) -> list[str]:
        return OPENCLAW_CLI_MODELS

    @property
    def default_model(self) -> str | None:
        return OPENCLAW_CLI_DEFAULT_MODEL

    @property
    def supports_freeform_model(self) -> bool:
        return True

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
