"""Claude Code JSONL format parser.

Parses ~/.claude/history.jsonl for session indices and individual
session .jsonl files for full conversation data, including subagent
conversations stored in {session-id}/subagents/ directories.

Claude Code stores each conversation event as a separate JSONL line with
a top-level ``type`` field (``"user"`` or ``"assistant"``).  Tool use
follows the Anthropic Messages API convention: tool invocations appear
as ``tool_use`` content blocks inside assistant messages, while their
results come back as ``tool_result`` blocks inside the *next* user
message, linked by ``tool_use_id``.  This two-message pairing requires
a pre-scan to build the result map before constructing ToolCall objects.
"""

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import (
    BaseParser,
    _is_meaningful_prompt,
    mark_error_content,
)
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import (
    Agent,
    FinalMetrics,
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
    TrajectoryRef,
)
from vibelens.models.trajectories.trajectory import DEFAULT_ATIF_VERSION
from vibelens.utils import coerce_to_string, get_logger, normalize_timestamp

# Sentinel for sorting steps that lack timestamps — placed before all
# real timestamps so they don't disrupt chronological ordering.
_EPOCH_MIN = datetime.min.replace(tzinfo=UTC)

logger = get_logger(__name__)

# Only "user" and "assistant" carry conversation content.
# Other types (e.g. "result", "progress") are internal bookkeeping.
RELEVANT_TYPES = {"user", "assistant"}

# ATIF source mapping for Claude Code role names
_ROLE_TO_SOURCE = {"user": StepSource.USER, "assistant": StepSource.AGENT}

AGENT_NAME = "claude-code"

# Number of lines to probe for project path extraction
PROJECT_PATH_PROBE_LIMIT = 10

# Tool names that spawn sub-agent JSONL files in subagents/ directory.
# Claude Code renamed "Agent" to "Task" in later versions.
_SUBAGENT_TOOL_NAMES = {"Agent", "Task"}

# Pattern to extract agentId from Task/Agent tool_result content.
# Claude Code embeds "agentId: {hex_hash}" in the tool output text.
_AGENT_ID_PATTERN = re.compile(r"agentId:\s*([a-f0-9]+)")


