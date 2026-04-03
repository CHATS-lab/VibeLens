"""OpenAI Codex CLI backend.

Invokes ``codex exec --json --sandbox read-only`` as a subprocess.
Supports native JSON output and schema validation via ``--output-schema``.

Safety flags: ``--ephemeral`` skips session persistence, ``--sandbox read-only``
prevents writes, and ``--skip-git-repo-check`` allows running outside repos.
"""

import json

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.inference import BackendType, InferenceRequest


class CodexCliBackend(CliBackend):
    """Run inference via the OpenAI Codex CLI."""

    @property
    def cli_executable(self) -> str:
        return "codex"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.CODEX_CLI

    @property
    def supports_native_json(self) -> bool:
        return True

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build codex CLI command.

        Creates a temp schema file for ``--output-schema`` when the
        request includes a JSON schema constraint.

        Args:
            request: Inference request for model and schema settings.

        Returns:
            Command as a list of strings.
        """
        cmd = [
            self._cli_path or self.cli_executable,
            "exec",
            "--json",
            "--sandbox",
            "read-only",
            "--ephemeral",
            "--skip-git-repo-check",
        ]
        if self._model:
            cmd.extend(["--model", self._model])
        if request.json_schema:
            schema_path = self._create_tempfile(
                json.dumps(request.json_schema, indent=2),
                suffix=".json",
                prefix="vibelens_schema_",
            )
            cmd.extend(["--output-schema", str(schema_path)])
        return cmd
