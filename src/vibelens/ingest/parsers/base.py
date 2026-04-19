"""Abstract base class for format-specific session parsers.

All parsers produce ATIF Trajectory objects. The main abstract method
is ``parse(content, source_path)`` which converts raw file content into
Trajectory objects. ``parse_file`` is a convenience wrapper that reads
the file and delegates to ``parse``.
"""

import json
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from pathlib import Path

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.models.enums import AgentType, StepSource
from vibelens.models.trajectories import (
    Agent,
    FinalMetrics,
    Step,
    Trajectory,
    TrajectoryRef,
)
from vibelens.models.trajectories.trajectory import DEFAULT_ATIF_VERSION
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Keeps session-list previews short enough for UI display while preserving
# enough context for the user to recognise the conversation at a glance.
MAX_FIRST_MESSAGE_LENGTH = 200

# Convention for marking error content in ObservationResult.
# Since ATIF ObservationResult has no is_error field, errors are signalled
# by prefixing the content string with this marker.
ERROR_PREFIX = "[ERROR] "

# ATIF source mapping shared across parsers that use standard role names.
ROLE_TO_SOURCE: dict[str, StepSource] = {"user": StepSource.USER, "assistant": StepSource.AGENT}


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


# System-XML-tag prefixes are agent-specific (observed via actual session scans):
#   claude  -> <local-command-caveat, <command-name, <command-message,
#              <local-command-stdout, <system-reminder, <user-prompt-submit-hook,
#              <task-notification, <command-args
#   codex   -> <environment_context, <turn_aborted, <skill, <subagent_notification
# Each parser module owns the list that fits its format. The union below is
# used only for agent-agnostic callers (e.g. demo mode loading ATIF files
# where the originating agent is unknown).
_ALL_KNOWN_SYSTEM_TAG_PREFIXES = (
    # claude
    "<system-reminder",
    "<command-name",
    "<command-message",
    "<command-args",
    "<user-prompt-submit-hook",
    "<local-command-caveat",
    "<local-command-stdout",
    "<task-notification",
    # codex
    "<environment_context",
    "<turn_aborted",
    "<subagent_notification",
    # generic fallbacks seen in wrapped imports
    "<environment-details",
    "<context",
    "<tool-",
    "<instructions",
)

# Skill-output marker is a claude-specific convention (the Skill tool writes
# "Base directory for this skill: ..." as the first line of its result).
# No other agent produces it, but the string is unique enough that keeping
# the check agent-agnostic costs nothing.
_SKILL_OUTPUT_PREFIX = "Base directory for this skill:"


