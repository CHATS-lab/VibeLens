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
  - Sub-agent sessions in older Gemini builds share the same ``sessionId``
    but live in separate files with ``kind: "subagent"``. Newer builds
    surface ``codebase_investigator``-style sub-agent calls inline as a
    ``toolCalls`` entry whose ``result.functionResponse.response.output``
    is the only record of the child run — see capability notes below.

User-message content array carries mixed parts: ``{text}`` for plain
text and ``{inlineData: {mimeType, data}}`` for pasted/attached images.

Capability vs Claude reference parser:
  - text content                  ✓
  - images (user inlineData)      ✓ (this revision)
  - reasoning content             ✓ (``thoughts[]``)
  - tool calls + observations     ✓
  - sub-agents (separate file)    ✓ legacy ``kind: subagent`` files
  - sub-agents (inline output)    ✓ ``codebase_investigator``-style tool
                                    calls whose ``functionResponse.output``
                                    holds the full sub-agent report. We
                                    synthesise a 2-step child Trajectory
                                    (objective + report) so the UI can
                                    navigate to it. The child's own steps
                                    aren't recoverable — Gemini doesn't
                                    persist them — so the synthetic shape
                                    is the best we can do without a wire
                                    format change upstream.
  - compaction (``/compress``)    ✓ Detected via ``logs.json`` cross-reference;
                                    splice a SYSTEM marker step at the
                                    timestamp.
  - persistent output files       ✗ Gemini doesn't split large tool output.
  - continuation refs             ✗ Gemini has no resume-from-prior workflow
                                    comparable to Claude's continuation chain.
