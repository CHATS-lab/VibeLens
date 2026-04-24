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

import re

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.llm.inference import BackendType, InferenceRequest, InferenceResult

# Matches ANSI CSI/OSC escape sequences so we can strip color/control codes
# from aider's terminal-oriented output before handing it to callers.
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")


class AiderCliBackend(CliBackend):
    """Run inference via the Aider CLI."""

    @property
    def cli_executable(self) -> str:
        return "aider"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.AIDER

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

    def _thinking_args(self) -> list[str]:
        """Aider thinking: both flags when on, disable tokens when off."""
        if self._config.thinking:
            return ["--reasoning-effort", "medium", "--thinking-tokens", "4k"]
        return ["--thinking-tokens", "0"]

    def _parse_output(self, output: str, duration_ms: int) -> InferenceResult:
        """Strip ANSI escapes and return stdout as plain text."""
        clean = _ANSI_ESCAPE_RE.sub("", output)
        return self._parse_plain_text(clean, duration_ms)