class ClaudeCodeParser(BaseParser):
    """Parser for Claude Code's native JSONL format.

    Handles both the history index (history.jsonl) and individual
    session files, including subagent conversations.
    """

    def parse(self, content: str, source_path: str | None = None) -> list[Trajectory]:
        """Parse JSONL session content into Trajectory objects.

        Returns a list containing the main session trajectory and any
        sub-agent trajectories. Sub-agents are separate Trajectory objects
        with parent_session_ref pointing back to the main session.

        Args:
            content: Raw JSONL content string.
            source_path: Original file path for sub-agent file discovery.

        Returns:
            List of Trajectory objects (main + sub-agents).
        """
        collector = DiagnosticsCollector()
        project_path = _extract_project_path(content)
        session_id, parent_sid, model_name, version = _extract_session_metadata(content)

        # Use extracted session_id, fallback to filename stem, then UUID
        if not session_id:
            session_id = Path(source_path).stem if source_path else str(uuid4())

        steps = self._parse_content(content, diagnostics=collector, session_id=session_id)
        if not steps:
            return []

        agent = self.build_agent(AGENT_NAME, version=version, model=model_name)
        extra = _build_diagnostics_extra(collector)

        # Sub-agent trajectories require filesystem access via source_path
        sub_trajectories: list[Trajectory] = []
        if source_path:
            sub_trajectories = self._parse_subagent_trajectories(
                Path(source_path), content, steps, session_id
            )
            if sub_trajectories:
                extra = extra or {}
                extra["sub_agent_count"] = len(sub_trajectories)

        parent_ref = TrajectoryRef(session_id=parent_sid) if parent_sid else None
        main_trajectory = self.assemble_trajectory(
            session_id=session_id,
            agent=agent,
            steps=steps,
            project_path=project_path,
            parent_trajectory_ref=parent_ref,
            extra=extra,
        )

        if sub_trajectories:
            _validate_subagent_linkage(main_trajectory, sub_trajectories)

        return [main_trajectory, *sub_trajectories]

    def parse_history_index(
        self, claude_dir: Path, since: datetime | None = None, limit: int | None = None
    ) -> list[Trajectory]:
        """Parse history.jsonl to build lightweight skeleton Trajectory objects.

        Groups entries by sessionId, extracts project name, first message,
        timestamp, and step count per session. These are skeleton
        trajectories for listing — full parse happens on get_session().

        Args:
            claude_dir: Path to ~/.claude directory.
            since: Only include sessions with activity at or after this time.
            limit: Maximum number of sessions to return (after sorting).

        Returns:
            List of skeleton Trajectory objects sorted by timestamp descending.
        """
        history_file = claude_dir / "history.jsonl"
        if not history_file.exists():
            logger.warning("history.jsonl not found at %s", history_file)
            return []

        since_ms = int(since.timestamp() * 1000) if since else 0
        sessions = _aggregate_history_lines(history_file, since_ms)

        trajectories = []
        for session_id, data in sessions.items():
            project_path = data["project_path"] or None
            first_message = self.truncate_first_message(data["first_message"]) or None
            timestamp = datetime.fromtimestamp(data["last_timestamp"] / 1000, tz=UTC)

            # Skeleton step so Trajectory validation passes (min_length=1)
            skeleton_step = Step(
                step_id="index-0",
                source=StepSource.USER,
                message=first_message or "",
                timestamp=timestamp,
            )

            # Build trajectory directly — skeleton data should not trigger
            # derived field computation from assemble_trajectory
            trajectories.append(
                Trajectory(
                    schema_version=DEFAULT_ATIF_VERSION,
                    session_id=session_id,
                    project_path=project_path,
                    first_message=first_message,
                    agent=Agent(name=AGENT_NAME),
                    steps=[skeleton_step],
                    final_metrics=FinalMetrics(total_steps=data["message_count"]),
                    extra={"is_skeleton": True, "total_entries": data["message_count"]},
                )
            )

        trajectories.sort(key=lambda t: t.steps[0].timestamp or _EPOCH_MIN, reverse=True)
        if limit is not None:
            trajectories = trajectories[:limit]
        return trajectories

    def parse_session_jsonl(self, file_path: Path) -> list[Step]:
        """Parse a session .jsonl file into main-session steps only.

        Args:
            file_path: Path to the session .jsonl file.

        Returns:
            List of Step objects for the main session (no sub-agents).
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Cannot read file: %s", file_path)
            return []
        return self._parse_content(content)

    def _parse_subagent_trajectories(
        self, source_path: Path, raw_content: str, parent_steps: list[Step], parent_sid: str
    ) -> list[Trajectory]:
        """Parse sub-agent JSONL files into separate Trajectory objects.

        Each sub-agent trajectory has a parent_session_ref pointing back
        to the parent session, and the parent step's observation is
        updated with a subagent_trajectory_ref.

        Matching uses agentId extracted from raw Task/Agent tool_result
        content, not positional ordering, to ensure correctness even
        when the bounded tool result cache evicts early entries.

        Args:
            source_path: Path to the main session .jsonl file.
            raw_content: Raw JSONL content of the main session.
            parent_steps: Parsed steps from the main session.
            parent_sid: Session ID of the parent.

        Returns:
            List of sub-agent Trajectory objects.
        """
        subagent_dir = source_path.parent / source_path.stem / "subagents"
        if not subagent_dir.is_dir():
            return []

        agent_files = sorted(subagent_dir.glob("agent-*.jsonl"))
        if not agent_files:
            return []

        # Build agentId → (step_id, tool_call_id) from raw JSONL
        spawn_map = _build_agent_spawn_map(raw_content, parent_steps)

        sub_trajectories: list[Trajectory] = []
        for agent_file in agent_files:
            agent_id = agent_file.stem.removeprefix("agent-")
            spawn_info = spawn_map.get(agent_id)
            spawn_step_id = spawn_info[0] if spawn_info else None
            spawn_tool_call_id = spawn_info[1] if spawn_info else None

            sub_traj = self._build_subagent_trajectory(
                agent_file, parent_sid, source_path, spawn_step_id, spawn_tool_call_id
            )
            if sub_traj:
                sub_trajectories.append(sub_traj)
                if spawn_tool_call_id:
                    _link_subagent_to_parent(parent_steps, spawn_tool_call_id, agent_file.stem)

        return sub_trajectories

    def _build_subagent_trajectory(
        self,
        agent_file: Path,
        parent_sid: str,
        source_path: Path,
        spawn_step_id: str | None,
        spawn_tool_call_id: str | None,
    ) -> Trajectory | None:
        """Parse a single sub-agent file and assemble its Trajectory.

        Args:
            agent_file: Path to the sub-agent .jsonl file.
            parent_sid: Session ID of the parent.
            source_path: Path to the parent session file.
            spawn_step_id: Step ID in parent that spawned this agent.
            spawn_tool_call_id: Tool call ID that spawned this agent.

        Returns:
            Trajectory for the sub-agent, or None if parsing fails.
        """
        try:
            sub_content = agent_file.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Cannot read sub-agent file: %s", agent_file)
            return None

        sub_steps = self._parse_content(sub_content)
        if not sub_steps:
            return None

        _, _, sub_model, sub_version = _extract_session_metadata(sub_content)
        parent_ref = TrajectoryRef(
            session_id=parent_sid,
            step_id=spawn_step_id,
            tool_call_id=spawn_tool_call_id,
            trajectory_path=str(source_path),
        )

        return self.assemble_trajectory(
            session_id=agent_file.stem,
            agent=self.build_agent(AGENT_NAME, version=sub_version, model=sub_model),
            steps=sub_steps,
            project_path=_extract_project_path(sub_content),
            parent_trajectory_ref=TrajectoryRef(session_id=parent_sid),
            parent_ref=parent_ref,
        )

    @staticmethod
    def discover_subagent_only_sessions(project_dir: Path) -> list[Path]:
        """Find session dirs that have only subagent files and no root JSONL.

        Args:
            project_dir: Directory containing session subdirectories.

        Returns:
            List of subagent directory paths without a root JSONL file.
        """
        orphaned = []
        try:
            for subagent_dir in project_dir.glob("*/subagents"):
                if not subagent_dir.is_dir():
                    continue
                session_dir = subagent_dir.parent
                root_jsonl = session_dir.parent / f"{session_dir.name}.jsonl"
                if not root_jsonl.exists() and list(subagent_dir.glob("agent-*.jsonl")):
                    orphaned.append(subagent_dir)
        except OSError:
            pass
        return orphaned

    def _parse_content(
        self,
        content: str,
        diagnostics: DiagnosticsCollector | None = None,
        session_id: str | None = None,
    ) -> list[Step]:
        """Parse JSONL content string into Step objects.

        Uses _decompose_raw_content() to convert Claude Code's polymorphic
        content block arrays into separated Step fields.

        Args:
            content: Raw JSONL content string.
            diagnostics: Optional collector for parse quality metrics.
            session_id: Main session ID for detecting copied context steps.

        Returns:
            List of Step objects.
        """
        raw_entries = _parse_jsonl_content(content, diagnostics)

        # Two-pass: first scan user messages for tool results,
        # then construct Steps with results already paired
        tool_results = _collect_tool_results(raw_entries)
        tool_use_ids: set[str] = set()
        seen_message_ids: set[str] = set()

        steps = []
        for entry in raw_entries:
            msg = entry.get("message", {})
            uuid = entry.get("uuid", str(uuid4()))
            timestamp = normalize_timestamp(entry.get("timestamp"))

            role = msg.get("role", entry.get("type", ""))
            source = _ROLE_TO_SOURCE.get(role, StepSource.USER)
            model_name = msg.get("model") or None
            raw_content = msg.get("content", "")

            # Deduplicate metrics: Claude Code emits the same message.id
            # across multiple JSONL lines (e.g. streaming chunks). Only
            # count usage from the first occurrence of each message.id.
            msg_id = msg.get("id")
            if msg_id and msg_id in seen_message_ids:
                metrics = None
            else:
                metrics = _parse_metrics(msg.get("usage"))
                if msg_id:
                    seen_message_ids.add(msg_id)

            # Decompose Anthropic Messages API content blocks into
            # separated ATIF Step fields with pre-scanned tool results
            message, reasoning_content, tool_calls, observation = _decompose_raw_content(
                raw_content, tool_results
            )

            # Skip "tool-relay" user messages — entries containing ONLY
            # tool_result blocks with no human-authored text. Their content
            # is already injected into the preceding assistant step via the
            # pre-scan tool_results map (tool_use_id linkage).
            #
            # This intentionally produces fewer steps than Harbor, which
            # preserves the raw API message structure (one step per API
            # message). VibeLens omits tool-relay messages for cleaner
            # analytical semantics: each user step represents a genuine
            # human turn, not an API bookkeeping artifact.
            if source == StepSource.USER and not message and not tool_calls and observation is None:
                continue

            for tc in tool_calls:
                if tc.tool_call_id:
                    tool_use_ids.add(tc.tool_call_id)
                    if diagnostics:
                        diagnostics.record_tool_call()

            # Detect steps copied from a previous session for context
            entry_session_id = entry.get("sessionId", "")
            is_copied = (
                session_id is not None and entry_session_id and entry_session_id != session_id
            )

            steps.append(
                Step(
                    step_id=uuid,
                    source=source,
                    message=message,
                    reasoning_content=reasoning_content,
                    model_name=model_name,
                    timestamp=timestamp,
                    metrics=metrics,
                    tool_calls=tool_calls,
                    observation=observation,
                    is_copied_context=True if is_copied else None,
                    extra=_build_step_extra(entry),
                )
            )

        if diagnostics:
            _detect_orphans(tool_use_ids, tool_results, diagnostics)

        return steps


def _parse_jsonl_content(
    content: str, diagnostics: DiagnosticsCollector | None = None
) -> list[dict]:
    """Parse JSONL content string into relevant entry dicts.

    Filters for RELEVANT_TYPES, handles queue-operation events, and
    tracks parse quality via diagnostics.

    Queue-operation handling: when a user types while the assistant is
    still processing, Claude Code queues the message as an ``enqueue``
    event. If it's later delivered normally, a ``dequeue`` event appears
    followed by a regular ``type: "user"`` message. If instead it's
    injected as a system-reminder and removed, only ``enqueue`` +
    ``remove`` exist — no standalone user message is emitted. We create
    synthetic user entries for enqueue+remove pairs to preserve that
    user intent.

    Args:
        content: Raw JSONL content.
        diagnostics: Optional collector for tracking skipped lines.

    Returns:
        List of parsed dicts with relevant types only.
    """
    all_parsed: list[dict] = []
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if diagnostics:
            diagnostics.total_lines += 1
        try:
            entry = json.loads(stripped)
            if diagnostics:
                diagnostics.parsed_lines += 1
        except json.JSONDecodeError:
            if diagnostics:
                diagnostics.record_skip("invalid JSON")
            continue
        all_parsed.append(entry)

    # Pre-scan: identify enqueue timestamps that were later dequeued
    # (delivered as normal user messages). Only enqueue+remove pairs
    # need synthetic user entries.
    dequeued_timestamps = _collect_dequeued_timestamps(all_parsed)

    raw_entries: list[dict] = []
    for entry in all_parsed:
        entry_type = entry.get("type")
        if entry_type in RELEVANT_TYPES:
            raw_entries.append(entry)
            continue
        if (
            entry_type == "queue-operation"
            and entry.get("operation") == "enqueue"
            and entry.get("content")
            and entry.get("timestamp", "") not in dequeued_timestamps
        ):
            raw_entries.append(_make_enqueue_user_entry(entry))
    return raw_entries


def _collect_dequeued_timestamps(all_parsed: list[dict]) -> set[str]:
    """Collect timestamps of enqueue events that were later dequeued.

    Dequeued messages are delivered as normal ``type: "user"`` entries,
    so creating a synthetic user entry would duplicate them.

    Args:
        all_parsed: All parsed JSONL entries (unfiltered).

    Returns:
        Set of timestamp strings for enqueue events followed by dequeue.
    """
    dequeued: set[str] = set()
    for entry in all_parsed:
        if entry.get("type") == "queue-operation" and entry.get("operation") == "dequeue":
            ts = entry.get("timestamp", "")
            if ts:
                dequeued.add(ts)
    return dequeued


def _make_enqueue_user_entry(entry: dict) -> dict:
    """Transform a queue-operation enqueue event into a synthetic user entry.

    When a user types a message while the assistant is still processing,
    Claude Code queues it as an enqueue event. If the message is later
    removed (not dequeued), no standalone user message exists — the
    enqueue is the only record of the user's input.

    Args:
        entry: Raw queue-operation JSONL entry with operation="enqueue".

    Returns:
        Synthetic user entry compatible with _parse_content() processing.
    """
    ts = entry.get("timestamp", "")
    unique_id = f"enqueue-{ts}-{uuid4().hex[:8]}" if ts else f"enqueue-{uuid4()}"
    return {
        "type": "user",
        "uuid": unique_id,
        "sessionId": entry.get("sessionId", ""),
        "timestamp": entry.get("timestamp"),
        "message": {
            "role": "user",
            "content": entry["content"],
        },
        "_queue_operation": "enqueue",
    }


def _build_step_extra(entry: dict) -> dict[str, Any] | None:
    """Build step-level extra dict from Claude Code entry fields.

    Extracts format-specific metadata mirroring Harbor's convention:
    is_sidechain, stop_reason, cwd, request_id, and service_tier.

    Args:
        entry: Raw JSONL entry dict.

    Returns:
        Extra dict with format-specific fields, or None if empty.
    """
    extra: dict[str, Any] = {}
    msg = entry.get("message", {})
    if not isinstance(msg, dict):
        msg = {}

    if entry.get("_queue_operation"):
        extra["is_queued_prompt"] = True

    if entry.get("isSidechain", False):
        extra["is_sidechain"] = True

    stop_reason = msg.get("stop_reason")
    if stop_reason is not None:
        extra["stop_reason"] = stop_reason

    cwd = entry.get("cwd")
    if cwd:
        extra["cwd"] = cwd

    request_id = msg.get("requestId")
    if request_id:
        extra["request_id"] = request_id

    service_tier = msg.get("service_tier")
    if service_tier:
        extra["service_tier"] = service_tier

    return extra or None


def _build_diagnostics_extra(collector: DiagnosticsCollector) -> dict | None:
    """Build trajectory extra dict from diagnostics if there are issues.

    Args:
        collector: Diagnostics collector from parsing.

    Returns:
        Extra dict with diagnostics, or None if no issues.
    """
    has_issues = (
        collector.skipped_lines > 0
        or collector.orphaned_tool_calls > 0
        or collector.orphaned_tool_results > 0
    )
    if not has_issues:
        return None
    return {"diagnostics": collector.to_diagnostics().model_dump()}


def _extract_project_path(content: str) -> str | None:
    """Extract the project working directory from the first JSONL entries.

    Claude Code entries carry a ``cwd`` field with the absolute working
    directory. We probe the first few lines to find the most common one.

    Args:
        content: Raw JSONL content string.

    Returns:
        Project path string, or None if not found.
    """
    cwd_values: list[str] = []
    for line in content.split("\n"):
        if len(cwd_values) >= PROJECT_PATH_PROBE_LIMIT:
            break
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        cwd = entry.get("cwd", "")
        if cwd:
            cwd_values.append(cwd)
    if not cwd_values:
        return None
    return Counter(cwd_values).most_common(1)[0][0]


def _extract_session_metadata(
    content: str,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Extract session_id, parent_sid, model_name, and version from JSONL.

    Scans all lines to find the most common sessionId (current session),
    any divergent sessionId (parent/continued session), the most common
    model name from assistant messages, and the CLI version string.

    Args:
        content: Raw JSONL content string.

    Returns:
        Tuple of (session_id, parent_sid, model_name, version).
    """
    session_counter: Counter[str] = Counter()
    model_counter: Counter[str] = Counter()
    version: str | None = None

    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except json.JSONDecodeError:
            continue

        sid = entry.get("sessionId", "")
        if sid:
            session_counter[sid] += 1

        if version is None:
            raw_version = entry.get("version", "")
            if raw_version:
                version = str(raw_version)

        msg = entry.get("message", {})
        if isinstance(msg, dict):
            model = msg.get("model", "")
            # Exclude synthetic markers like "<synthetic>" from model detection
            if model and not model.startswith("<"):
                model_counter[model] += 1

    session_id = session_counter.most_common(1)[0][0] if session_counter else None
    parent_sid = None
    for sid in session_counter:
        if sid != session_id:
            parent_sid = sid
            break

    model_name = model_counter.most_common(1)[0][0] if model_counter else None
    return session_id, parent_sid, model_name, version


