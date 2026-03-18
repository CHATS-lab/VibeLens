"""Abstract base class for format-specific session parsers.

All parsers produce ATIF Trajectory objects. The main abstract method
is ``parse(content, source_path)`` which converts raw file content into
Trajectory objects. ``parse_file`` is a convenience wrapper that reads
the file and delegates to ``parse``.
"""

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from vibelens.models.enums import StepSource
from vibelens.models.trajectories import (
    Agent,
    FinalMetrics,
    Step,
    Trajectory,
    TrajectoryRef,
)
from vibelens.models.trajectories.trajectory import DEFAULT_ATIF_VERSION

if TYPE_CHECKING:
    from vibelens.ingest.diagnostics import DiagnosticsCollector

logger = logging.getLogger(__name__)

# Keeps session-list previews short enough for UI display while preserving
# enough context for the user to recognise the conversation at a glance.
MAX_FIRST_MESSAGE_LENGTH = 200

# Convention for marking error content in ObservationResult.
# Since ATIF ObservationResult has no is_error field, errors are signalled
# by prefixing the content string with this marker.
ERROR_PREFIX = "[ERROR] "


def is_error_content(content: str | list | None) -> bool:
    """Check whether an observation result's content indicates an error.

    Args:
        content: ObservationResult content string.

    Returns:
        True if the content starts with the error prefix.
    """
    if not content or not isinstance(content, str):
        return False
    return content.startswith(ERROR_PREFIX)


def mark_error_content(content: str | None) -> str:
    """Prefix content with the error marker if not already present.

    Args:
        content: Raw error output text.

    Returns:
        Content with ERROR_PREFIX prepended.
    """
    text = content or ""
    if text.startswith(ERROR_PREFIX):
        return text
    return f"{ERROR_PREFIX}{text}"


def _is_meaningful_prompt(text: str) -> bool:
    """Return True if the text is a real user prompt, not a slash command or system message."""
    stripped = text.strip()
    if not stripped:
        return False
    is_single_line = "\n" not in stripped
    # Single slash commands like "/permissions", "/compact"
    if stripped.startswith("/") and is_single_line and len(stripped.split()) <= 3:
        return False
    # System-generated interrupt/status messages wrapped in square brackets
    # e.g. "[Request interrupted by user for tool use]"
    return not (stripped.startswith("[") and stripped.endswith("]") and is_single_line)


