"""Codex CLI rollout JSONL format parser.

Parses ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl files containing
Codex CLI session data with session_meta, response_item, turn_context,
and event_msg entries.

Codex uses the OpenAI Responses API convention where each JSONL line is
a ``RolloutItem`` envelope with ``{timestamp, type, payload}``.  Unlike
Claude Code, tool invocations are *separate* ``response_item`` entries
(``function_call`` + ``function_call_output`` linked by ``call_id``)
rather than content blocks embedded in the assistant message.  This
requires a two-pass approach: first collect all tool outputs by call_id,
then attach them to the assistant message that preceded them.

The rollout also has a ``turn_context`` entry per turn carrying the
active model name, which can change mid-session (e.g. switching between
gpt-5.4 and a lighter model), so model tracking is per-turn rather than
per-session.
"""

import hashlib
import re
import sqlite3
from collections import OrderedDict
from pathlib import Path
from typing import NamedTuple
from uuid import uuid4

import orjson
from pydantic import BaseModel, Field

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import BaseParser
from vibelens.ingest.parsers.helpers import (
    ROLE_TO_SOURCE,
    iter_jsonl_safe,
    parse_tool_arguments,
    truncate_first_message,
)
from vibelens.models.enums import AgentType, StepSource
from vibelens.models.trajectories import (
    FinalMetrics,
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
    TrajectoryRef,
)
from vibelens.utils import (
    coerce_to_string,
    get_logger,
    normalize_timestamp,
    parse_iso_timestamp,
)

logger = get_logger(__name__)

# Skip "developer" role (system prompts, AGENTS.md injections, permission
# instructions) since they are boilerplate and not user-facing conversation.
RELEVANT_ROLES = {"user", "assistant"}

# Cap the tool-result lookup map to avoid unbounded memory on huge sessions
MAX_TOOL_RESULT_CACHE = 500

# Matches the metadata prefix Codex prepends to tool outputs:
#
#   Exit code: 0
#   Wall time: 1.23s
#   Output:
#   <actual output>
_OUTPUT_PREFIX_RE = re.compile(
    r"^Exit code:\s*(\d+)\nWall time:\s*([0-9.]+)s?\nOutput:\n", re.DOTALL
)

# Tool output types that carry results linked by call_id
_TOOL_OUTPUT_TYPES = {"function_call_output", "custom_tool_call_output"}

# Tool call types that initiate tool invocations
_TOOL_CALL_TYPES = {"function_call", "custom_tool_call"}

# Codex injects several XML-wrapped system turns as role=user messages.
# We reclassify them to StepSource.SYSTEM so they do not look like user input.
_CODEX_SYSTEM_TAG_PREFIXES = (
    "<environment_context",
    "<turn_aborted",
    "<subagent_notification",
    "<user_instructions",
)

# Tool name that Codex uses to spawn a sub-agent. Output is JSON
# ``{"agent_id": "<child-thread-id>", "nickname": "..."}`` where
# ``agent_id`` matches the child rollout's ``session_meta.id``.
_SPAWN_AGENT_TOOL_NAME = "spawn_agent"


class _CodexSessionMeta(NamedTuple):
    """Aggregated metadata from a single pass over raw JSONL content."""

    session_id: str | None
    cli_version: str | None
    model_name: str | None
    project_path: str | None
    source: str | None
    originator: str | None
    effort: str | None
    sandbox_policy: str | None
    approval_policy: str | None
    forked_from_id: str | None
    agent_role: str | None
    agent_nickname: str | None


class _CodexParseState(BaseModel):
    """Mutable state carried across response_item processing.

    Codex emits tool calls and reasoning as separate JSONL entries
    *between* message entries, with no explicit end-of-turn marker.
    We buffer them here and flush to the preceding agent step
    when the next message boundary arrives (or at end-of-file).
    """

    pending_tools: list[ToolCall] = Field(
        default_factory=list, description="Tool calls buffered until the next message boundary."
    )
    pending_obs_results: list[ObservationResult] = Field(
        default_factory=list, description="Observation results buffered for the preceding step."
    )
    current_model: str = Field(
        default="", description="Active model name from the most recent turn_context."
    )
    current_cwd: str = Field(
        default="", description="Working directory from the most recent turn_context."
    )
    current_effort: str = Field(
        default="", description="Reasoning effort from the most recent turn_context."
    )
    pending_thinking: list[str] = Field(
        default_factory=list, description="Reasoning text blocks buffered for attachment."
    )
    thinking_seen: set[str] = Field(
        default_factory=set, description="MD5 hashes of reasoning blocks seen for deduplication."
    )


