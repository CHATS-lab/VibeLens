"""Aider CLI backend.

Invokes ``aider --message - --no-auto-commits --yes --no-stream`` as a
subprocess. Prompt is piped via stdin. ``--yes`` auto-approves all actions
to prevent hanging, and ``--no-stream`` produces clean non-streaming output.

Does not support native JSON output — uses prompt-level schema augmentation.

System prompt: Aider has no ``--system-prompt`` flag. The ``--read`` flag
injects files as user-level context (not a true system prompt), and
``--show-prompts`` is debug-only (view, not customize). System and user
prompts are combined in stdin.

References:
    - CLI options: https://aider.chat/docs/config/options.html
    - Conventions via --read: https://aider.chat/docs/usage/conventions.html
    - Feature request: https://github.com/Aider-AI/aider/issues/3364
"""

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.llm.inference import BackendType, InferenceRequest

AIDER_CLI_MODELS = [
    "deepseek-v3",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "claude-haiku-4-5",
    "claude-sonnet-4-6",
    "gpt-5.4-mini",
    "gpt-5.4",
]
AIDER_CLI_DEFAULT_MODEL = "deepseek-v3"


class AiderCliBackend(CliBackend):
    """Run inference via the Aider CLI."""

    @property
    def cli_executable(self) -> str:
        return "aider"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.AIDER_CLI

    @property
    def available_models(self) -> list[str]:
        return AIDER_CLI_MODELS

    @property
    def default_model(self) -> str | None:
        return AIDER_CLI_DEFAULT_MODEL

    @property
    def supports_freeform_model(self) -> bool:
        return True

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