def _decompose_raw_content(
    raw_content: str | list, tool_results: dict[str, dict] | None = None
) -> tuple[str, str | None, list[ToolCall], Observation | None]:
    """Decompose Anthropic Messages API content into separated Step fields.

    Converts the polymorphic content block array from Claude Code API
    responses into separated ATIF Step fields: message (text),
    reasoning_content (thinking), tool_calls, and observation.

    When tool_results is provided, injects matching tool results from
    the pre-scan map to produce proper Observation objects.

    Args:
        raw_content: Raw content from JSONL entry (str or list of dicts).
        tool_results: Optional pre-scanned tool_use_id -> result mapping.

    Returns:
        Tuple of (message, reasoning_content, tool_calls, observation).
    """
    if isinstance(raw_content, str):
        stripped = raw_content.strip()
        return (stripped, None, [], None) if stripped else ("", None, [], None)

    if not isinstance(raw_content, list):
        return ("", None, [], None)

    text_parts: list[str] = []
    thinking_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    obs_results: list[ObservationResult] = []
    tool_results = tool_results or {}

    for block in raw_content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type", "text")

        if block_type == "text":
            text = block.get("text", "")
            if text:
                text_parts.append(text)

        elif block_type == "thinking":
            thinking = block.get("thinking", "")
            if thinking:
                thinking_parts.append(thinking)

        elif block_type == "tool_use":
            tool_call_id = block.get("id", "")
            tool_calls.append(
                ToolCall(
                    tool_call_id=tool_call_id,
                    function_name=block.get("name", ""),
                    arguments=block.get("input"),
                )
            )
            # Inject pre-scanned tool result if available
            result = tool_results.get(tool_call_id) if tool_call_id else None
            if result:
                output = result.get("output")
                if result.get("is_error", False):
                    output = mark_error_content(output)
                obs_results.append(
                    ObservationResult(
                        source_call_id=tool_call_id,
                        content=output,
                        extra=_extract_tool_result_metadata(result),
                    )
                )

        elif block_type == "tool_result":
            # When pre-scan results are available, tool_result blocks are
            # already captured via the tool_use branch above. Skip direct
            # processing to prevent duplicate ObservationResults.
            if tool_results:
                continue
            result_text = _extract_tool_result_content(block.get("content"))
            if block.get("is_error"):
                result_text = mark_error_content(result_text)
            obs_results.append(
                ObservationResult(source_call_id=block.get("tool_use_id", ""), content=result_text)
            )

    message = "\n\n".join(text_parts).strip() if text_parts else ""
    reasoning_content = "\n\n".join(thinking_parts).strip() if thinking_parts else None
    observation = Observation(results=obs_results) if obs_results else None

    return message, reasoning_content, tool_calls, observation


