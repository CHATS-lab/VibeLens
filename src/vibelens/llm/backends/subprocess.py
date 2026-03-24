"""Subprocess-based inference backends for CLI tools (claude, codex).

Zero-cost analysis for subscription users — invokes the CLI as a subprocess
and captures stdout. Prompts are passed via stdin to avoid argument length limits.
"""

import asyncio
import json
import shutil
import time

from vibelens.llm.backend import InferenceBackend, InferenceError, InferenceTimeoutError
from vibelens.models.inference import InferenceRequest, InferenceResult, TokenUsage
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

SIGTERM_GRACE_SECONDS = 5


class SubprocessBackend(InferenceBackend):
    """Run inference via a CLI subprocess (claude-cli or codex-cli).

    Passes the full prompt via stdin pipe. Enforces timeout with
    SIGTERM followed by SIGKILL after a grace period.
    """

    def __init__(
        self, cli_name: str, backend_type: str, model: str | None = None, timeout: int = 120
    ):
        """Initialize subprocess backend.

        Args:
            cli_name: CLI executable name (e.g. 'claude', 'codex').
            backend_type: Backend identifier string.
            model: Optional model override.
            timeout: Request timeout in seconds.
        """
        self._cli_name = cli_name
        self._backend_type = backend_type
        self._model = model
        self._timeout = timeout
        self._cli_path = shutil.which(cli_name)

    async def generate(self, request: InferenceRequest) -> InferenceResult:
        """Run inference via subprocess.

        Args:
            request: Inference request to process.

        Returns:
            InferenceResult from CLI output.

        Raises:
            InferenceError: If CLI is not available or exits with error.
            InferenceTimeoutError: If the subprocess exceeds the timeout.
        """
        if not self._cli_path:
            raise InferenceError(f"{self._cli_name} CLI not found in PATH")

        cmd = self._build_command(request)
        prompt_text = self._build_prompt(request)
        prompt_bytes = prompt_text.encode("utf-8")

        start_ms = _now_ms()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt_bytes), timeout=self._timeout
            )
        except TimeoutError as exc:
            await _kill_process(proc)
            raise InferenceTimeoutError(
                f"{self._cli_name} timed out after {self._timeout}s"
            ) from exc
        except OSError as exc:
            raise InferenceError(f"Failed to start {self._cli_name}: {exc}") from exc

        duration_ms = _now_ms() - start_ms

        if proc.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            raise InferenceError(
                f"{self._cli_name} exited with code {proc.returncode}: {stderr_text}"
            )

        output = stdout.decode("utf-8", errors="replace").strip()
        return self._parse_output(output, duration_ms)

    async def is_available(self) -> bool:
        """Check if the CLI executable exists in PATH."""
        return shutil.which(self._cli_name) is not None

    @property
    def backend_id(self) -> str:
        """Return the backend type identifier."""
        return self._backend_type

    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build the CLI command arguments.

        Args:
            request: Inference request (used for model/token settings).

        Returns:
            Command as a list of strings.
        """
        if self._backend_type == "claude-cli":
            return self._build_claude_command(request)
        return self._build_codex_command(request)

    def _build_claude_command(self, request: InferenceRequest) -> list[str]:
        """Build claude CLI command."""
        cmd = [self._cli_path or self._cli_name, "-p", "-", "--output-format", "json"]
        if self._model:
            cmd.extend(["--model", self._model])
        if request.max_tokens:
            cmd.extend(["--max-tokens", str(request.max_tokens)])
        return cmd

    def _build_codex_command(self, request: InferenceRequest) -> list[str]:
        """Build codex CLI command."""
        cmd = [self._cli_path or self._cli_name, "exec", "--json", "--sandbox", "read-only"]
        if self._model:
            cmd.extend(["--model", self._model])
        return cmd

    def _build_prompt(self, request: InferenceRequest) -> str:
        """Combine system and user prompts for stdin.

        Args:
            request: Inference request with system and user prompts.

        Returns:
            Combined prompt text.
        """
        return f"{request.system}\n\n{request.user}"

    def _parse_output(self, output: str, duration_ms: int) -> InferenceResult:
        """Parse CLI output into InferenceResult.

        Attempts JSON parsing first (for --output-format json), falls back
        to treating the entire output as plain text.

        Args:
            output: Raw stdout from the CLI process.
            duration_ms: Elapsed time in milliseconds.

        Returns:
            Parsed InferenceResult.
        """
        text = output
        usage = None
        model = self._model or self._cli_name

        try:
            data = json.loads(output)
            if isinstance(data, dict):
                text = data.get("result", data.get("content", data.get("text", output)))
                if "usage" in data:
                    usage_data = data["usage"]
                    usage = TokenUsage(
                        input_tokens=usage_data.get("input_tokens", 0),
                        output_tokens=usage_data.get("output_tokens", 0),
                    )
                if "model" in data:
                    model = data["model"]
        except (json.JSONDecodeError, TypeError):
            pass

        return InferenceResult(
            text=str(text),
            model=model,
            usage=usage,
            cost_usd=None,
            duration_ms=duration_ms,
        )


async def _kill_process(proc: asyncio.subprocess.Process) -> None:
    """Terminate a subprocess with SIGTERM, then SIGKILL after grace period."""
    try:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=SIGTERM_GRACE_SECONDS)
        except TimeoutError:
            proc.kill()
            await proc.wait()
    except ProcessLookupError:
        pass


def _now_ms() -> int:
    """Return current time in milliseconds."""
    return int(time.monotonic() * 1000)
