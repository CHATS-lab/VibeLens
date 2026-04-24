"""Base class for CLI subprocess inference backends.

Shared infrastructure for all CLI-based backends: subprocess lifecycle
(spawn -> stdin pipe -> timeout -> kill -> parse), prompt augmentation
with JSON schema instructions, and temp file management.
"""

import asyncio
import contextlib
import json
import os
import shutil
import tempfile
from abc import abstractmethod
from collections.abc import Callable, Iterator
from pathlib import Path

from vibelens.llm.backend import InferenceBackend, InferenceError, InferenceTimeoutError
from vibelens.llm.model_catalog import available_models, default_model
from vibelens.models.llm.inference import BackendType, InferenceRequest, InferenceResult
from vibelens.models.trajectories.metrics import Metrics
from vibelens.utils.log import get_logger
from vibelens.utils.timestamps import monotonic_ms

# Dedicated cwds for analysis subprocesses. Keeps CLI-derived session files
# (claude/codex/gemini/openclaw write logs relative to cwd) segregated per
# analysis module instead of sharing one directory.
_VIBELENS_HOME: Path = Path.home() / ".vibelens"
_PERSONALIZATION_ROOT: Path = _VIBELENS_HOME / "personalization"
RECOMMENDATION_CWD: Path = _PERSONALIZATION_ROOT / "recommendation"
CREATION_CWD: Path = _PERSONALIZATION_ROOT / "creation"
EVOLUTION_CWD: Path = _PERSONALIZATION_ROOT / "evolution"
FRICTION_CWD: Path = _VIBELENS_HOME / "friction"

# Signature for per-backend extractors passed to ``_parse_single_json``.
# Returns (text, metrics, model) — metrics may be None when the backend
# reports no usage; cost lives inside ``Metrics.cost_usd``.
JsonExtractor = Callable[[dict], tuple[str, "Metrics | None", str]]

logger = get_logger(__name__)

# Seconds to wait after SIGTERM before escalating to SIGKILL
SIGTERM_GRACE_SECONDS = 5
# Appended to user prompts to enforce JSON output when the CLI has no native schema flag
SCHEMA_INSTRUCTION_TEMPLATE = (
    "\n\n---\nYou MUST respond with a single JSON object conforming to the following schema. "
    "Do NOT wrap the JSON in markdown code fences or add any text before/after it.\n\n"
    "```json\n{schema}\n```"
)