class BaseParser(ABC):
    """Abstract base for format-specific session parsers.

    Every concrete parser must implement ``parse`` which converts raw
    file content into ATIF ``Trajectory`` objects.
    ``parse_file`` is a non-abstract convenience that reads a file
    and delegates to ``parse``.
    ``assemble_trajectory`` auto-computes derived fields
    (first_message, final_metrics) from steps.
    """

    @abstractmethod
    def parse(self, content: str, source_path: str | None = None) -> list[Trajectory]:
        """Parse raw file content into Trajectory objects.

        This is the main parsing entry point. Each parser implements
        format-specific logic to convert raw text into ATIF models.

        Args:
            content: Raw file content string.
            source_path: Optional original file path for resolving
                relative resources (e.g. sub-agent files).

        Returns:
            List of Trajectory objects (one per session in the content).
        """

    def parse_file(self, file_path: Path) -> list[Trajectory]:
        """Read a file and parse it into Trajectory objects.

        Convenience wrapper that reads file content and delegates
        to ``parse`` with source_path set.

        Args:
            file_path: Path to the data file.

        Returns:
            List of Trajectory objects.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Cannot read file: %s", file_path)
            return []
        return self.parse(content, source_path=str(file_path))

    @staticmethod
    def truncate_first_message(text: str) -> str:
        """Truncate text to MAX_FIRST_MESSAGE_LENGTH with ellipsis if needed.

        Args:
            text: Raw message text.

        Returns:
            Truncated string with trailing "..." when cut.
        """
        if len(text) <= MAX_FIRST_MESSAGE_LENGTH:
            return text
        return text[:MAX_FIRST_MESSAGE_LENGTH] + "..."

    def find_first_user_text(self, steps: list[Step]) -> str | None:
        """Extract truncated text of the first meaningful user step.

        Skips copied context (from ``claude --resume``) and slash commands
        (e.g. ``/permissions``, ``/compact``) that are not meaningful
        conversation starters.

        Args:
            steps: Ordered list of parsed Step objects.

        Returns:
            Truncated first user message, or None if not found.
        """
        for step in steps:
            if step.source != StepSource.USER:
                continue
            if step.is_copied_context:
                continue
            if not isinstance(step.message, str):
                continue
            if _is_meaningful_prompt(step.message):
                return self.truncate_first_message(step.message)
        return None

    @staticmethod
    def build_agent(name: str, version: str | None = None, model: str | None = None) -> Agent:
        """Create an ATIF Agent model.

        Args:
            name: Agent system name (e.g. 'claude-code', 'codex').
            version: Agent system version.
            model: Default LLM model name.

        Returns:
            Agent instance.
        """
        return Agent(name=name, version=version, model_name=model)

    def assemble_trajectory(
        self,
        session_id: str,
        agent: Agent,
        steps: list[Step],
        project_path: str | None = None,
        parent_trajectory_ref: TrajectoryRef | None = None,
        parent_ref: TrajectoryRef | None = None,
        extra: dict | None = None,
    ) -> Trajectory:
        """Assemble a Trajectory from parts with auto-computed derived fields.

        Computes from steps:
        - first_message: truncated first meaningful user message
        - final_metrics: token totals, tool_call_count, duration, cache metrics

        Args:
            session_id: Unique session identifier.
            agent: Agent configuration.
            steps: Complete step list.
            project_path: Inferred working directory path.
            parent_trajectory_ref: Reference to the parent/continued-from trajectory.
            parent_ref: Optional reference to parent session for sub-agents.
            extra: Optional metadata dict for format-specific fields.

        Returns:
            Populated Trajectory instance.
        """
        # Derive session start timestamp from the earliest step
        timestamp = steps[0].timestamp if steps and steps[0].timestamp else None

        return Trajectory(
            schema_version=DEFAULT_ATIF_VERSION,
            session_id=session_id,
            project_path=project_path,
            first_message=self.find_first_user_text(steps),
            agent=agent,
            steps=steps,
            final_metrics=_compute_final_metrics(steps),
            parent_trajectory_ref=parent_trajectory_ref,
            parent_session_ref=parent_ref,
            extra=extra,
            timestamp=timestamp,
        )

    @staticmethod
    def iter_jsonl_safe(
        file_path: Path, diagnostics: "DiagnosticsCollector | None" = None
    ) -> Iterator[dict]:
        """Yield parsed JSON dicts from a JSONL file, catching errors.

        Args:
            file_path: Path to the JSONL file.
            diagnostics: Optional collector for tracking skipped lines.

        Yields:
            Parsed JSON dict per non-empty line.
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if diagnostics:
                        diagnostics.total_lines += 1
                    try:
                        parsed = json.loads(stripped)
                        if diagnostics:
                            diagnostics.parsed_lines += 1
                        yield parsed
                    except json.JSONDecodeError:
                        if diagnostics:
                            diagnostics.record_skip("invalid JSON")
                        continue
        except OSError:
            logger.warning("Cannot read file: %s", file_path)


def _compute_final_metrics(steps: list[Step]) -> FinalMetrics:
    """Compute aggregate FinalMetrics from step-level metrics.

    Args:
        steps: All steps in the trajectory.

    Returns:
        FinalMetrics with token totals, duration, tool counts, and cache stats.
    """
    total_prompt = 0
    total_completion = 0
    total_cached = 0
    total_cost: float | None = None
    total_cache_write = 0
    total_cache_read = 0
    tool_call_count = 0

    for step in steps:
        tool_call_count += len(step.tool_calls)
        if step.metrics:
            total_prompt += step.metrics.prompt_tokens
            total_completion += step.metrics.completion_tokens
            total_cached += step.metrics.cached_tokens
            total_cache_write += step.metrics.cache_creation_tokens
            total_cache_read += step.metrics.cached_tokens
            if step.metrics.cost_usd is not None:
                total_cost = (total_cost or 0.0) + step.metrics.cost_usd

    # Compute wall-clock duration from step timestamps
    timestamps = [s.timestamp for s in steps if s.timestamp]
    duration = 0
    if len(timestamps) >= 2:
        duration = int((max(timestamps) - min(timestamps)).total_seconds())

    return FinalMetrics(
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        total_cached_tokens=total_cached,
        total_cost_usd=total_cost,
        total_steps=len(steps),
        tool_call_count=tool_call_count,
        duration=duration,
        total_cache_write=total_cache_write,
        total_cache_read=total_cache_read,
    )
