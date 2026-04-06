"""OpenCode CLI backend.

Invokes ``opencode -p - -q -f json --system <prompt>`` as a subprocess.
The user prompt is piped via stdin. ``-q`` suppresses the interactive spinner
for scripted usage, and ``-f json`` returns structured JSON output.

The system prompt is passed via ``--system`` to properly separate system
and user prompts, avoiding duplication in stdin.
"""

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.llm.inference import BackendType, InferenceRequest

OPENCODE_CLI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "claude-haiku-4-5",
    "claude-sonnet-4-6",
    "gpt-5.4-mini",
    "gpt-5.4",
]
OPENCODE_CLI_DEFAULT_MODEL = "gemini-2.5-flash"


class OpenCodeCliBackend(CliBackend):
    """Run inference via the OpenCode CLI."""

    @property
    def cli_executable(self) -> str:
        return "opencode"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.OPENCODE_CLI

    @property
    def available_models(self) -> list[str]:
        return OPENCODE_CLI_MODELS

    @property
    def default_model(self) -> str | None:
        return OPENCODE_CLI_DEFAULT_MODEL

    @property
    def supports_freeform_model(self) -> bool:
        return True

    @property
    def supports_native_json(self) -> bool:
        return True

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build opencode CLI command.

        Passes the system prompt via ``--system`` for clean
        system/user separation. Stdin carries only the user prompt.

        Args:
            request: Inference request for prompt settings.

        Returns:
            Command as a list of strings.
        """
        cmd = [
            self._cli_path or self.cli_executable,
            "-p",
            "-",
            "-q",
            "-f",
            "json",
            "--system",
            request.system,
        ]
        if self._model:
            cmd.extend(["--model", self._model])
        return cmd

    def _build_prompt(self, request: InferenceRequest) -> str:
        """Return only the user prompt.

        The system prompt is passed via ``--system`` in
        ``_build_command``, so stdin carries only the user content.

        Args:
            request: Inference request with system and user prompts.

        Returns:
            User prompt text only.
        """
        return request.user