class CodexParser(BaseParser):
    """Parser for Codex CLI's native rollout JSONL format.

    Handles rollout files containing session_meta, response_item,
    turn_context, and event_msg entries.
    """

    AGENT_TYPE = AgentType.CODEX
    LOCAL_DATA_DIR: Path | None = Path.home() / ".codex"

    def discover_session_files(self, data_dir: Path) -> list[Path]:
        """Find Codex rollout session files."""
        return sorted(f for f in data_dir.rglob("*.jsonl") if f.stem.startswith("rollout-"))

    # ---- 4-stage parsing ----
    def _decode_file(self, file_path: Path, diagnostics: DiagnosticsCollector) -> list[dict] | None:
        """Stage 1: read JSONL + drop fork-mode prelude (parent history before model_switch)."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read Codex rollout %s: %s", file_path, exc)
            return None
        entries = list(iter_jsonl_safe(content, diagnostics=diagnostics))
        if not entries:
            return None
        return _strip_fork_prelude(entries)

    def _extract_metadata(
        self, raw: list[dict], file_path: Path, diagnostics: DiagnosticsCollector
    ) -> Trajectory | None:
        """Stage 2: session_meta scan → session_id, model, version, parent linkage.

        Three signals point a child at its parent, in order of strength:
          1. ``forked_from_id`` on session_meta — fork-mode children only.
          2. ``source.subagent.thread_spawn.parent_thread_id`` — both modes.
          3. ``agent_role`` alone — confirms sub-agent status; parent stays unknown.
        """
        meta = _scan_session_metadata(raw)
        session_id = meta.session_id or file_path.stem or str(uuid4())
        parent_id = meta.forked_from_id or _parent_id_from_source(meta.source)
        extra = _build_session_extra(meta)
        total_usage = _extract_final_token_usage(raw)
        if total_usage:
            extra = extra or {}
            extra["total_token_usage"] = total_usage
        return Trajectory(
            session_id=session_id,
            agent=self.build_agent(version=meta.cli_version, model_name=meta.model_name),
            project_path=meta.project_path,
            parent_trajectory_ref=TrajectoryRef(session_id=parent_id) if parent_id else None,
            extra=extra,
        )

    def _build_steps(
        self, raw: list[dict], traj: Trajectory, file_path: Path, diagnostics: DiagnosticsCollector
    ) -> list[Step]:
        """Stage 3: build steps; in-step linkage sets ``subagent_trajectory_ref`` on
        ``spawn_agent`` function_call_output observations."""
        return _build_steps(raw, traj.session_id, diagnostics)

    def _load_subagents(self, main: Trajectory, file_path: Path) -> list[Trajectory]:
        """Find spawned rollout files via SQLite; fall back to filesystem scan
        of parent content for ``codex exec`` mode where SQLite isn't written."""
        rollout_paths = _find_subagent_rollouts(main.session_id)
        if not rollout_paths:
            try:
                parent_content = file_path.read_text(encoding="utf-8")
            except OSError:
                return []
            rollout_paths = _find_subagent_rollouts_via_filesystem(parent_content)
        if not rollout_paths:
            return []
        out: list[Trajectory] = []
        for path in rollout_paths:
            sub = self._parse_trajectory(path)
            if sub is None:
                continue
            if sub.parent_trajectory_ref is None:
                # Confirm linkage from caller side when neither rollout source
                # nor forked_from_id was present.
                sub.parent_trajectory_ref = TrajectoryRef(session_id=main.session_id)
            out.append(sub)
        return out

    def parse_session_index(self, data_dir: Path) -> list[Trajectory]:
        """Build skeleton trajectories from Codex SQLite index.

        Reads ~/.codex/state_5.sqlite threads table for fast listing
        without parsing individual rollout files.

        Args:
            data_dir: Path to the Codex data directory (~/.codex).

        Returns:
            List of skeleton Trajectory objects (no steps).
        """
        db_path = data_dir / "state_5.sqlite"
        if not db_path.exists():
            return []

        trajectories: list[Trajectory] = []
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, rollout_path, created_at, source, cwd, "
                "title, tokens_used, model, first_user_message, cli_version "
                "FROM threads"
            )
            for row in cursor:
                traj = self._build_skeleton_from_row(row)
                if traj:
                    trajectories.append(traj)
            conn.close()
        except (sqlite3.Error, OSError) as exc:
            logger.warning("Failed to read Codex SQLite index: %s", exc)
            return []

        logger.info("Codex SQLite index: %d sessions", len(trajectories))
        return trajectories

    def _build_skeleton_from_row(self, row: sqlite3.Row) -> Trajectory | None:
        """Build a skeleton Trajectory from a SQLite threads row.

        Args:
            row: sqlite3.Row with columns from the threads table.

        Returns:
            Skeleton Trajectory, or None if row lacks a valid id.
        """
        session_id = row["id"]
        if not session_id:
            return None

        # Sub-agent threads carry a JSON source describing their parent.
        # We keep the row in the skeleton index but tag it with
        # ``parent_trajectory_ref`` so downstream listing logic can
        # filter sub-agents out of the main session list while still
        # resolving them when the parent is loaded.
        parent_thread_id = _extract_parent_thread_id(row["source"] or "")

        timestamp = normalize_timestamp(row["created_at"])
        agent = self.build_agent(version=row["cli_version"], model_name=row["model"])

        first_message = row["first_user_message"]
        if first_message:
            first_message = truncate_first_message(first_message)

        # Skeleton step so Trajectory validation passes (min_length=1)
        skeleton_step = Step(
            step_id="index-0",
            source=StepSource.USER,
            message=first_message or "",
            timestamp=timestamp,
        )

        tokens_used = row["tokens_used"] or 0
        final_metrics = FinalMetrics(
            total_prompt_tokens=tokens_used,
            total_completion_tokens=0,
            total_steps=0,
            tool_call_count=0,
            duration=0,
            total_cache_write_tokens=0,
            total_cache_read_tokens=0,
        )

        extra: dict = {"is_skeleton": True}
        if row["rollout_path"]:
            extra["rollout_path"] = row["rollout_path"]
        if row["source"]:
            extra["source"] = row["source"]
        if row["title"]:
            extra["title"] = row["title"]

        parent_ref = TrajectoryRef(session_id=parent_thread_id) if parent_thread_id else None

        return Trajectory(
            session_id=session_id,
            project_path=row["cwd"],
            timestamp=timestamp,
            first_message=first_message,
            agent=agent,
            steps=[skeleton_step],
            final_metrics=final_metrics,
            parent_trajectory_ref=parent_ref,
            extra=extra,
        )


