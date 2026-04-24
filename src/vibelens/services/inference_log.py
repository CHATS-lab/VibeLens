"""Structured inference logging for analysis runs.

Writer that accumulates per-call records in ``inference.json`` alongside
raw prompt ``.txt`` files. Each record captures the full ``InferenceResult``
(text, model, metrics) or an error snapshot when the call fails.
"""

import asyncio
import hashlib
from pathlib import Path

from pydantic import BaseModel, Field

from vibelens.config.settings import InferenceConfig
from vibelens.llm.backend import InferenceBackend
from vibelens.models.context import SessionContextBatch
from vibelens.models.llm.inference import InferenceRequest, InferenceResult
from vibelens.utils.json import atomic_write_json
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

INFERENCE_LOG_FILENAME = "inference.json"

# Config fields captured in inference.json for reproducibility.
_CONFIG_SNAPSHOT_FIELDS = frozenset(
    {"backend", "model", "max_output_tokens", "temperature", "timeout", "thinking"}
)


class InferenceCallContext(BaseModel):
    """Identifies one LLM call within an analysis run."""

    task_id: str = Field(description="Logical step name (e.g. 'friction_analysis').")
    system_file: str = Field(description="Filename of the system prompt .txt.")
    user_file: str = Field(description="Filename of the user prompt .txt.")


class InferenceLogWriter:
    """Accumulates per-call inference records and flushes to inference.json."""

    def __init__(self, log_dir: Path, analysis_id: str, mode: str, config: InferenceConfig) -> None:
        """Initialize the writer for one analysis run.

        Args:
            log_dir: Directory for this run's log files.
            analysis_id: Unique identifier for the analysis run.
            mode: Analysis mode (e.g. 'friction', 'creation').
            config: Inference config snapshot captured at run start.
        """
        self._log_dir = log_dir
        self._analysis_id = analysis_id
        self._mode = mode
        self._config_snapshot = config.model_dump(include=_CONFIG_SNAPSHOT_FIELDS, mode="json")
        self._calls: list[dict] = []
        self._lock = asyncio.Lock()
        self._written_hashes: dict[str, str] = {}

    def log_prompt_file(self, filename: str, content: str) -> None:
        """Write a raw prompt .txt file. Idempotent for identical content.

        Duplicate calls with the same filename and content are no-ops.
        A WARNING is logged if the content differs from a prior write;
        the first write is kept.

        Args:
            filename: File name within the log directory.
            content: Text content to write.
        """
        content_hash = hashlib.md5(content.encode()).hexdigest()
        previous_hash = self._written_hashes.get(filename)
        if previous_hash is not None:
            if previous_hash != content_hash:
                logger.warning(
                    "log_prompt_file: different content for %s; keeping first write",
                    filename,
                )
            return
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            (self._log_dir / filename).write_text(content, encoding="utf-8")
            self._written_hashes[filename] = content_hash
        except OSError as exc:
            logger.warning("Failed to write prompt file %s/%s: %s", self._log_dir, filename, exc)

    async def record_call(
        self, context: InferenceCallContext, result: InferenceResult | None, error: str | None
    ) -> None:
        """Append one call record and flush inference.json.

        Safe under asyncio concurrency via an internal lock.

        Args:
            context: Call metadata (task_id, file pointers).
            result: InferenceResult on success, None on error.
            error: Error string on failure, None on success.
        """
        async with self._lock:
            self._calls.append(_build_call_entry(len(self._calls), context, result, error))
            self._flush()

    def _flush(self) -> None:
        """Write inference.json atomically via the shared utility."""
        doc = {
            "analysis_id": self._analysis_id,
            "mode": self._mode,
            "config": self._config_snapshot,
            "calls": self._calls,
        }
        target = self._log_dir / INFERENCE_LOG_FILENAME
        try:
            atomic_write_json(target, doc, indent=2)
        except OSError as exc:
            logger.warning("Failed to flush %s: %s", target, exc)


async def run_inference(
    backend: InferenceBackend,
    request: InferenceRequest,
    writer: InferenceLogWriter,
    context: InferenceCallContext,
) -> InferenceResult:
    """Run backend.generate and record success or error in the writer.

    On failure the error is recorded and the exception re-raised.

    Args:
        backend: Configured inference backend.
        request: Inference request to process.
        writer: Log writer for this analysis run.
        context: Call metadata for logging.

    Returns:
        InferenceResult from the backend.

    Raises:
        Exception: Re-raised from backend.generate on failure.
    """
    try:
        result = await backend.generate(request)
    except Exception as exc:
        await writer.record_call(context, result=None, error=f"{type(exc).__name__}: {exc}")
        raise
    await writer.record_call(context, result=result, error=None)
    return result


def _build_call_entry(
    index: int, context: InferenceCallContext, result: InferenceResult | None, error: str | None
) -> dict:
    """Build one ``calls[]`` entry for inference.json."""
    entry: dict = {
        "index": index,
        "task_id": context.task_id,
        "system_file": context.system_file,
        "user_file": context.user_file,
    }
    if result is not None:
        entry["status"] = "success"
        entry["result"] = {
            "text": result.text,
            "model": result.model,
            "metrics": result.metrics.model_dump(exclude_none=True),
        }
    else:
        entry["status"] = "error"
        entry["error"] = error or "unknown error"
    return entry


def analysis_log_dir(mode: str) -> Path:
    """Return the base directory for per-run prompt artifacts of a mode.

    Friction lives at ``{log_root}/friction/``; the three personalization
    modes live under ``{log_root}/personalization/{mode}/``. The returned
    path has no trailing analysis_id segment — callers append that.
    Resolved at call time so tests that reconfigure settings see the
    current log root.
    """
    from vibelens.deps import get_settings

    base = get_settings().logging.dir
    if mode == "friction":
        return base / "friction"
    return base / "personalization" / mode


def log_inference_summary(
    context_set: SessionContextBatch, batches: list[SessionContextBatch], backend: InferenceBackend
) -> None:
    """Log a structured summary of an inference run.

    Args:
        context_set: SessionContextBatch with loaded/skipped session metadata.
        batches: Built session batches.
        backend: Inference backend in use.
    """
    total_tokens = sum(b.total_tokens for b in batches)
    logger.info(
        "Inference run: %d loaded, %d skipped, %d batches, %d total tokens, model=%s, backend=%s",
        len(context_set.session_ids),
        len(context_set.skipped_session_ids),
        len(batches),
        total_tokens,
        backend.model,
        backend.backend_id,
    )
    for batch in batches:
        sids = [ctx.session_id for ctx in batch.contexts]
        logger.info(
            "Batch %s: %d sessions, %d tokens, ids=%s",
            batch.batch_id,
            len(sids),
            batch.total_tokens,
            sids,
        )