def _extract_tool_result_content(content: str | list | None) -> str | None:
    """Extract plain text from a tool_result content field.

    Args:
        content: Raw content from a tool_result block (str, list, or None).

    Returns:
        Extracted text, or None if empty.
    """
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
        return "\n".join(parts) if parts else None
    return str(content)


def _extract_tool_result_metadata(result: dict) -> dict[str, Any] | None:
    """Extract structured execution metadata from a cached tool result.

    When the tool result cache contains a ``tool_use_result`` dict (captured
    from the event-level ``toolUseResult`` field), extracts salient fields:
    exit_code, stdout_length, stderr_length, and interrupted.

    Args:
        result: A single entry from the tool_results cache dict.

    Returns:
        Metadata dict, or None if no structured metadata is available.
    """
    tur = result.get("tool_use_result")
    if not isinstance(tur, dict):
        return None

    meta: dict[str, Any] = {}
    exit_code = tur.get("exitCode")
    if exit_code is None:
        exit_code = tur.get("exit_code")
    if exit_code is not None:
        meta["exit_code"] = exit_code

    stdout = tur.get("stdout")
    if stdout is not None:
        meta["stdout_length"] = len(stdout) if isinstance(stdout, str) else 0

    stderr = tur.get("stderr")
    if stderr is not None:
        meta["stderr_length"] = len(stderr) if isinstance(stderr, str) else 0

    if tur.get("interrupted"):
        meta["interrupted"] = True

    return meta or None