def _scan_session_metadata(entries: list[dict]) -> _CodexSessionMeta:
    """Extract session metadata from a single pass over entries.

    Collects fields from:
    - ``session_meta.payload``: id, cli_version, cwd, source, originator
    - First ``turn_context.payload``: model, effort, sandbox_policy, approval_policy

    Args:
        entries: Parsed JSONL entries.

    Returns:
        Populated _CodexSessionMeta.
    """
    session_id: str | None = None
    cli_version: str | None = None
    model_name: str | None = None
    project_path: str | None = None
    source: str | None = None
    originator: str | None = None
    effort: str | None = None
    sandbox_policy: str | None = None
    approval_policy: str | None = None
    forked_from_id: str | None = None
    agent_role: str | None = None
    agent_nickname: str | None = None
    found_session_meta = False
    found_turn_context = False

    for entry in entries:
        entry_type = entry.get("type", "")
        payload = entry.get("payload", {})

        # Sub-agent rollouts contain two session_meta entries: the child
        # (this rollout) and the parent (forked-from context). Only use
        # the first one to avoid session_id collisions.
        if entry_type == "session_meta" and not found_session_meta:
            found_session_meta = True
            session_id = payload.get("id") or None
            cli_version = payload.get("cli_version") or None
            project_path = payload.get("cwd") or None
            source = payload.get("source") or None
            originator = payload.get("originator") or None
            forked_from_id = payload.get("forked_from_id") or None
            agent_role = payload.get("agent_role") or None
            agent_nickname = payload.get("agent_nickname") or None

        elif entry_type == "turn_context" and not found_turn_context:
            found_turn_context = True
            model_name = payload.get("model") or None
            effort = payload.get("reasoning_effort") or payload.get("effort") or None
            sandbox_policy = payload.get("sandbox") or payload.get("sandbox_policy") or None
            approval_policy = payload.get("approval_policy") or None

    return _CodexSessionMeta(
        session_id=session_id,
        cli_version=cli_version,
        model_name=model_name,
        project_path=project_path,
        source=source,
        originator=originator,
        effort=effort,
        sandbox_policy=sandbox_policy,
        approval_policy=approval_policy,
        forked_from_id=forked_from_id,
        agent_role=agent_role,
        agent_nickname=agent_nickname,
    )


