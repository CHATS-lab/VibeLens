"""OpenAI Codex CLI backend.

Invokes ``codex exec --json --sandbox read-only`` as a subprocess.
Supports native JSON output and schema validation via ``--output-schema``.

Safety flags: ``--ephemeral`` skips session persistence, ``--sandbox read-only``
prevents writes, and ``--skip-git-repo-check`` allows running outside repos.

System prompt: Codex supports ``-c model_instructions_file=<path>`` and
``-c developer_instructions="..."`` as global config overrides, but these
are top-level flags for the interactive ``codex`` command — the ``exec``
subcommand does not accept them. System and user prompts are combined
in stdin as a workaround.

References:
    - Config reference: https://developers.openai.com/codex/config-reference
    - CLI options: https://developers.openai.com/codex/cli/reference
    - Feature request for --system-prompt: https://github.com/openai/codex/issues/11588
"""

import json

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.llm.inference import BackendType, InferenceRequest

CODEX_CLI_MODELS = [
    "gpt-4.1-nano",
    "gpt-5.4-nano",
    "gpt-4.1-mini",
    "gpt-5.4-mini",
    "o4-mini",
    "gpt-4.1",
    "o3",
    "gpt-5.4",
    "o3-pro",
    "gpt-5.4-pro",
]
CODEX_CLI_DEFAULT_MODEL = "gpt-5.4-mini"


class CodexCliBackend(CliBackend):
    """Run inference via the OpenAI Codex CLI."""

    @property
    def cli_executable(self) -> str:
        return "codex"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.CODEX_CLI

    @property
    def available_models(self) -> list[str]:
        return CODEX_CLI_MODELS

    @property
    def default_model(self) -> str | None:
        return CODEX_CLI_DEFAULT_MODEL

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