"""

import hashlib
import json
from collections import Counter
from os.path import commonpath
from pathlib import Path

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import BaseParser
from vibelens.ingest.parsers.helpers import (
    attach_subagent_ref,
    build_multimodal_message,
    make_compaction_step,
)
from vibelens.models.enums import AgentType, ContentType, StepSource
from vibelens.models.trajectories import (
    Agent,
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
    TrajectoryRef,
)
from vibelens.models.trajectories.content import Base64Source, ContentPart
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

# Default local data root. Used as ``LOCAL_DATA_DIR`` *and* as the
# fallback when resolving projectHash for sessions outside ~/.gemini/
# (e.g. archived session files copied elsewhere).
GEMINI_DATA_DIR = Path.home() / ".gemini"

# Tool-call argument keys we probe when inferring a project path from
# on-disk paths the agent actually touched.
_PATH_ARG_KEYS = {"file_path", "path", "filename", "directory"}

# Reject paths shallower than this when inferring from tool args —
# paths like "/" or "/Users" are not meaningful project roots.
_MIN_PATH_DEPTH = 3

# Value of the chat-file ``kind`` field that marks a sub-agent rollout.
_KIND_SUBAGENT = "subagent"

# Tool names whose ``functionResponse.response.output`` is a sub-agent's
# summary report. Newer Gemini builds dispatch sub-agents through these tools
# and never persist the child conversation as a separate file. We synthesise a
# minimal child Trajectory from the summary so the UI can navigate to it.
_INLINE_SUBAGENT_TOOL_NAMES = frozenset({"codebase_investigator"})

# Gemini's dedicated skill-activation tool. Activation only — reading SKILL.md
# via run_shell_command/read_file does not count.
_SKILL_TOOL_NAMES: frozenset[str] = frozenset({"activate_skill"})


class GeminiParser(BaseParser):
    """Parser for Gemini CLI's native session JSON format.

    Handles session JSON files with user and gemini messages,
    embedded tool calls, and structured thinking process.
    """

    AGENT_TYPE = AgentType.GEMINI
    LOCAL_DATA_DIR: Path | None = GEMINI_DATA_DIR
    # Filenames embed only the first 8 chars of the canonical UUID; the real
    # session_id lives in the file's top-level ``sessionId`` field. We read it
    # in ``_namespace_session_id`` so default ``discover_sessions`` produces
    # the same id ``parse()`` will set on the trajectory.
    NAMESPACE_SESSION_IDS = False

    def discover_session_files(self, data_dir: Path) -> list[Path]:
        """Find Gemini session files inside chats/ directories."""
        return sorted(f for f in data_dir.rglob("session-*.json") if "chats" in f.parts)

    def _namespace_session_id(self, file_path: Path) -> str:
        """Read the session's canonical id from the JSON's ``sessionId`` field.

        Sub-agent files share the parent's ``sessionId`` on disk, so we
        return the filename stem for them — matching what ``_extract_metadata``
        does in stage 2.
        """
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return file_path.stem
        if not isinstance(data, dict):
            return file_path.stem
        if data.get("kind", "main") == _KIND_SUBAGENT:
            return file_path.stem
        return data.get("sessionId") or file_path.stem

    # ---- 4-stage parsing ----
    def _decode_file(self, file_path: Path, diagnostics: DiagnosticsCollector) -> dict | None:
        """Stage 1: read + JSON-parse the chat file."""
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.debug("Invalid JSON in Gemini session %s", file_path)
            return None
        if not isinstance(data, dict):
            return None
        diagnostics.total_lines = len(data.get("messages", []) or [])
        return data

    def _extract_metadata(
        self, raw: dict, file_path: Path, diagnostics: DiagnosticsCollector
    ) -> Trajectory | None:
        """Stage 2: identity + parent linkage. Sub-agent files (``kind: subagent``)
        get a synthetic session id from the filename stem to avoid colliding with
        the main's ``sessionId`` (which they share verbatim)."""
        original_sid = raw.get("sessionId")
        if not original_sid:
            return None
        if raw.get("kind", "main") == _KIND_SUBAGENT:
            session_id = file_path.stem
            parent_ref = TrajectoryRef(session_id=original_sid)
        else:
            session_id = original_sid
            parent_ref = None
        return Trajectory(
            session_id=session_id,
            agent=self.build_agent(),  # model filled in stage 3
            parent_trajectory_ref=parent_ref,
        )

    def _build_steps(
        self, raw: dict, traj: Trajectory, file_path: Path, diagnostics: DiagnosticsCollector
    ) -> list[Step]:
        """Stage 3: build steps + backfill model + project path (both depend on steps)."""
        steps = _build_steps(raw.get("messages", []), traj.session_id)
        # Splice synthetic compaction boundaries derived from the per-project
        # logs.json. Gemini's /compress slash command rewrites the in-memory
        # history in-place — the chat JSON only ever holds the post-compression
        # state — so we infer compaction events from the slash-command log.
        steps = _splice_compaction_markers(steps, raw, file_path)
        diagnostics.parsed_lines = len(steps)
        if not steps:
            return []
        # Gemini has no session-level model; take the most recent step model
        # so downstream pricing lookup matches.
        traj.agent.model_name = next((s.model_name for s in reversed(steps) if s.model_name), None)
        traj.project_path = _resolve_project(file_path, raw, steps)
        return steps

    def _load_subagents(self, main: Trajectory, file_path: Path) -> list[Trajectory]:
        """Combine sibling-file sub-agents and inline tool-result sub-agents.

        Two sources contribute to children:

        1. Legacy sibling files (``kind: subagent`` chat JSONs in the same
           ``chats/`` dir whose ``sessionId`` matches the main's) — full
           Trajectories with their own Steps.
        2. Inline summaries (e.g. ``codebase_investigator`` tool calls whose
           ``functionResponse.response.output`` carries the entire child
           report as text). Newer Gemini builds never persist the child's
           own events, so we synthesise a 2-step Trajectory containing the
           objective and the summary so the UI can still navigate down.
        """
        subs = self._load_sibling_subagents(main, file_path)
        subs.extend(self._load_inline_subagents(main, file_path))
        return subs

    def _load_sibling_subagents(self, main: Trajectory, file_path: Path) -> list[Trajectory]:
        """Load chats/ siblings tagged ``kind: subagent`` for legacy Gemini builds."""
        chats_dir = file_path.parent
        if chats_dir.name != "chats" or not chats_dir.is_dir():
            return []
        subs: list[Trajectory] = []
        for sibling in sorted(chats_dir.iterdir()):
            if sibling == file_path or not sibling.is_file():
                continue
            if not (sibling.name.startswith("session-") and sibling.suffix == ".json"):
                continue
            try:
                data = json.loads(sibling.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("kind") != _KIND_SUBAGENT or data.get("sessionId") != main.session_id:
                continue
            sub = self._parse_decoded(data, sibling)
            if sub is not None:
                subs.append(sub)
        return subs

    def _load_inline_subagents(self, main: Trajectory, file_path: Path) -> list[Trajectory]:
        """Synthesise child trajectories from inline ``codebase_investigator``-style tools.

        We re-walk the parent's parsed Steps because the spawning ToolCall
        already carries arguments + result text, and we need to wire each
        synthetic child back to its spawning tool call via
        ``subagent_trajectory_ref`` for UI navigation.
        """
        subs: list[Trajectory] = []
        for step in main.steps:
            if step.observation is None:
                continue
            for tool_call, obs_result in zip(
                step.tool_calls or [], step.observation.results, strict=False
            ):
                if tool_call.function_name not in _INLINE_SUBAGENT_TOOL_NAMES:
                    continue
                sub = _build_inline_subagent(
                    main_session_id=main.session_id,
                    tool_call=tool_call,
                    obs_result=obs_result,
                    main_model=main.agent.model_name if main.agent else None,
                    parent_step_timestamp=step.timestamp,
                )
                if sub is None:
                    continue
                attach_subagent_ref(main.steps, tool_call.tool_call_id, sub.session_id)
                subs.append(sub)
        return subs

    def _parse_decoded(self, data: dict, file_path: Path) -> Trajectory | None:
        """Run stages 2-4 on a pre-decoded chat dict (skips the file re-read).

        Mirrors ``BaseParser._parse_trajectory`` but starts from data that
        ``_load_subagents`` already loaded for its sibling-filter check.
        """
        diagnostics = DiagnosticsCollector()
        diagnostics.total_lines = len(data.get("messages", []) or [])
        traj = self._extract_metadata(data, file_path, diagnostics)
        if traj is None:
            return None
        traj.steps = self._build_steps(data, traj, file_path, diagnostics)
        if not traj.steps:
            return None
        return self._finalize(traj, diagnostics)


def _build_inline_subagent(
    main_session_id: str,
    tool_call: ToolCall,
    obs_result: ObservationResult,
    main_model: str | None,
    parent_step_timestamp,
) -> Trajectory | None:
    """Construct a 2-step Trajectory from an inline sub-agent tool call.

    The objective comes from the ToolCall's arguments; the report text comes
    from the spawning tool's observation content. No timestamps are recorded
    by Gemini for either, so we reuse the parent step's timestamp for both.
    Returns ``None`` when the report text is missing — without it the child
    has nothing meaningful to display.
    """
    report_text = (obs_result.content or "").strip()
    if not report_text:
        return None

    args = tool_call.arguments if isinstance(tool_call.arguments, dict) else {}
    objective = args.get("objective") or (
        f"(spawned via {tool_call.function_name}; objective not recorded by Gemini)"
    )

    sub_session_id = (
        f"{main_session_id}:subagent:{tool_call.tool_call_id or tool_call.function_name}"
    )
    steps = [
        Step(
            step_id=f"{sub_session_id}-objective",
            source=StepSource.USER,
            message=objective,
            timestamp=parent_step_timestamp,
        ),
        Step(
            step_id=f"{sub_session_id}-result",
            source=StepSource.AGENT,
            message=report_text,
            timestamp=parent_step_timestamp,
        ),
    ]
    return Trajectory(
        session_id=sub_session_id,
        agent=Agent(name=AgentType.GEMINI.value, model_name=main_model),
        parent_trajectory_ref=TrajectoryRef(session_id=main_session_id),
        steps=steps,
        extra={
            "agent_role": tool_call.function_name,
            "spawn_tool_call_id": tool_call.tool_call_id,
            "synthesized_inline": True,
        },
    )


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
                    message=_build_user_message(raw),
                    timestamp=timestamp,
                )
            )
        elif msg_type == "gemini":
            content = raw.get("content", "")
            thinking = _extract_thinking(raw)
            # Gemini sometimes produces only thoughts with empty content
            message = content or (thinking or "")
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


