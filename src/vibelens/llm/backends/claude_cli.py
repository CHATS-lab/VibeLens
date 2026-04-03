"""Claude Code CLI backend.

Invokes ``claude -p`` with ``--system-prompt`` to properly separate system
and user prompts. The ``--output-format json`` flag wraps the response in a
JSON envelope with ``result``, ``usage``, and ``modelUsage`` fields.

Safety flags prevent agentic behavior during scripted inference:
``--no-session-persistence`` avoids polluting history, ``--tools ""``
disables all tool use for pure text inference.
"""

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.inference import BackendType, InferenceRequest


class ClaudeCliBackend(CliBackend):
    """Run inference via the Claude Code CLI."""

    @property
    def cli_executable(self) -> str:
        return "claude"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.CLAUDE_CLI

    @property
    def supports_native_json(self) -> bool:
        return True

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build claude CLI command.

        Passes the system prompt via ``--system-prompt`` for clean
        system/user separation. Stdin carries only the user prompt.

        Args:
            request: Inference request for model and prompt settings.

        Returns:
            Command as a list of strings.
        """
        cmd = [
            self._cli_path or self.cli_executable,
            "-p",
            "-",
            "--output-format",
            "json",
            "--system-prompt",
            request.system,
            "--no-session-persistence",
            "--tools",
            "",
        ]
        if self._model:
            cmd.extend(["--model", self._model])
        return cmd

    def _build_prompt(self, request: InferenceRequest) -> str:
        """Return only the user prompt.

        The system prompt is passed via ``--system-prompt`` in
        ``_build_command``, so stdin carries only the user content.

        Args:
            request: Inference request with system and user prompts.

        Returns:
            User prompt text only.
        """
        return request.user
