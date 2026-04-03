"""Google Gemini CLI backend.

Invokes ``gemini --prompt --output-format json --yolo`` as a subprocess.
``--prompt`` enables headless non-interactive mode, ``--output-format json``
returns a structured JSON envelope, and ``--yolo`` auto-approves all actions.

Gemini has no native JSON schema enforcement, so schema instructions are
always included in the prompt regardless of the JSON output envelope.
"""

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.inference import BackendType, InferenceRequest


class GeminiCliBackend(CliBackend):
    """Run inference via the Gemini CLI."""

    @property
    def cli_executable(self) -> str:
        return "gemini"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.GEMINI_CLI

    @property
    def supports_native_json(self) -> bool:
        return True

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build gemini CLI command.

        Args:
            request: Inference request for model settings.

        Returns:
            Command as a list of strings.
        """
        cmd = [
            self._cli_path or self.cli_executable,
            "--prompt",
            "--output-format",
            "json",
            "--yolo",
        ]
        if self._model:
            cmd.extend(["--model", self._model])
        return cmd

    def _build_prompt(self, request: InferenceRequest) -> str:
        """Combine system and user prompts, always augmenting with schema.

        Gemini returns a JSON envelope via ``--output-format json`` but has
        no native schema enforcement. Schema instructions must always be
        included in the prompt to constrain the model's output format.

        Args:
            request: Inference request with system and user prompts.

        Returns:
            Combined prompt text with optional schema instruction.
        """
        prompt = f"{request.system}\n\n{request.user}"
        if request.json_schema:
            prompt = self._augment_prompt_with_schema(prompt, request.json_schema)
        return prompt
