"""Gemini CLI session JSON format parser.

Parses ~/.gemini/tmp/{project}/chats/session-*.json files containing
Gemini CLI session data with user and gemini message types.

Gemini CLI stores each session as a single JSON file (not JSONL), so the
entire conversation is loaded at once.  Key design differences from
Claude Code and Codex:

  - Tool calls and their results are **embedded** in the same ``gemini``
    message object (``toolCalls[].result``), so no cross-message pairing
    is needed.
  - Thinking is a structured ``thoughts`` array with ``subject`` /
    ``description`` pairs, not raw text.
  - The assistant role is recorded as ``type: "gemini"``; we normalise
    it to ``source: "agent"`` for the unified model.
  - Sub-agent sessions share the same ``sessionId`` but live in separate
    files with ``kind: "subagent"``.
"""

import hashlib
import json
from collections import Counter
from os.path import commonpath, dirname
from pathlib import Path

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import BaseParser, mark_error_content
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import (
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
)
from vibelens.utils import (
    coerce_to_string,
    deterministic_id,
    get_logger,
    load_json_file,
    parse_iso_timestamp,
)

logger = get_logger(__name__)

# Gemini CLI uses "gemini" instead of "assistant" for model responses.
RELEVANT_TYPES = {"user", "gemini"}

AGENT_NAME = "gemini"