def _splice_compaction_markers(steps: list[Step], raw: dict, file_path: Path) -> list[Step]:
    """Insert synthetic SYSTEM compaction steps based on ``logs.json``.

    Gemini CLI logs each user-typed slash command (``/compress``, ``/quit``,
    etc.) to ``~/.gemini/tmp/<project>/logs.json``. The compression itself
    rewrites the in-memory message list and the next persisted save replaces
    the older content with a summarised version — so the chat JSON we read
    only ever shows the post-compression state. We can still tell that a
    ``/compress`` happened by cross-referencing the logs file and inserting
    a marker step at the point where the last pre-compression message would
    have been.

    No-ops when ``logs.json`` is absent or carries no ``/compress`` entries
    inside this session's ``[startTime, lastUpdated]`` window.
    """
    logs_path = file_path.parent.parent / "logs.json"
    if not logs_path.is_file():
        return steps
    try:
        log_entries = json.loads(logs_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return steps
    if not isinstance(log_entries, list):
        return steps

    session_start = raw.get("startTime")
    session_end = raw.get("lastUpdated")
    if not session_start or not session_end:
        return steps

    boundaries: list[Step] = []
    for entry in log_entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") != "user":
            continue
        message = entry.get("message") or ""
        if message.strip() != "/compress":
            continue
        ts = entry.get("timestamp")
        if not ts or not (session_start <= ts <= session_end):
            continue
        boundaries.append(
            make_compaction_step(
                step_id=f"gemini-compress-{ts}",
                timestamp=parse_iso_timestamp(ts),
                message="[Context compressed via /compress]",
            )
        )
    if not boundaries:
        return steps

    # Splice each boundary at the position matching its timestamp.
    merged: list[Step] = []
    boundary_iter = iter(boundaries)
    next_boundary = next(boundary_iter, None)
    for step in steps:
        while next_boundary is not None and (
            step.timestamp is None
            or (next_boundary.timestamp is not None and step.timestamp >= next_boundary.timestamp)
        ):
            merged.append(next_boundary)
            next_boundary = next(boundary_iter, None)
        merged.append(step)
    while next_boundary is not None:
        merged.append(next_boundary)
        next_boundary = next(boundary_iter, None)
    return merged


def _resolve_project(file_path: Path, data: dict, steps: list[Step]) -> str:
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
    if project_hash and GEMINI_DATA_DIR.is_dir():
        result = resolve_project_path(project_hash, GEMINI_DATA_DIR, steps)
        if result and result != project_hash:
            return result

    # Strategy 3: infer from tool call file paths
    if steps:
        result = _infer_project_from_tool_args(steps)
        if result:
            return result

    return ""


def resolve_project_path(hash_dir: str, gemini_dir: Path, steps: list[Step] | None = None) -> str:
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
                is_skill=True if tool_name in _SKILL_TOOL_NAMES else None,
            )
        )
        obs_results.append(
            ObservationResult(
                source_call_id=tc_id,
                content=_extract_tool_output(tool.get("result", [])),
                is_error=tool.get("status") == "error",
            )
        )

    observation = Observation(results=obs_results) if obs_results else None
    return calls, observation


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
    # Current format: {projects: {path: hash_or_dirname}}
    projects_map = projects_data.get("projects", {})
    if isinstance(projects_map, dict):
        for project_path, project_hash in projects_map.items():
            if project_hash == hash_dir:
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

    directories = [
        p.rstrip("/") if p.endswith("/") else str(Path(p).parent) for p in absolute_paths
    ]
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


