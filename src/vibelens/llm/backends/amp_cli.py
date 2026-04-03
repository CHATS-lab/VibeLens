"""Amp CLI backend.

Invokes ``amp --headless --stream-json`` as a subprocess. Prompt is piped
via stdin. ``--headless`` enables non-interactive mode, and ``--stream-json``
produces structured NDJSON event output (one JSON object per line).
"""

import json

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.inference import BackendType, InferenceRequest, InferenceResult


class AmpCliBackend(CliBackend):
    """Run inference via the Amp CLI."""

    @property
    def cli_executable(self) -> str:
        return "amp"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.AMP_CLI

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build amp CLI command.

        Args:
            request: Inference request (unused beyond base class).

        Returns:
            Command as a list of strings.
        """
        return [self._cli_path or self.cli_executable, "--headless", "--stream-json"]

    def _parse_output(self, output: str, duration_ms: int) -> InferenceResult:
        """Parse NDJSON output by extracting the last valid JSON line.

        ``--stream-json`` emits one JSON object per line. We take the last
        valid JSON line (typically the final event/result) and delegate
        to the base class parser for envelope extraction.

        Args:
            output: Raw NDJSON stdout from amp.
            duration_ms: Elapsed time in milliseconds.

        Returns:
            Parsed InferenceResult.
        """
        last_json_line = self._extract_last_json_line(output)
        return super()._parse_output(last_json_line, duration_ms)

    def _extract_last_json_line(self, output: str) -> str:
        """Find the last valid JSON line in NDJSON output.

        Args:
            output: Raw NDJSON output.

        Returns:
            The last line that parses as valid JSON, or the full output
            if no valid JSON line is found.
        """
        for line in reversed(output.splitlines()):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                json.loads(stripped)
                return stripped
            except (json.JSONDecodeError, ValueError):
                continue
        return output