class GeminiParser(BaseParser):
    """Parser for Gemini CLI's native session JSON format.

    Handles session JSON files with user and gemini messages,
    embedded tool calls, and structured thinking process.
    """

    def parse(self, content: str, source_path: str | None = None) -> list[Trajectory]:
        """Parse Gemini CLI session JSON content into a Trajectory.

        Args:
            content: Raw JSON content string.
            source_path: Original file path for project resolution.

        Returns:
            Single-element list with the Trajectory, or empty list.
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in Gemini session content")
            return []

        session_id = data.get("sessionId", "")
        if not session_id:
            return []

        collector = DiagnosticsCollector()
        raw_messages = data.get("messages", [])
        collector.total_lines = len(raw_messages) if isinstance(raw_messages, list) else 0
        steps = _build_steps(raw_messages, session_id)
        collector.parsed_lines = len(steps)
        if not steps:
            return []

        file_path = Path(source_path) if source_path else None
        project_path = _resolve_project(file_path, data, steps) if file_path else None
        extra = _build_diagnostics_extra(collector)
        agent = self.build_agent(AGENT_NAME)
        return [self.assemble_trajectory(
            session_id=session_id,
            agent=agent,
            steps=steps,
            project_path=project_path,
            extra=extra,
        )]


def _build_diagnostics_extra(collector: DiagnosticsCollector) -> dict | None:
    """Build trajectory extra dict from diagnostics if there are issues."""
    has_issues = (
        collector.skipped_lines > 0
        or collector.orphaned_tool_calls > 0
        or collector.orphaned_tool_results > 0
    )
    if not has_issues:
        return None
    return {"diagnostics": collector.to_diagnostics().model_dump()}


_DEFAULT_GEMINI_DIR = Path.home() / ".gemini"


def _resolve_project(
    file_path: Path, data: dict, steps: list[Step]
) -> str:
    """Resolve the project path using all available strategies.

    Strategy chain:
    1. Filesystem layout (file at ~/.gemini/tmp/{hash}/chats/)
    2. projectHash lookup against ~/.gemini/ (for files outside ~/.gemini/)
    3. Tool call argument inference
    4. Empty string (no project)

    Args:
        file_path: Path to the session JSON file.
        data: Parsed session JSON root object.
        steps: Parsed steps for tool-arg inference.

    Returns:
        Project path string, or empty string if unresolvable.
    """
    # Strategy 1: file is at the expected ~/.gemini/tmp/{hash}/chats/ location
    hash_dir = ""
    gemini_dir = None
    if file_path.parts:
        chats_parent = file_path.parent.parent
        if chats_parent.name and file_path.parent.name == "chats":
            hash_dir = chats_parent.name
            gemini_dir = chats_parent.parent.parent

    if hash_dir and gemini_dir:
        result = resolve_project_path(hash_dir, gemini_dir, steps)
        if result and result != hash_dir:
            return result

    # Strategy 2: use projectHash from session data against default ~/.gemini/
    project_hash = data.get("projectHash", "")
    if project_hash and _DEFAULT_GEMINI_DIR.is_dir():
        result = resolve_project_path(project_hash, _DEFAULT_GEMINI_DIR, steps)
        if result and result != project_hash:
            return result

    # Strategy 3: infer from tool call file paths
    if steps:
        result = _infer_project_from_tool_args(steps)
        if result:
            return result

    return ""


def _lookup_projects_json(projects_data: dict, hash_dir: str) -> str:
    """Reverse-lookup a project path from projects.json.

    Handles both Gemini projects.json formats:
    - Current: ``{projects: {path: dirname}}``
    - Legacy: ``{path: {hash: "..."}}``

    Args:
        projects_data: Parsed projects.json content.
        hash_dir: Directory name or SHA-256 hash to look up.

    Returns:
        Resolved project path, or empty string if not found.
    """
    # Current format: {projects: {path: dirname}}
    projects_map = projects_data.get("projects", {})
    if isinstance(projects_map, dict):
        for project_path, dirname in projects_map.items():
            if dirname == hash_dir:
                return project_path
            path_hash = hashlib.sha256(project_path.encode()).hexdigest()
            if path_hash == hash_dir:
                return project_path

    # Legacy format: {path: {hash: "..."}}
    for project_path, info in projects_data.items():
        if project_path == "projects":
            continue
        if isinstance(info, dict) and info.get("hash") == hash_dir:
            return project_path

    return ""


_PATH_ARG_KEYS = {"file_path", "path", "filename", "directory"}

# Avoid interpreting root-level paths like "/" or "/Users" as projects.
_MIN_PATH_DEPTH = 3


def resolve_project_path(
    hash_dir: str, gemini_dir: Path, steps: list[Step] | None = None
) -> str:
    """Resolve a Gemini SHA-256 hash directory to the original project path.

    Uses four strategies in order of speed:
    1. Check ``~/.gemini/tmp/{hash_dir}/.project_root`` file (fast path)
    2. Check ``~/.gemini/projects.json`` reverse lookup (medium path)
    3. Infer from tool call arguments in steps (slow path)
    4. Fall back to the hash string as-is

    Args:
        hash_dir: SHA-256 hash directory name.
        gemini_dir: Path to the ``~/.gemini`` directory.
        steps: Optional parsed steps for tool-arg inference.

    Returns:
        Resolved project path, or the hash string if unresolvable.
    """
    # Fast path: .project_root file inside the hash directory
    project_root_file = gemini_dir / "tmp" / hash_dir / ".project_root"
    try:
        if project_root_file.is_file():
            content = project_root_file.read_text(encoding="utf-8").strip()
            if content:
                return content
    except OSError:
        pass

    # Medium path: projects.json reverse lookup
    projects_file = gemini_dir / "projects.json"
    projects_data = load_json_file(projects_file)
    if isinstance(projects_data, dict):
        resolved = _lookup_projects_json(projects_data, hash_dir)
        if resolved:
            return resolved

    # Slow path: infer from tool call arguments
    if steps:
        inferred = _infer_project_from_tool_args(steps)
        if inferred:
            return inferred

    return hash_dir


def _infer_project_from_tool_args(steps: list[Step]) -> str:
    """Infer the project directory from absolute paths in tool call inputs.

    Args:
        steps: Parsed steps with tool_calls.

    Returns:
        Inferred project path, or empty string if insufficient data.
    """
    absolute_paths: list[str] = []
    for step in steps:
        for tc in step.tool_calls:
            if not isinstance(tc.arguments, dict):
                continue
            for key in _PATH_ARG_KEYS:
                value = tc.arguments.get(key, "")
                if isinstance(value, str) and value.startswith("/"):
                    absolute_paths.append(value)

    if len(absolute_paths) < 2:
        return ""

    directories = [dirname(p) if not p.endswith("/") else p.rstrip("/") for p in absolute_paths]
    dir_counts: Counter[str] = Counter()
    for directory in directories:
        parts = directory.split("/")
        if len(parts) >= _MIN_PATH_DEPTH:
            dir_counts[directory] += 1

    if not dir_counts:
        return ""

    try:
        prefix = commonpath(absolute_paths)
    except ValueError:
        return ""

    prefix_parts = prefix.split("/")
    if len(prefix_parts) < _MIN_PATH_DEPTH:
        most_common = dir_counts.most_common(1)[0]
        if most_common[1] >= 2:
            return most_common[0]
        return ""

    return prefix


def _build_steps(raw_messages: list, session_id: str) -> list[Step]:
    """Convert Gemini CLI messages into Step objects.

    Args:
        raw_messages: Raw message dicts from session JSON.
        session_id: Session identifier.

    Returns:
        Ordered list of Step objects.
    """
    steps = []
    for idx, raw in enumerate(raw_messages):
        if not isinstance(raw, dict):
            continue
        msg_type = raw.get("type", "")
        if msg_type not in RELEVANT_TYPES:
            continue

        step_id = raw.get("id") or deterministic_id("msg", session_id, str(idx), msg_type)
        timestamp = parse_iso_timestamp(raw.get("timestamp"))

        if msg_type == "user":
            steps.append(
                Step(
                    step_id=step_id,
                    source=StepSource.USER,
                    message=_extract_user_content(raw),
                    timestamp=timestamp,
                )
            )
        elif msg_type == "gemini":
            content = raw.get("content", "")
            thinking = _extract_thinking(raw)
            # Gemini sometimes produces only thoughts with empty content
            message = content if content else (thinking or "")
            tool_calls, observation = _build_tool_calls_and_observation(
                raw.get("toolCalls", []), session_id, idx
            )
            steps.append(
                Step(
                    step_id=step_id,
                    source=StepSource.AGENT,
                    message=message,
                    reasoning_content=thinking,
                    model_name=raw.get("model") or None,
                    timestamp=timestamp,
                    metrics=_parse_gemini_tokens(raw.get("tokens")),
                    tool_calls=tool_calls,
                    observation=observation,
                )
            )

    return steps


def _extract_user_content(raw: dict) -> str:
    """Extract plain text from a user message's content array."""
    return coerce_to_string(raw.get("content", []))