def _strip_fork_prelude(entries: list[dict]) -> list[dict]:
    """Drop the inherited parent-history prefix from a fork-mode rollout.

    A Codex sub-agent spawned with ``fork_context: true`` writes the
    parent's full conversation into the child's rollout file, then a
    ``<model_switch>`` developer message marks where the child's own
    work begins. We keep the child's first ``session_meta`` entry
    (so id/cli_version extraction still works) and drop everything
    between it and the boundary.

    Returns ``entries`` unchanged when the rollout isn't a fork-mode
    child or the boundary marker is missing (degrade gracefully — at
    worst the listing still shows the parent's first prompt as the
    sub-agent's first_message, which is the pre-fix behaviour).
    """
    if not entries:
        return entries
    first = entries[0]
    if first.get("type") != "session_meta":
        return entries
    if not first.get("payload", {}).get("forked_from_id"):
        return entries
    for i in range(1, len(entries)):
        entry = entries[i]
        if entry.get("type") != "response_item":
            continue
        payload = entry.get("payload", {})
        if payload.get("type") != "message" or payload.get("role") != "developer":
            continue
        content = payload.get("content", [])
        text = ""
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text += block.get("text", "")
        elif isinstance(content, str):
            text = content
        if "<model_switch>" in text.lstrip()[:80]:
            return [entries[0]] + entries[i + 1 :]
    return entries


def _build_steps(
    entries: list[dict], session_id: str, diagnostics: DiagnosticsCollector | None = None
) -> list[Step]:
    """Build Step objects from rollout entries.

    Args:
        entries: Parsed JSON entries from rollout JSONL.
        session_id: Session identifier from session_meta.
        diagnostics: Optional collector for parse quality metrics.

    Returns:
        Ordered list of Step objects.
    """
    tool_outputs = _collect_tool_outputs(entries, diagnostics)
    steps: list[Step] = []
    state = _CodexParseState()

    for entry in entries:
        entry_type = entry.get("type", "")
        timestamp = parse_iso_timestamp(entry.get("timestamp"))
        payload = entry.get("payload", {})

        if entry_type == "turn_context":
            state.current_model = payload.get("model", state.current_model)
            state.current_cwd = payload.get("cwd", state.current_cwd)
            effort = payload.get("reasoning_effort") or payload.get("effort") or ""
            if effort:
                state.current_effort = effort
            continue

        if entry_type == "response_item":
            _handle_response_item(payload, timestamp, session_id, tool_outputs, steps, state)
            continue

        # token_count events carry per-turn usage stats from the OpenAI API;
        # attach to the most recent agent step for per-step accounting.
        if entry_type == "event_msg" and payload.get("type") == "token_count":
            metrics = _parse_token_count(payload)
            if metrics:
                _attach_metrics_to_last_agent(steps, metrics)

    # Flush any trailing tool calls / thinking from the last agent turn.
    _flush_pending(steps, state)
    return steps