class CliBackend(InferenceBackend):
    """Abstract base for CLI subprocess backends.

    Subclasses provide CLI-specific command construction and metadata.
    This base handles the full subprocess lifecycle, optional JSON schema
    augmentation, and output parsing.
    """

    def __init__(self, model: str | None = None, timeout: int = 120):
        """Initialize CLI backend.

        Args:
            model: Optional model override passed to the CLI.
            timeout: Request timeout in seconds.
        """
        self._model = model
        self._timeout = timeout
        self._cli_path = shutil.which(self.cli_executable)
        self._tempfiles: list[Path] = []

    @property
    @abstractmethod
    def cli_executable(self) -> str:
        """Binary name to invoke (e.g. 'claude', 'codex')."""

    @property
    @abstractmethod
    def backend_id(self) -> BackendType:
        """Unique BackendType enum value for this backend."""

    @property
    def model(self) -> str:
        """Return configured model name, falling back to CLI executable name."""
        return self._model or self.cli_executable

    @property
    def available_models(self) -> list[str]:
        """Models this CLI supports, ordered cheapest first.

        Resolved through the central ``model_catalog`` keyed by
        ``self.backend_id``.
        """
        return available_models(self.backend_id)

    @property
    def default_model(self) -> str | None:
        """Cheapest recommended model for this CLI, or None if no selection."""
        return default_model(self.backend_id)

    @property
    def supports_freeform_model(self) -> bool:
        """Whether the CLI accepts arbitrary model names beyond the preset list."""
        return False

    @property
    def supports_native_json(self) -> bool:
        """Whether the CLI natively supports JSON output mode."""
        return False

    @abstractmethod
    def _build_command(self, request: InferenceRequest) -> list[str]:
        """Build the CLI command arguments.

        Args:
            request: Inference request (used for model/token settings).

        Returns:
            Command as a list of strings.
        """

    async def generate(self, request: InferenceRequest) -> InferenceResult:
        """Run inference via subprocess.

        Spawns the CLI process, pipes the prompt via stdin, enforces
        timeout with SIGTERM/SIGKILL, and parses stdout.

        Args:
            request: Inference request to process.

        Returns:
            InferenceResult from CLI output.

        Raises:
            InferenceError: If CLI is not available or exits with error.
            InferenceTimeoutError: If the subprocess exceeds the timeout.
        """
        if not self._cli_path:
            raise InferenceError(f"{self.cli_executable} CLI not found in PATH")

        # Isolate temp files per generate() call so concurrent coroutines
        # don't interfere with each other's cleanup.
        saved_tempfiles = self._tempfiles
        self._tempfiles = []
        try:
            cmd = self._build_command(request)
            prompt_text = self._build_prompt(request)
            prompt_bytes = prompt_text.encode("utf-8")
            env = self._build_env()
            if request.analysis_cwd is None:
                raise InferenceError("InferenceRequest.analysis_cwd is required for CLI backends")
            cwd = request.analysis_cwd
            cwd.mkdir(parents=True, exist_ok=True)

            start_ms = monotonic_ms()
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    cwd=str(cwd),
                )
                timeout = request.timeout or self._timeout
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=prompt_bytes), timeout=timeout
                )
            except TimeoutError as exc:
                await _kill_process(proc)
                raise InferenceTimeoutError(
                    f"{self.cli_executable} timed out after {timeout}s"
                ) from exc
            except OSError as exc:
                raise InferenceError(f"Failed to start {self.cli_executable}: {exc}") from exc

            duration_ms = monotonic_ms() - start_ms

            if proc.returncode != 0:
                stderr_text = stderr.decode("utf-8", errors="replace").strip()
                raise InferenceError(
                    f"{self.cli_executable} exited with code {proc.returncode}: {stderr_text}"
                )

            output = stdout.decode("utf-8", errors="replace").strip()
            result = self._parse_output(output, duration_ms)
            logger.info(
                "CLI inference complete: backend=%s duration_ms=%d output_len=%d",
                self.backend_id,
                duration_ms,
                len(output),
            )
            return result
        finally:
            _cleanup_tempfiles(self._tempfiles)
            self._tempfiles = saved_tempfiles

    async def is_available(self) -> bool:
        """Check if the CLI executable exists in PATH."""
        return shutil.which(self.cli_executable) is not None

    def _build_env(self) -> dict[str, str]:
        """Build a clean environment for the subprocess.

        Strips variables that cause nesting-detection failures (e.g.
        CLAUDECODE prevents Claude Code from launching inside another
        Claude Code session).
        """
        env = os.environ.copy()
        for var in ("CLAUDECODE",):
            env.pop(var, None)
        return env

    def _build_prompt(self, request: InferenceRequest) -> str:
        """Combine system and user prompts, optionally augmenting with schema.

        Args:
            request: Inference request with system and user prompts.

        Returns:
            Combined prompt text.
        """
        prompt = f"{request.system}\n\n{request.user}"
        if request.json_schema and not self.supports_native_json:
            prompt = self._augment_prompt_with_schema(prompt, request.json_schema)
        return prompt

    def _augment_prompt_with_schema(self, prompt: str, json_schema: dict) -> str:
        """Append JSON schema instruction to the prompt.

        Used when the CLI lacks native JSON output support, so the LLM
        must be instructed via the prompt itself.

        Args:
            prompt: Original combined prompt text.
            json_schema: JSON schema dict for structured output.

        Returns:
            Prompt with appended schema instruction.
        """
        schema_str = json.dumps(json_schema, indent=2)
        return prompt + SCHEMA_INSTRUCTION_TEMPLATE.format(schema=schema_str)

    def _create_tempfile(
        self, content: str, suffix: str = ".txt", prefix: str = "vibelens_"
    ) -> Path:
        """Write content to a temp file and register it for cleanup.

        Args:
            content: Text content to write.
            suffix: File extension for the temp file.
            prefix: Filename prefix for the temp file.

        Returns:
            Path to the created temp file.

        Raises:
            InferenceError: If the temp file cannot be written.
        """
        fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as exc:
            raise InferenceError(f"Failed to write temp file at {path}") from exc
        temp_path = Path(path)
        self._tempfiles.append(temp_path)
        return temp_path

    @abstractmethod
    def _parse_output(self, output: str, duration_ms: int) -> InferenceResult:
        """Parse CLI stdout into an InferenceResult.

        Each backend knows its own envelope shape; implementations should
        delegate to one of the helpers below (``_parse_plain_text``,
        ``_parse_single_json``, ``_iter_ndjson_events``).

        Args:
            output: Raw stdout from the CLI process.
            duration_ms: Elapsed time in milliseconds.

        Returns:
            Parsed InferenceResult.

        Raises:
            InferenceError: If the output cannot be parsed per the backend's envelope.
        """

    def _parse_plain_text(self, output: str, duration_ms: int) -> InferenceResult:
        """Wrap raw stdout as an InferenceResult with no usage or cost.

        Used for CLIs whose entire stdout is the assistant's reply
        (aider, openclaw, kimi).

        Args:
            output: Raw stdout text.
            duration_ms: Elapsed time in milliseconds.

        Returns:
            InferenceResult with text=output, model=self.model, and a
            Metrics that records only the wall-clock duration.
        """
        return InferenceResult(
            text=output, model=self.model, metrics=Metrics(duration_ms=duration_ms)
        )

    def _parse_single_json(
        self, output: str, duration_ms: int, extract: JsonExtractor
    ) -> InferenceResult:
        """Parse stdout as a single JSON object and apply ``extract``.

        Args:
            output: Raw stdout assumed to be a single JSON object.
            duration_ms: Elapsed time in milliseconds.
            extract: Backend-specific callable that pulls (text, metrics,
                model) out of the parsed dict.

        Returns:
            InferenceResult assembled from the extractor's tuple, with
            ``duration_ms`` injected into the returned Metrics.

        Raises:
            InferenceError: If stdout is not a valid JSON object.
        """
        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            logger.error(
                "CLI %s returned non-JSON output (len=%d): %r",
                self.cli_executable,
                len(output),
                output[:200],
            )
            raise InferenceError(
                f"{self.cli_executable} returned non-JSON output: {exc.msg}"
            ) from exc
        if not isinstance(data, dict):
            raise InferenceError(
                f"{self.cli_executable} returned JSON of type "
                f"{type(data).__name__}, expected object"
            )
        text, metrics, model = extract(data)
        if metrics is None:
            metrics = Metrics()
        metrics.duration_ms = duration_ms
        return InferenceResult(text=text, model=model, metrics=metrics)

    def _metrics_from_anthropic(self, usage_data: dict) -> Metrics:
        """Build a Metrics from an Anthropic-style usage dict.

        Shared by Claude Code and Amp, which both emit the same four
        ``*_input_tokens`` / ``*_tokens`` key names.

        Args:
            usage_data: Dict with ``input_tokens``, ``output_tokens``,
                ``cache_creation_input_tokens``, ``cache_read_input_tokens``.

        Returns:
            Populated Metrics (missing keys default to 0).
        """
        return Metrics(
            prompt_tokens=usage_data.get("input_tokens", 0),
            completion_tokens=usage_data.get("output_tokens", 0),
            cached_tokens=usage_data.get("cache_read_input_tokens", 0),
            cache_creation_tokens=usage_data.get("cache_creation_input_tokens", 0),
        )

    def _iter_ndjson_events(self, output: str) -> Iterator[dict]:
        """Yield each JSON object from an NDJSON stdout stream.

        Blank lines are silently skipped. Lines that fail to parse (e.g.
        stderr-style warnings interleaved by the CLI) are logged at
        debug level and skipped so a single malformed line doesn't
        abort the whole event stream.

        Args:
            output: Raw NDJSON stdout.

        Yields:
            Each parsed JSON object that is a dict.
        """
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                logger.debug(
                    "Skipping non-JSON line in %s NDJSON stream: %r",
                    self.cli_executable,
                    stripped[:120],
                )
                continue
            if isinstance(event, dict):
                yield event


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


def _cleanup_tempfiles(paths: list[Path]) -> None:
    """Remove all temp files from the given list.

    Args:
        paths: Temp file paths to delete.
    """
    for path in paths:
        if path.exists():
            with contextlib.suppress(OSError):
                path.unlink()