def count_history_entries(claude_dir: Path) -> int:
    """Count lines in history.jsonl with O(1) memory via buffered byte reads.

    Args:
        claude_dir: Path to ~/.claude directory.

    Returns:
        Number of non-empty lines in history.jsonl, or 0 if missing.
    """
    history_file = claude_dir / "history.jsonl"
    if not history_file.exists():
        return 0

    count = 0
    buf_size = 65536
    try:
        with open(history_file, "rb") as f:
            while True:
                buf = f.read(buf_size)
                if not buf:
                    break
                count += buf.count(b"\n")
    except OSError:
        return 0
    return count


def _aggregate_history_lines(history_file: Path, since_ms: int) -> dict[str, dict]:
    """Read history.jsonl and group entries by session.

    Skips entries whose timestamp falls before ``since_ms`` for early
    filtering when callers only need recent sessions.

    Args:
        history_file: Path to the history.jsonl file.
        since_ms: Minimum timestamp in milliseconds (0 to include all).

    Returns:
        Dict mapping session_id -> aggregated session data.
    """
    sessions: dict[str, dict] = {}
    with open(history_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            session_id = entry.get("sessionId", "")
            if not session_id:
                continue

            timestamp_ms = entry.get("timestamp", 0)
            if since_ms and timestamp_ms < since_ms:
                continue

            display = entry.get("display", "")
            project_path = entry.get("project", "")

            if session_id not in sessions:
                sessions[session_id] = {
                    "first_timestamp": timestamp_ms,
                    "last_timestamp": timestamp_ms,
                    "first_message": display if _is_meaningful_prompt(display) else "",
                    "project_path": project_path,
                    "message_count": 1,
                }
            else:
                sess = sessions[session_id]
                sess["message_count"] += 1
                if not sess["first_message"] and _is_meaningful_prompt(display):
                    sess["first_message"] = display
                if timestamp_ms < sess["first_timestamp"]:
                    sess["first_timestamp"] = timestamp_ms
                    if _is_meaningful_prompt(display):
                        sess["first_message"] = display
                if timestamp_ms > sess["last_timestamp"]:
                    sess["last_timestamp"] = timestamp_ms
    return sessions


def _detect_orphans(
    tool_use_ids: set[str], tool_results: dict[str, dict], diagnostics: DiagnosticsCollector
) -> None:
    """Detect orphaned tool calls and results and record in diagnostics.

    Args:
        tool_use_ids: Set of tool_use IDs found in agent steps.
        tool_results: Mapping of tool_use_id -> result from user steps.
        diagnostics: Collector to record orphans into.
    """
    result_ids = set(tool_results.keys())
    for tc_id in tool_use_ids:
        diagnostics.record_tool_result()
        if tc_id not in result_ids:
            diagnostics.record_orphaned_call(tc_id)
    for result_id in result_ids:
        diagnostics.record_tool_result()
        if result_id not in tool_use_ids:
            diagnostics.record_orphaned_result(result_id)


def _build_agent_spawn_map(
    raw_content: str, parent_steps: list[Step]
) -> dict[str, tuple[str, str]]:
    """Build agentId → (step_id, tool_call_id) map from raw JSONL.

    Scans raw JSONL directly (not parsed steps) to avoid missing
    entries evicted from the bounded tool result cache. For each
    Task/Agent tool_use, finds the corresponding tool_result and
    extracts the 'agentId: {hash}' embedded in the output text.

    Args:
        raw_content: Raw JSONL content of the main session.
        parent_steps: Parsed steps for resolving tool_call_id → step_id.

    Returns:
        Dict mapping agentId to (step_id, tool_call_id).
    """
    # Pass 1: collect Task/Agent tool_use_ids from assistant messages
    spawn_tc_ids: set[str] = set()
    for line in raw_content.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        msg = entry.get("message", {})
        if not isinstance(msg, dict):
            continue
        for block in msg.get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") in _SUBAGENT_TOOL_NAMES:
                tc_id = block.get("id", "")
                if tc_id:
                    spawn_tc_ids.add(tc_id)

    if not spawn_tc_ids:
        return {}

    # Pass 2: find tool_results for these tool_use_ids, extract agentId
    agent_to_tc: dict[str, str] = {}
    for line in raw_content.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", {})
        if not isinstance(msg, dict):
            continue
        for block in msg.get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue
            tc_id = block.get("tool_use_id", "")
            if tc_id not in spawn_tc_ids:
                continue
            result_content = block.get("content", "")
            if isinstance(result_content, list):
                result_content = " ".join(
                    b.get("text", "") for b in result_content if isinstance(b, dict)
                )
            match = _AGENT_ID_PATTERN.search(str(result_content))
            if match:
                agent_to_tc[match.group(1)] = tc_id

    # Resolve tool_call_id → step_id via parsed steps
    tc_to_step_id: dict[str, str] = {}
    for step in parent_steps:
        for tc in step.tool_calls:
            if tc.tool_call_id in spawn_tc_ids:
                tc_to_step_id[tc.tool_call_id] = step.step_id

    return {
        agent_id: (tc_to_step_id.get(tc_id, ""), tc_id) for agent_id, tc_id in agent_to_tc.items()
    }


def _collect_tool_results(raw_entries: list[dict]) -> dict[str, dict]:
    """Build a mapping of tool_use_id -> result from user messages.

    Uses a plain dict (unbounded) so that long sessions with many tool
    calls do not lose early results to eviction. Also captures the
    event-level ``toolUseResult`` field (structured metadata like
    exit_code, stdout, stderr) for downstream extraction.
    """
    tool_results: dict[str, dict] = {}
    for entry in raw_entries:
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", {})
        content = msg.get("content", "")
        if not isinstance(content, list):
            continue
        # Event-level toolUseResult carries structured execution metadata
        tool_use_result = entry.get("toolUseResult")
        for block in content:
            if block.get("type") == "tool_result":
                tool_use_id = block.get("tool_use_id", "")
                if tool_use_id:
                    result_content = block.get("content", "")
                    is_error = block.get("is_error", False)
                    output = coerce_to_string(result_content)
                    result_entry: dict = {"output": output, "is_error": bool(is_error)}
                    if tool_use_result and isinstance(tool_use_result, dict):
                        result_entry["tool_use_result"] = tool_use_result
                    tool_results[tool_use_id] = result_entry
    return tool_results


def _parse_metrics(usage_data: dict | None) -> Metrics | None:
    """Parse Anthropic usage dict into VibeLens Metrics model.

    Token field mapping (VibeLens convention):
    - ``prompt_tokens`` = fresh input tokens only (Anthropic ``input_tokens``).
    - ``cached_tokens`` = cache-read tokens (Anthropic ``cache_read_input_tokens``).
    - ``cache_creation_tokens`` = tokens written to cache
      (Anthropic ``cache_creation_input_tokens``).
    - Total context window = ``prompt_tokens + cached_tokens``.

    Note: Harbor uses a different convention where
    ``prompt_tokens = input_tokens + cache_read_input_tokens`` (i.e. total
    context). VibeLens keeps them separated for finer-grained analysis.
    """
    if not usage_data:
        return None
    return Metrics(
        prompt_tokens=usage_data.get("input_tokens", 0),
        completion_tokens=usage_data.get("output_tokens", 0),
        cache_creation_tokens=usage_data.get("cache_creation_input_tokens", 0),
        cached_tokens=usage_data.get("cache_read_input_tokens", 0),
    )


def _link_subagent_to_parent(
    parent_steps: list[Step], spawn_tool_call_id: str, sub_agent_id: str
) -> None:
    """Add a subagent_trajectory_ref to the parent step's observation.

    Args:
        parent_steps: Steps from the parent session.
        spawn_tool_call_id: Tool call ID that spawned the sub-agent.
        sub_agent_id: Session ID of the sub-agent trajectory.
    """
    for step in parent_steps:
        if not step.observation:
            continue
        for result in step.observation.results:
            if result.source_call_id == spawn_tool_call_id:
                ref = TrajectoryRef(session_id=sub_agent_id)
                if result.subagent_trajectory_ref is None:
                    result.subagent_trajectory_ref = [ref]
                else:
                    result.subagent_trajectory_ref.append(ref)
                return


def _validate_subagent_linkage(
    main_trajectory: Trajectory, sub_trajectories: list[Trajectory]
) -> None:
    """Warn about broken subagent references between parent and children.

    Checks two invariants:
    - Every subagent_trajectory_ref.session_id in the parent points to
      an existing sub-trajectory.
    - Every sub-trajectory is referenced by at least one parent step.

    Uses logger.warning (not errors) since subagent files may be missing
    or the session may have been interrupted before completion.

    Args:
        main_trajectory: The parent session trajectory.
        sub_trajectories: List of parsed sub-agent trajectories.
    """
    sub_ids = {t.session_id for t in sub_trajectories}

    # Collect all subagent refs from parent observation results
    parent_refs: set[str] = set()
    for step in main_trajectory.steps:
        if not step.observation:
            continue
        for result in step.observation.results:
            if result.subagent_trajectory_ref:
                for ref in result.subagent_trajectory_ref:
                    parent_refs.add(ref.session_id)

    # Parent refs pointing to missing sub-trajectories
    dangling_refs = parent_refs - sub_ids
    if dangling_refs:
        logger.warning(
            "Session %s: parent references missing sub-trajectories: %s",
            main_trajectory.session_id,
            dangling_refs,
        )

    # Sub-trajectories not referenced by any parent step
    unreferenced = sub_ids - parent_refs
    if unreferenced:
        logger.warning(
            "Session %s: sub-trajectories not referenced by parent: %s",
            main_trajectory.session_id,
            unreferenced,
        )