def _handle_response_item(
    payload: dict,
    timestamp,
    session_id: str,
    tool_outputs: dict[str, dict],
    steps: list[Step],
    state: _CodexParseState,
) -> None:
    """Process a single response_item entry."""
    payload_type = payload.get("type", "")

    if payload_type == "message":
        role = payload.get("role", "")
        if role not in RELEVANT_ROLES:
            return
        # A new message boundary: flush any tool calls / thinking buffered
        # from the preceding agent turn before creating the next step.
        _flush_pending(steps, state)
        content_text = _extract_message_text(payload)
        source = ROLE_TO_SOURCE.get(role, StepSource.USER)
        # Reclassify agent-injected context (e.g. <environment_context>)
        # that arrives as role=user but is system boilerplate.
        if source == StepSource.USER and content_text.lstrip().startswith(
            _CODEX_SYSTEM_TAG_PREFIXES
        ):
            source = StepSource.SYSTEM
        extra = _build_step_extra(state) if role == "assistant" else None
        status = payload.get("status")
        if status and extra is not None:
            extra["status"] = status
        elif status:
            extra = {"status": status}
        steps.append(
            Step(
                step_id=str(uuid4()),
                source=source,
                message=content_text,
                model_name=(state.current_model or None) if role == "assistant" else None,
                timestamp=timestamp,
                extra=extra,
            )
        )

    elif payload_type in _TOOL_CALL_TYPES:
        call_id = payload.get("call_id", "")
        # custom_tool_call uses "input" for arguments, function_call uses "arguments"
        raw_args = payload.get("arguments", "") or payload.get("input", "")
        result = tool_outputs.get(call_id, {})
        state.pending_tools.append(
            ToolCall(
                tool_call_id=call_id,
                function_name=payload.get("name", "unknown"),
                arguments=parse_tool_arguments(raw_args),
            )
        )
        # Buffer observation result for the tool output
        if result:
            content = result.get("output")
            state.pending_obs_results.append(
                ObservationResult(
                    source_call_id=call_id,
                    content=content,
                    is_error=bool(result.get("is_error")),
                    extra=result.get("metadata"),
                    subagent_trajectory_ref=_extract_subagent_ref(payload.get("name", ""), content),
                )
            )

    elif payload_type == "reasoning":
        # Codex reasoning entries contain summary[].text blocks with the
        # model's chain-of-thought.  Deduplicate by content hash because
        # Codex streaming recovery can re-emit identical reasoning blocks.
        summary_items = payload.get("summary", [])
        for item in summary_items:
            if not isinstance(item, dict):
                continue
            text = item.get("text", "")
            if not text:
                continue
            # md5 is fine here — used as a content fingerprint for dedup,
            # not for any security or integrity claim.
            content_hash = hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()
            if content_hash not in state.thinking_seen:
                state.thinking_seen.add(content_hash)
                state.pending_thinking.append(text)


def _collect_tool_outputs(
    entries: list[dict], diagnostics: DiagnosticsCollector | None = None
) -> OrderedDict[str, dict]:
    """Build a bounded call_id -> result mapping from tool output entries.

    Handles both ``function_call_output`` and ``custom_tool_call_output``.
    Uses an OrderedDict bounded at MAX_TOOL_RESULT_CACHE entries.
    """
    outputs: OrderedDict[str, dict] = OrderedDict()
    for entry in entries:
        if entry.get("type") != "response_item":
            continue
        payload = entry.get("payload", {})
        if payload.get("type") not in _TOOL_OUTPUT_TYPES:
            continue
        call_id = payload.get("call_id", "")
        if call_id:
            raw_output = coerce_to_string(payload.get("output", ""))
            cleaned, has_error, metadata = _parse_structured_output(raw_output)
            outputs[call_id] = {
                "output": cleaned,
                "is_error": has_error,
                "metadata": metadata,
            }
            if len(outputs) > MAX_TOOL_RESULT_CACHE:
                outputs.popitem(last=False)
            if diagnostics:
                diagnostics.record_tool_result()
    return outputs


def _extract_final_token_usage(entries: list[dict]) -> dict | None:
    """Extract cumulative total_token_usage from the last token_count event.

    Codex includes a ``total_token_usage`` block in token_count events
    that represents the cumulative usage across the entire session.

    Args:
        entries: Parsed JSONL entries.

    Returns:
        The total_token_usage dict, or None if not found.
    """
    for entry in reversed(entries):
        if entry.get("type") != "event_msg":
            continue
        payload = entry.get("payload", {})
        if payload.get("type") != "token_count":
            continue
        # Codex sometimes writes ``info: null`` when a turn failed before
        # the usage block was produced; ``.get("info", {})`` returns None
        # in that case (key is present, value is None), so guard explicitly.
        info = payload.get("info") or {}
        total_usage = info.get("total_token_usage")
        if isinstance(total_usage, dict) and total_usage:
            return total_usage
    return None


def _extract_subagent_ref(function_name: str, output: str | None) -> list[TrajectoryRef] | None:
    """Extract a sub-agent trajectory reference from a ``spawn_agent`` output.

    Codex's ``spawn_agent`` tool returns JSON like
    ``{"agent_id": "<child-thread-id>", "nickname": "..."}`` where
    ``agent_id`` matches the spawned child rollout's ``session_meta.id``.
    Setting :class:`ObservationResult.subagent_trajectory_ref` here lets
    the UI navigate parent → child the same way Claude does.
    """
    if function_name != _SPAWN_AGENT_TOOL_NAME or not isinstance(output, str) or not output:
        return None
    try:
        parsed = orjson.loads(output)
    except orjson.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    agent_id = parsed.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        return None
    return [TrajectoryRef(session_id=agent_id)]


