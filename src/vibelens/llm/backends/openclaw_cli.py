"""OpenClaw CLI backend.

Invokes ``openclaw agent --local --agent main --message <user> --json`` as a
subprocess. Uses the embedded-local runtime (no Gateway) and emits a JSON
envelope with ``payloads[].text`` plus per-call usage under ``meta``.

System prompt: OpenClaw has no CLI flag for system prompts. It uses a
bootstrap file system (``SOUL.md``, ``AGENTS.md``, etc.) loaded from the
workspace. System + user prompts are combined and passed via ``--message``.

Thinking: OpenClaw has a native ``--thinking <off|minimal|low|medium|high|xhigh>``
flag on the ``agent`` subcommand.

References:
    - CLI: ``openclaw agent --help``
    - System prompt: https://docs.openclaw.ai/concepts/system-prompt
"""

from vibelens.llm.backends.cli_base import CliBackend
from vibelens.models.llm.inference import BackendType, InferenceRequest, InferenceResult
from vibelens.models.trajectories.metrics import Metrics

_THINKING_LEVEL = "medium"
_DEFAULT_AGENT_ID = "main"


class OpenClawCliBackend(CliBackend):
    """Run inference via the OpenClaw CLI."""

    @property
    def cli_executable(self) -> str:
        return "openclaw"

    @property
    def backend_id(self) -> BackendType:
        return BackendType.OPENCLAW

    @property
    def supports_freeform_model(self) -> bool:
        return True

    @property
    def supports_native_json(self) -> bool:
        return True

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build openclaw agent CLI command.

        Passes the combined system+user prompt via ``--message``. Stdin is
        unused by the new ``agent`` subcommand.
        """
        message = self._build_prompt(request)
        return [
            self._cli_path or self.cli_executable,
            "--log-level",
            "silent",
            "agent",
            "--local",
            "--agent",
            _DEFAULT_AGENT_ID,
            "--json",
            "--message",
            message,
        ]

    def _select_output(self, stdout: bytes, stderr: bytes) -> str:
        """OpenClaw writes its ``--json`` envelope to stderr, not stdout."""
        return stderr.decode("utf-8", errors="replace").strip()

    def _build_prompt(self, request: InferenceRequest) -> str:
        """Combine system + user into a single message.

        Schema instructions live in the system prompt via
        ``_output_envelope.j2`` — we do not re-append them here.
        """
        return f"{request.system}\n\n{request.user}"

    def _thinking_args(self) -> list[str]:
        """Native OpenClaw --thinking flag on the agent subcommand."""
        if self._config.thinking:
            return ["--thinking", _THINKING_LEVEL]
        return ["--thinking", "off"]

    def _parse_output(self, output: str, duration_ms: int) -> InferenceResult:
        """Parse OpenClaw's JSON envelope from ``openclaw agent --json``."""
        return self._parse_single_json(output, duration_ms, self._extract)

    def _extract(self, data: dict) -> tuple[str, Metrics | None, str]:
        """Pull text, usage, and model name from OpenClaw's envelope."""
        payloads = data.get("payloads") or []
        text_parts: list[str] = []
        for payload in payloads:
            if isinstance(payload, dict):
                block_text = payload.get("text")
                if isinstance(block_text, str):
                    text_parts.append(block_text)
        text = "\n".join(text_parts)

        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        agent_meta = meta.get("agentMeta") if isinstance(meta.get("agentMeta"), dict) else {}
        usage = agent_meta.get("lastCallUsage") or {}
        metrics: Metrics | None = None
        if usage:
            metrics = Metrics(
                prompt_tokens=usage.get("input", 0),
                completion_tokens=usage.get("output", 0),
                cached_tokens=usage.get("cacheRead", 0),
                cache_creation_tokens=usage.get("cacheWrite", 0),
            )
        model = agent_meta.get("model") or self.model
        return text, metrics, model
