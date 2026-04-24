"""Google Gemini CLI backend.

Invokes ``gemini --prompt --output-format json --yolo`` as a subprocess.
``--prompt`` enables headless non-interactive mode, ``--output-format json``
returns a structured JSON envelope, and ``--yolo`` auto-approves all actions.

The system prompt is passed via the ``GEMINI_SYSTEM_MD`` environment variable
pointing to a temp file, keeping it separate from the user prompt in stdin.

Gemini has no native JSON schema enforcement; the schema is rendered
into the system prompt upstream (via ``_output_envelope.j2``), so
nothing is appended here.

Thinking control: the Gemini CLI has no per-invocation flag or environment
variable for reasoning (upstream issue
https://github.com/google-gemini/gemini-cli/issues/25122). We emulate
``thinking=False`` by writing a **project-scoped**
``<workspace_dir>/.gemini/settings.json`` that registers a custom model
alias with ``thinkingBudget: 0`` and ``includeThoughts: false``, then
passing ``--model <alias>``. The settings file is only picked up when
the CLI is run from that cwd, so the user's global Gemini CLI config
is not touched.

Envelope shape (verified 2026-04-16 via ``gemini -p "..." -o json --yolo``)::

    {
        "session_id": "...",
        "response": "<assistant text>",
        "stats": {
            "models": {
                "<model-name>": {
                    "tokens": {
                        "input": <int>, "candidates": <int>,
                        "cached": <int>, "thoughts": <int>, ...
                    },
                    "roles": {"main": {...}, "utility_router": {...}}
                },
                ...
            }
        }
    }

The Gemini CLI may dispatch to several models in one turn (a cheap
"utility_router" plus a "main" model). We report the entry carrying
``roles.main`` when present, so the usage we surface matches the model
that actually produced the response.

References:
    - Headless mode: https://geminicli.com/docs/cli/headless/
    - Headless docs: https://google-gemini.github.io/gemini-cli/docs/cli/headless.html
"""

import json
from pathlib import Path

from vibelens.config.settings import InferenceConfig
from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.llm.inference import BackendType, InferenceRequest, InferenceResult
from vibelens.models.trajectories.metrics import Metrics

# Project-scoped alias name we register in <cwd>/.gemini/settings.json to
# pin ``thinkingBudget: 0`` on the user's requested model.
_NOTHINK_ALIAS = "vibelens-nothink"


def _select_main_model(models: dict) -> tuple[str, dict]:
    """Pick the ``roles.main`` model entry, falling back to first key.

    Gemini CLI may log several models per turn (e.g. a utility router
    plus the main answering model). The one carrying ``roles.main``
    is the one whose output reached the user.

    Args:
        models: ``stats.models`` dict from the Gemini CLI envelope.

    Returns:
        Tuple of (model name, model entry dict).
    """
    for name, entry in models.items():
        if isinstance(entry, dict) and "main" in entry.get("roles", {}):
            return name, entry
    first_name = next(iter(models))
    first_entry = models[first_name]
    if not isinstance(first_entry, dict):
        first_entry = {}
    return first_name, first_entry


class GeminiCliBackend(CliBackend):
    """Run inference via the Gemini CLI."""

    def __init__(self, config: InferenceConfig):
        """Initialize Gemini CLI backend.

        Args:
            config: Inference configuration.
        """
        super().__init__(config=config)
        self._system_prompt_file: Path | None = None

    @property
    def cli_executable(self) -> str:
        return "gemini"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.GEMINI

    @property
    def supports_native_json(self) -> bool:
        return True

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build gemini CLI command.

        Writes the system prompt to a temp file for ``GEMINI_SYSTEM_MD``
        so the system and user prompts remain cleanly separated. When
        ``thinking=False`` and a workspace_dir is available, also writes
        a project-scoped ``.gemini/settings.json`` that registers a
        no-thinking alias and swaps ``--model`` to that alias.

        Args:
            request: Inference request for model and prompt settings.

        Returns:
            Command as a list of strings.
        """
        self._system_prompt_file = self._create_tempfile(
            request.system, suffix=".md", prefix="vibelens_system_"
        )
        # --prompt requires a string arg in current Gemini CLI; pass empty
        # so the real prompt flows in on stdin (gemini appends stdin to --prompt).
        cmd = [
            self._cli_path or self.cli_executable,
            "--prompt",
            "",
            "--output-format",
            "json",
            "--yolo",
        ]
        model_arg = self._resolve_model_arg(request)
        if model_arg:
            cmd.extend(["--model", model_arg])
        return cmd

    def _resolve_model_arg(self, request: InferenceRequest) -> str | None:
        """Return the ``--model`` value — a no-thinking alias when requested.

        When ``thinking=False``, writes ``<workspace_dir>/.gemini/settings.json``
        that extends the user's model with ``thinkingBudget: 0`` and returns
        the alias name. Falls back to the raw model id if no workspace_dir
        is available (cannot scope the override).
        """
        if not self._model:
            return None
        if self._config.thinking or request.workspace_dir is None:
            return self._model
        self._write_nothink_settings(request.workspace_dir, self._model)
        return _NOTHINK_ALIAS

    def _write_nothink_settings(self, workspace_dir: Path, base_model: str) -> None:
        """Write a scoped settings.json that disables reasoning via alias."""
        settings_path = workspace_dir / ".gemini" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if settings_path.exists():
            try:
                existing = json.loads(settings_path.read_text()) or {}
            except (OSError, json.JSONDecodeError):
                existing = {}
        alias_config = {
            "extends": base_model,
            "modelConfig": {
                "generateContentConfig": {
                    "thinkingConfig": {"thinkingBudget": 0, "includeThoughts": False},
                },
            },
        }
        aliases = existing.setdefault("modelConfigs", {}).setdefault("customAliases", {})
        aliases[_NOTHINK_ALIAS] = alias_config
        settings_path.write_text(json.dumps(existing, indent=2))

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
        """Return only the user prompt (stdin), system is in ``GEMINI_SYSTEM_MD``.

        Schema instructions live in the system prompt via the
        ``_output_envelope.j2`` partial — we do not re-append them here.

        Args:
            request: Inference request with user prompt.

        Returns:
            User prompt text.
        """
        thinking_prefix = self._thinking_prompt_prefix()
        return f"{thinking_prefix}{request.user}" if thinking_prefix else request.user

    def _parse_output(self, output: str, duration_ms: int) -> InferenceResult:
        """Parse the Gemini CLI JSON envelope."""
        return self._parse_single_json(output, duration_ms, self._extract)

    def _extract(self, data: dict) -> tuple[str, Metrics | None, str]:
        """Pull text, usage, and model name from Gemini's ``stats.models`` map."""
        text = str(data.get("response", ""))
        model = self.model
        metrics: Metrics | None = None

        models = data.get("stats", {}).get("models")
        if isinstance(models, dict) and models:
            name, entry = _select_main_model(models)
            model = name
            tokens = entry.get("tokens", {}) if isinstance(entry, dict) else {}
            reasoning_tokens = tokens.get("thoughts", 0)
            metrics = Metrics(
                prompt_tokens=tokens.get("prompt", tokens.get("input", 0)),
                completion_tokens=tokens.get("candidates", 0),
                cached_tokens=tokens.get("cached", 0),
                extra={"reasoning_tokens": reasoning_tokens} if reasoning_tokens else None,
            )
        return text, metrics, model
