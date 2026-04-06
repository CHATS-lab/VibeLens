"""Google Gemini CLI backend.

Invokes ``gemini --prompt --output-format json --yolo`` as a subprocess.
``--prompt`` enables headless non-interactive mode, ``--output-format json``
returns a structured JSON envelope, and ``--yolo`` auto-approves all actions.

The system prompt is passed via the ``GEMINI_SYSTEM_MD`` environment variable
pointing to a temp file, keeping it separate from the user prompt in stdin.

Gemini has no native JSON schema enforcement, so schema instructions are
always included in the user prompt regardless of the JSON output envelope.
"""

from pathlib import Path

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.llm.inference import BackendType, InferenceRequest

GEMINI_CLI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3.1-pro",
]
GEMINI_CLI_DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiCliBackend(CliBackend):
    """Run inference via the Gemini CLI."""

    def __init__(self, model: str | None = None, timeout: int = 120):
        """Initialize Gemini CLI backend.

        Args:
            model: Optional model override passed to the CLI.
            timeout: Request timeout in seconds.
        """
        super().__init__(model=model, timeout=timeout)
        self._system_prompt_file: Path | None = None

    @property
    def cli_executable(self) -> str:
        return "gemini"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.GEMINI_CLI

    @property
    def available_models(self) -> list[str]:
        return GEMINI_CLI_MODELS

    @property
    def default_model(self) -> str | None:
        return GEMINI_CLI_DEFAULT_MODEL

    @property
    def supports_native_json(self) -> bool:
        return True

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build gemini CLI command.

        Writes the system prompt to a temp file for ``GEMINI_SYSTEM_MD``
        so the system and user prompts remain cleanly separated.

        Args:
            request: Inference request for model and prompt settings.

        Returns:
            Command as a list of strings.
        """
        self._system_prompt_file = self._create_tempfile(
            request.system, suffix=".md", prefix="vibelens_system_"
        )
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

    def _build_env(self) -> dict[str, str]:
        """Build env with ``GEMINI_SYSTEM_MD`` pointing to the system prompt file.

        Returns:
            Environment dict with system prompt override.
        """
        env = super()._build_env()
        if self._system_prompt_file:
            env["GEMINI_SYSTEM_MD"] = str(self._system_prompt_file)
        return env

    def _build_prompt(self, request: InferenceRequest) -> str:
        """Return only the user prompt, with optional schema augmentation.

        The system prompt is passed via ``GEMINI_SYSTEM_MD`` env var,
        so stdin carries only the user content. Gemini has no native
        schema enforcement, so schema instructions are always appended.

        Args:
            request: Inference request with user prompt and optional schema.

        Returns:
            User prompt text with optional schema instruction.
        """
        prompt = request.user
        if request.json_schema:
            prompt = self._augment_prompt_with_schema(prompt, request.json_schema)
        return prompt