def _extract_thinking(raw: dict) -> str | None:
    """Extract concatenated thinking text from thoughts array.

    Gemini structures thinking as ``{subject, description, timestamp}``
    objects. We flatten them into ``[Subject] description`` formatting.
    """
    thoughts = raw.get("thoughts", [])
    if not thoughts:
        return None
    parts = []
    for thought in thoughts:
        if not isinstance(thought, dict):
            continue
        subject = thought.get("subject", "")
        description = thought.get("description", "")
        if subject and description:
            parts.append(f"[{subject}] {description}")
        elif description:
            parts.append(description)
    return "\n".join(parts) if parts else None


def _parse_gemini_tokens(tokens: dict | None) -> Metrics | None:
    """Parse Gemini CLI token statistics into Metrics."""
    if not tokens:
        return None
    return Metrics(
        prompt_tokens=tokens.get("input", 0),
        completion_tokens=tokens.get("output", 0),
        cached_tokens=tokens.get("cached", 0),
    )


def _build_tool_calls_and_observation(
    raw_tool_calls: list, session_id: str, msg_idx: int
) -> tuple[list[ToolCall], Observation | None]:
    """Convert Gemini CLI toolCalls into ToolCall objects and Observation.

    Gemini embeds the result directly inside each toolCall object,
    so no cross-entry pairing is needed.

    Args:
        raw_tool_calls: Raw toolCalls array from session JSON.
        session_id: Session identifier.
        msg_idx: Message index for deterministic ID generation.

    Returns:
        Tuple of (tool_calls, observation).
    """
    calls = []
    obs_results = []
    for tc_idx, tool in enumerate(raw_tool_calls):
        if not isinstance(tool, dict):
            continue
        tool_name = tool.get("name", "unknown")
        tc_id = tool.get("id") or deterministic_id(
            "tc", session_id, tool_name, str(msg_idx), str(tc_idx)
        )
        calls.append(
            ToolCall(
                tool_call_id=tc_id,
                function_name=tool_name,
                arguments=tool.get("args"),
            )
        )
        output = _extract_tool_output(tool.get("result", []))
        has_error = tool.get("status") == "error"
        content = mark_error_content(output) if has_error else output
        obs_results.append(
            ObservationResult(
                source_call_id=tc_id,
                content=content,
            )
        )

    observation = Observation(results=obs_results) if obs_results else None
    return calls, observation


def _extract_tool_output(result: list) -> str | None:
    """Extract output text from a Gemini toolCall result array."""
    if not result:
        return None
    parts = []
    for item in result:
        if not isinstance(item, dict):
            continue
        response = item.get("functionResponse", {}).get("response", {})
        output = response.get("output", "")
        if output:
            parts.append(output)
    return "\n".join(parts) if parts else None
