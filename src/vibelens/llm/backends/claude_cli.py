"""Claude Code CLI backend.

Invokes ``claude -p`` with ``--system-prompt`` to properly separate system
and user prompts. The ``--output-format json`` flag wraps the response in a
JSON envelope with ``result``, ``usage``, ``modelUsage``, and
``total_cost_usd`` fields.

Envelope shape (verified 2026-04-16 via ``claude -p - --output-format json``)::

    {
        "type": "result",
        "result": "<assistant text>",
        "model": "<optional>",
        "usage": {
            "input_tokens": <int>,
            "output_tokens": <int>,
            "cache_creation_input_tokens": <int>,
            "cache_read_input_tokens": <int>,
            ...
        },
        "modelUsage": {"<model-name>": {...}},
        "total_cost_usd": <float>
    }

Thinking control:
  - ``thinking=False``: set env ``CLAUDE_CODE_DISABLE_THINKING=1`` which fully
    suppresses the hidden reasoning pass on recent models (haiku-4-5,
    opus-4-6, opus-4-7). Verified empirically via session-log inspection.
  - ``thinking=True``: pass ``--effort high`` to raise the effort budget
    above the implicit default.

Safety flags prevent agentic behavior during scripted inference:
  --tools "": disables all tool use for pure text inference.

References:
    - CLI reference: https://code.claude.com/docs/en/cli-reference
    - Env vars: https://code.claude.com/docs/en/env-vars
    - Headless mode: https://code.claude.com/docs/en/headless
"""

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.llm.usage import metrics_from_anthropic_usage
from vibelens.models.llm.inference import BackendType, InferenceRequest, InferenceResult
from vibelens.models.trajectories.metrics import Metrics


class ClaudeCliBackend(CliBackend):
    """Run inference via the Claude Code CLI."""

    @property
    def cli_executable(self) -> str:
        return "claude"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.CLAUDE_CODE

    @property
    def supports_native_json(self) -> bool:
        return True

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build claude CLI command.

        Passes the system prompt via ``--system-prompt`` for clean
        system/user separation. Stdin carries only the user prompt.

        ``-p`` is the ``--print`` flag (no argument). Do NOT pass ``-``
        as a positional prompt: Claude concatenates positional + stdin,
        so ``-p -`` prepends a literal ``"-\\n"`` to the prompt the model
        sees.

        Args:
            request: Inference request for model and prompt settings.

        Returns:
            Command as a list of strings.
        """
        cmd = [
            self._cli_path or self.cli_executable,
            "-p",
            "--output-format",
            "json",
            "--system-prompt",
            request.system,
            "--tools",
            "",
        ]
        if self._model:
            cmd.extend(["--model", self._model])
        return cmd

    def _thinking_args(self) -> list[str]:
        """Claude ``--effort high`` elevates the thinking budget when on.

        When ``thinking=False``, we do NOT pass ``--effort low`` — we set
        ``CLAUDE_CODE_DISABLE_THINKING=1`` in the subprocess env instead
        (see ``_build_env``), which fully suppresses the hidden reasoning
        pass. The four documented effort levels (low/medium/high/max) all
        still run some thinking; only the env var truly disables it.
        """
        if self._config.thinking:
            return ["--effort", "high"]
        return []

    def _build_env(self) -> dict[str, str]:
        """Add ``CLAUDE_CODE_DISABLE_THINKING=1`` when thinking is off."""
        env = super()._build_env()
        if not self._config.thinking:
            env["CLAUDE_CODE_DISABLE_THINKING"] = "1"
        return env

    def _build_prompt(self, request: InferenceRequest) -> str:
        """Return only the user prompt (with optional thinking prefix).

        The system prompt is passed via ``--system-prompt`` in
        ``_build_command``, so stdin carries only the user content.

        Args:
            request: Inference request with system and user prompts.

        Returns:
            User prompt text, optionally prefixed with a thinking directive.
        """
        thinking_prefix = self._thinking_prompt_prefix()
        return f"{thinking_prefix}{request.user}" if thinking_prefix else request.user

    def _parse_output(self, output: str, duration_ms: int) -> InferenceResult:
        """Parse the Claude Code JSON envelope."""
        return self._parse_single_json(output, duration_ms, self._extract)

    def _extract(self, data: dict) -> tuple[str, Metrics | None, str]:
        """Pull Claude Code's text, usage, model, and cost from the envelope."""
        text = str(data.get("result", ""))
        usage_data = data.get("usage")
        metrics = metrics_from_anthropic_usage(usage_data) if isinstance(usage_data, dict) else None
        cost_usd = data.get("total_cost_usd")
        if cost_usd is not None:
            if metrics is None:
                metrics = Metrics()
            metrics.cost_usd = cost_usd
        model = data.get("model") or self._model_from_usage(data)
        return text, metrics, model or self.model

    def _model_from_usage(self, data: dict) -> str | None:
        """Derive model name from ``modelUsage`` keys (e.g. ``claude-opus-4-6[plan]``)."""
        model_usage = data.get("modelUsage")
        if not isinstance(model_usage, dict) or not model_usage:
            return None
        first_key = next(iter(model_usage))
        return first_key.split("[")[0]