def _build_user_message(raw: dict) -> str | list[ContentPart]:
    """Convert a Gemini user message into either plain text or multimodal parts.

    Gemini stores attached images inline as ``{"inlineData": {"mimeType": ...,
    "data": "<base64>"}}`` content parts alongside text parts. When images are
    present we return a ``list[ContentPart]`` so the renderer can show both;
    pure-text messages stay as a string for backward compatibility.
    """
    content = raw.get("content")
    if not isinstance(content, list):
        return coerce_to_string(content)

    text_chunks: list[str] = []
    images: list[ContentPart] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if "inlineData" in part:
            inline = part.get("inlineData") or {}
            mime = inline.get("mimeType") or "application/octet-stream"
            payload = inline.get("data") or ""
            if not mime.startswith("image/") or not payload:
                continue
            images.append(
                ContentPart(
                    type=ContentType.IMAGE,
                    source=Base64Source(media_type=mime, base64=payload),
                )
            )
        elif "text" in part:
            text = part.get("text") or ""
            if text:
                text_chunks.append(text)

    return build_multimodal_message("\n".join(text_chunks), images)


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
    """Parse Gemini CLI token statistics into ``Metrics``.

    Gemini reports ``input`` already including any cached portion, so
    we don't add ``cached`` into ``prompt_tokens`` (unlike the
    Anthropic-style :meth:`Metrics.from_tokens`).
    """
    if not tokens:
        return None
    return Metrics(
        prompt_tokens=tokens.get("input", 0),
        completion_tokens=tokens.get("output", 0),
        cache_read_tokens=tokens.get("cached", 0),
    )


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