def _find_subagent_rollouts(parent_id: str) -> list[Path]:
    """Return rollout paths for sub-agents directly spawned from ``parent_id``.

    Reads ``~/.codex/state_5.sqlite`` because Codex doesn't write the
    parent → child link into the rollout files for fresh
    (``fork_context=false``) spawns. A LIKE query against the source
    column is fast enough on a few-thousand-row threads table — the
    column is opaque JSON, so we can't index on the embedded id.
    """
    db_path = Path.home() / ".codex" / "state_5.sqlite"
    if not db_path.is_file():
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        # ``LIKE`` with a parameterised string is bind-safe; the JSON
        # subkey we match on is a stable Codex constant, not user input.
        cursor = conn.execute(
            "SELECT rollout_path FROM threads WHERE source LIKE ?",
            (f'%"parent_thread_id":"{parent_id}"%',),
        )
        rows = [row[0] for row in cursor if row[0]]
        conn.close()
    except sqlite3.Error as exc:
        logger.debug("state_5.sqlite sub-agent lookup failed for %s: %s", parent_id, exc)
        return []
    return [Path(p) for p in rows if Path(p).is_file()]


def _find_subagent_rollouts_via_filesystem(parent_content: str) -> list[Path]:
    """Locate sub-agent rollout files by scanning the parent's spawn_agent outputs.

    Used when SQLite has no matching rows (``codex exec`` mode). For
    each ``spawn_agent`` ``function_call_output`` whose JSON carries
    an ``agent_id``, we look for a rollout whose filename ends with
    ``-<agent_id>.jsonl`` under ``~/.codex/sessions/``.

    The rglob is bounded by the small total number of rollout files
    (typically a few hundred); we stop after the first match per
    agent_id.
    """
    sessions_dir = Path.home() / ".codex" / "sessions"
    if not sessions_dir.is_dir():
        return []
    agent_ids: set[str] = set()
    for line in parent_content.splitlines():
        # Cheap pre-filter to skip the vast majority of lines. The bytes
        # form sees the JSON-escaped key (``\"agent_id\"``) the same way
        # as a plain substring search would in the un-escaped source —
        # ``agent_id`` as a bare substring is unique enough to gate.
        if "agent_id" not in line:
            continue
        try:
            entry = orjson.loads(line)
        except orjson.JSONDecodeError:
            continue
        payload = entry.get("payload", {}) if isinstance(entry, dict) else {}
        if payload.get("type") != "function_call_output":
            continue
        output = payload.get("output", "")
        if not isinstance(output, str):
            continue
        try:
            parsed_output = orjson.loads(output)
        except orjson.JSONDecodeError:
            continue
        if not isinstance(parsed_output, dict):
            continue
        agent_id = parsed_output.get("agent_id")
        if isinstance(agent_id, str) and agent_id:
            agent_ids.add(agent_id)
    paths: list[Path] = []
    for agent_id in agent_ids:
        for match in sessions_dir.rglob(f"*-{agent_id}.jsonl"):
            paths.append(match)
            break
    return paths


def _parent_id_from_source(source: object) -> str | None:
    """Pull ``parent_thread_id`` from a parsed source object.

    The same shape appears in two places: the rollout's
    ``session_meta.payload.source`` (already a dict when present) and
    the SQLite ``threads.source`` column (a JSON string). This helper
    normalises both — ``_extract_parent_thread_id`` decodes the string
    and forwards here.
    """
    if not isinstance(source, dict):
        return None
    spawn = source.get("subagent", {}).get("thread_spawn", {})
    if not isinstance(spawn, dict):
        return None
    parent = spawn.get("parent_thread_id")
    return parent if isinstance(parent, str) and parent else None


def _build_session_extra(meta: _CodexSessionMeta) -> dict | None:
    """Build trajectory-level extra dict from session metadata.

    Args:
        meta: Scanned session metadata.

    Returns:
        Dict with non-None metadata fields, or None if all empty.
    """
    pairs = [
        ("source", meta.source),
        ("originator", meta.originator),
        ("reasoning_effort", meta.effort),
        ("sandbox_policy", meta.sandbox_policy),
        ("approval_policy", meta.approval_policy),
        ("agent_role", meta.agent_role),
        ("agent_nickname", meta.agent_nickname),
    ]
    extra = {k: v for k, v in pairs if v}
    return extra or None