def _is_meaningful_prompt(text: str, extra_system_prefixes: tuple[str, ...] = ()) -> bool:
    """Return True if text looks like a real user prompt rather than system chatter.

    Args:
        text: Candidate message body.
        extra_system_prefixes: Agent-specific system XML-tag prefixes to
            reject in addition to the universal set. Pass an empty tuple
            when the caller already provides a full list.
    """
    stripped = text.strip()
    if not stripped:
        return False
    prefixes = extra_system_prefixes or _ALL_KNOWN_SYSTEM_TAG_PREFIXES
    if stripped.startswith(prefixes):
        return False
    if stripped.startswith(_SKILL_OUTPUT_PREFIX):
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

    Subclasses must set ``AGENT_TYPE`` to their ``AgentType`` enum value
    (e.g. ``AgentType.CLAUDE_CODE``, ``AgentType.CODEX``).

    Parsers that read from a local data directory set ``LOCAL_DATA_DIR``
    to the default path (e.g. ``Path.home() / ".claude"``).
    Parsers for imported formats leave it as ``None`` to opt out of
    local discovery.
    """

    AGENT_TYPE: AgentType
    LOCAL_DATA_DIR: Path | None = None

    def parse_session_index(self, data_dir: Path) -> list[Trajectory] | None:
        """Build skeleton trajectories from a fast index if available.

        Parsers with an external index (history.jsonl, SQLite DB) override
        this to avoid full-file parsing during listing. Returns None to
        signal no fast index is available, triggering file-parse fallback.

        Args:
            data_dir: Agent's data directory.

        Returns:
            Skeleton trajectories, or None if no fast index exists.
        """
        return None

    def discover_session_files(self, data_dir: Path) -> list[Path]:
        """Discover session files in the given directory.

        Override in subclasses to apply agent-specific filename filters.
        Default returns an empty list.

        Args:
            data_dir: Directory to scan for session files.

        Returns:
            List of discovered session file paths.
        """
        return []

    def get_session_files(self, session_file: Path) -> list[Path]:
        """Return all files related to a session including sub-agent files.

        Default returns just the session file. Override in parsers with
        multi-file sessions (e.g., Claude Code sub-agents).

        Args:
            session_file: Path to the main session file.

        Returns:
            List of all file paths belonging to this session.
        """
        return [session_file]

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
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read file %s: %s", file_path, exc)
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
            extra = step.extra or {}
            if extra.get("is_skill_output") or extra.get("is_auto_prompt"):
                continue
            if _is_meaningful_prompt(step.message):
                return self.truncate_first_message(step.message)
        return None

    @staticmethod
    def build_diagnostics_extra(collector: DiagnosticsCollector) -> dict | None:
        """Build trajectory extra dict from diagnostics if there are issues.

        Args:
            collector: Diagnostics collector with parse quality metrics.

        Returns:
            Dict with diagnostics data, or None if no issues were recorded.
        """
        has_issues = (
            collector.skipped_lines > 0
            or collector.orphaned_tool_calls > 0
            or collector.orphaned_tool_results > 0
        )
        if not has_issues:
            return None
        return {"diagnostics": collector.to_diagnostics().model_dump()}

    def build_agent(self, version: str | None = None, model: str | None = None) -> Agent:
        """Create an ATIF Agent model using this parser's AGENT_TYPE.

        Args:
            version: Agent system version.
            model: Default LLM model name.

        Returns:
            Agent instance.
        """
        return Agent(name=self.AGENT_TYPE.value, version=version, model_name=model)

    def assemble_trajectory(
        self,
        session_id: str,
        agent: Agent,
        steps: list[Step],
        project_path: str | None = None,
        prev_trajectory_ref: TrajectoryRef | None = None,
        parent_trajectory_ref: TrajectoryRef | None = None,
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
            prev_trajectory_ref: Reference to previous session (continuation).
            parent_trajectory_ref: Reference to parent trajectory (sub-agent spawn).
            extra: Optional metadata dict for format-specific fields.

        Returns:
            Populated Trajectory instance.
        """
        timestamp = steps[0].timestamp if steps and steps[0].timestamp else None

        return Trajectory(
            schema_version=DEFAULT_ATIF_VERSION,
            session_id=session_id,
            project_path=project_path,
            timestamp=timestamp,
            first_message=self.find_first_user_text(steps),
            agent=agent,
            steps=steps,
            final_metrics=_compute_final_metrics(steps),
            prev_trajectory_ref=prev_trajectory_ref,
            parent_trajectory_ref=parent_trajectory_ref,
            extra=extra,
        )

    @staticmethod
    def iter_jsonl_safe(
        source: Path | str, diagnostics: DiagnosticsCollector | None = None
    ) -> Iterator[dict]:
        """Yield parsed JSON dicts from a JSONL file or in-memory string.

        Blank lines are skipped silently; decode errors are recorded to
        ``diagnostics`` (if provided) and skipped. A ``Path`` streams
        the file line-by-line; a ``str`` iterates over ``splitlines()``.

        Args:
            source: Path to a JSONL file, or the raw content string.
            diagnostics: Optional collector for tracking skipped lines.

        Yields:
            Parsed JSON dict per non-empty line.
        """
        if isinstance(source, Path):
            try:
                with source.open(encoding="utf-8") as f:
                    yield from _iter_parsed_jsonl(f, diagnostics)
            except OSError:
                logger.debug("Cannot read file: %s", source)
        else:
            yield from _iter_parsed_jsonl(source.splitlines(), diagnostics)


def _iter_parsed_jsonl(
    lines: Iterable[str], diagnostics: DiagnosticsCollector | None
) -> Iterator[dict]:
    """Shared loop body for BaseParser.iter_jsonl_safe.

    Kept out of the class so both the file-streaming and string-splitting
    paths can share the same blank-line / decode-error / diagnostics
    handling.
    """
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if diagnostics is not None:
            diagnostics.total_lines += 1
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            if diagnostics is not None:
                diagnostics.record_skip("invalid JSON")
            continue
        if diagnostics is not None:
            diagnostics.parsed_lines += 1
        yield parsed


def _compute_final_metrics(steps: list[Step]) -> FinalMetrics:
    """Compute aggregate FinalMetrics from step-level metrics.

    Args:
        steps: All steps in the trajectory.

    Returns:
        FinalMetrics with token totals, duration, tool counts, and cache stats.
    """
    total_prompt = 0
    total_completion = 0
    total_cost: float | None = None
    total_cache_write = 0
    total_cache_read = 0
    tool_call_count = 0

    for step in steps:
        tool_call_count += len(step.tool_calls)
        if step.metrics:
            total_prompt += step.metrics.prompt_tokens
            total_completion += step.metrics.completion_tokens
            total_cache_read += step.metrics.cached_tokens
            total_cache_write += step.metrics.cache_creation_tokens
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
        total_cost_usd=total_cost,
        total_steps=len(steps),
        tool_call_count=tool_call_count,
        duration=duration,
        total_cache_write=total_cache_write,
        total_cache_read=total_cache_read,
    )