def _build_step_extra(state: _CodexParseState) -> dict | None:
    """Build step-level extra dict from current parse state.

    Args:
        state: Current parse state with cwd and effort.

    Returns:
        Dict with non-empty fields, or None if all empty.
    """
    extra: dict = {}
    if state.current_cwd:
        extra["cwd"] = state.current_cwd
    if state.current_effort:
        extra["reasoning_effort"] = state.current_effort
    return extra or None


def _flush_pending(steps: list[Step], state: _CodexParseState) -> None:
    """Attach pending tool calls, observations, and thinking to the last agent step."""
    if not state.pending_tools and not state.pending_thinking:
        return
    for step in reversed(steps):
        if step.source == StepSource.AGENT:
            if state.pending_tools:
                step.tool_calls.extend(state.pending_tools)
            if state.pending_obs_results:
                if step.observation is None:
                    step.observation = Observation(results=[])
                step.observation.results.extend(state.pending_obs_results)
            if state.pending_thinking:
                existing = step.reasoning_content or ""
                new_thinking = "\n".join(state.pending_thinking)
                step.reasoning_content = (
                    f"{existing}\n{new_thinking}".strip() if existing else new_thinking
                )
            break
    state.pending_tools.clear()
    state.pending_obs_results.clear()
    state.pending_thinking.clear()


def _attach_metrics_to_last_agent(steps: list[Step], metrics: Metrics) -> None:
    """Attach token metrics to the last agent step lacking metrics data."""
    for step in reversed(steps):
        if step.source == StepSource.AGENT and not step.metrics:
            step.metrics = metrics
            return


def _extract_message_text(payload: dict) -> str:
    """Extract plain text from a response_item message payload.

    Codex uses ``input_text`` for user messages and ``output_text`` for
    assistant messages (following the OpenAI Responses API content types).
    """
    content = payload.get("content", [])
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return coerce_to_string(content)
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") in ("input_text", "output_text"):
            text = block.get("text", "")
            if text:
                parts.append(text)
    return "\n".join(parts)


def _parse_structured_output(raw: str) -> tuple[str, bool, dict | None]:
    """Parse Codex structured tool output, stripping metadata prefix.

    Args:
        raw: Raw tool output string.

    Returns:
        Tuple of (cleaned_output, is_error, metadata).
        metadata contains exit_code and wall_time_sec when the prefix is present.
    """
    if not raw:
        return "", False, None
    match = _OUTPUT_PREFIX_RE.match(raw)
    if not match:
        return raw, False, None
    exit_code = int(match.group(1))
    wall_time_sec = float(match.group(2))
    cleaned = raw[match.end() :]
    metadata = {"exit_code": exit_code, "wall_time_sec": wall_time_sec}
    return cleaned, exit_code != 0, metadata


def _parse_token_count(payload: dict) -> Metrics | None:
    """Parse a Codex token_count event_msg payload into ``Metrics``.

    Per-turn usage is nested under ``info.last_token_usage``; falls back
    to the top-level ``info`` fields for older formats. Accepts both old
    (``prompt_tokens``/``completion_tokens``) and new
    (``input_tokens``/``output_tokens``) field names.
    """
    info = payload.get("info", {})
    if not info:
        return None

    usage = info.get("last_token_usage") or info

    input_tokens = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0)
    output_tokens = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)
    cache_read_tokens = usage.get("cached_input_tokens", 0)
    if not cache_read_tokens:
        cache_read_tokens = (usage.get("input_tokens_details") or {}).get("cache_read_tokens", 0)

    if input_tokens + cache_read_tokens == 0 and output_tokens == 0:
        return None

    reasoning = usage.get("reasoning_output_tokens", 0)
    extra = {"reasoning_output_tokens": reasoning} if reasoning else None

    return Metrics.from_tokens(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        extra=extra,
    )


def _extract_parent_thread_id(source_val: str) -> str | None:
    """Pull ``parent_thread_id`` out of a Codex thread's source JSON.

    Returns None when the source is empty, not JSON, or doesn't
    describe a sub-agent. Catches malformed JSON quietly because the
    column is opaque to us — better to lose linkage than reject
    a row.
    """
    if not source_val or not source_val.startswith("{") or "subagent" not in source_val:
        return None
    try:
        source_obj = orjson.loads(source_val)
    except orjson.JSONDecodeError:
        return None
    return _parent_id_from_source(source_obj)
