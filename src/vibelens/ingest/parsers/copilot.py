"""GitHub Copilot CLI session parser.

Each session lives at ``~/.copilot/session-state/<uuid>/events.jsonl`` plus a
sibling ``workspace.yaml`` carrying static metadata. The JSONL stream is the
primary source.

Each event has the envelope ``{type, data, id, timestamp, parentId, agentId?}``.
``agentId`` is set on every event the spawned sub-agent emits; events with no
``agentId`` belong to the main session. Event types observed:

  session.start            sessionId, copilotVersion, context.{cwd, gitRoot,
                           branch, headCommit, repository, hostType,
                           repositoryHost}
  session.model_change     newModel, reasoningEffort
  session.plan_changed     operation marker — drop
  session.shutdown         shutdownType, modelMetrics.<model>.{requests, usage},
                           codeChanges, currentModel, *Tokens, totalApiDurationMs,
                           totalPremiumRequests, sessionStartTime
  system.message           role, content — drop (system prompt)
  user.message             content (raw user-typed), transformedContent,
                           attachments[].{type, path, displayName}, interactionId
  assistant.message        messageId, content, toolRequests[].{toolCallId, name,
                           arguments, intentionSummary?, toolTitle?}, outputTokens,
                           reasoningOpaque (encrypted), encryptedContent, requestId
  assistant.turn_start/end bookkeeping — drop
  tool.execution_start     toolCallId, toolName, arguments
  tool.execution_complete  toolCallId, model, success, result.{content, detailedContent},
                           toolTelemetry
  subagent.started         toolCallId, agentName, agentDisplayName, agentDescription
  subagent.completed       toolCallId, model, totalToolCalls, totalTokens, durationMs
  system.notification      sub-agent completion broadcast — non-conversational

Sub-agents: every event the sub-agent emits carries ``agentId`` matching the
spawning ``toolCallId``. We split events by ``agentId`` and parse each group as
a child Trajectory linked to the main via ``parent_trajectory_ref``. The
spawning ToolCall's observation gets a ``subagent_trajectory_ref`` so the UI
can navigate from the parent's tool call into the child session.

Images: ``user.message.attachments`` carries paths to clipboard/file images
under ``/var/folders/.../copilot-image-*.png``. We read those bytes and encode
them as inline ``ContentPart`` so the UI can render them. When the file has
been removed (e.g. system tmp cleanup), the text-only placeholder
``[📷 <name>]`` already in ``content`` keeps the message readable.

Capability vs Claude reference parser:
  - text content                ✓
  - images (user attachments)   ✓ (this revision)
  - reasoning content           ✗ ``reasoningOpaque`` is encrypted by Copilot
                                  and only ``outputTokens`` is exposed; nothing
                                  decodable to surface. Future work: re-evaluate
                                  if Copilot exposes a plaintext field.
  - sub-agents (full transcript)✓ (this revision; depth 1)
  - sub-agent depth >1          // TODO(copilot-nested): the agentId field
                                  is flat; nested spawns would need a parent-of
                                  link. Not seen in observed data.
  - compaction events           ✓ ``session.compaction_complete`` carries
                                  ``summaryContent`` — surfaced as a SYSTEM
                                  step so the post-compaction context is
                                  visible. ``session.truncation`` is also
                                  surfaced with token/message removal stats.
  - persistent output files     ✗ Copilot does not split large tool outputs.
  - continuation refs           ✗ Copilot has no "resume from prior session"
                                  workflow comparable to Claude's.
  - skill output filtering      n/a Copilot has no Skill tool.

Future work:
  // TODO(copilot-plan): ingest plan.md alongside events.jsonl when ATIF gains
     a slot for agent-authored plans.
"""

import base64
import mimetypes
from pathlib import Path
from typing import Any

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import BaseParser
from vibelens.ingest.parsers.helpers import (
    attach_subagent_ref,
    build_multimodal_message,
    iter_jsonl_safe,
)
from vibelens.models.enums import AgentType, ContentType, StepSource
from vibelens.models.trajectories import (
    Agent,
    DailyBucket,
    FinalMetrics,
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
    TrajectoryRef,
)
from vibelens.models.trajectories.content import Base64Source, ContentPart
from vibelens.utils import deterministic_id, get_logger, parse_iso_timestamp
from vibelens.utils.timestamps import local_date_key

logger = get_logger(__name__)

# Event types we drop without warning — bookkeeping or non-conversational.
_DROP_EVENT_TYPES = frozenset(
    {
        "system.message",
        "session.start",  # already consumed in _extract_metadata
        "session.plan_changed",
        "assistant.turn_start",
        "assistant.turn_end",
        "tool.execution_start",
        "tool.execution_complete",
        "subagent.started",  # pre-scanned
        "subagent.completed",  # pre-scanned
        "system.notification",  # surfaces sub-agent completion only
        "session.compaction_start",  # paired with compaction_complete; that's where the data is
        "session.context_changed",  # post-compaction cwd/branch refresh, no chat content
    }
)

# Tools that spawn Copilot sub-agents.
_SUBAGENT_SPAWN_TOOLS = frozenset({"task"})

# Cap for inlined image bytes. Copilot's clipboard images are typically <2MB;
# anything larger almost certainly isn't an image and we'd rather skip than
# bloat the trajectory payload.
_MAX_IMAGE_BYTES = 8 * 1024 * 1024


class CopilotParser(BaseParser):
    """Parser for GitHub Copilot CLI's events.jsonl format."""

    AGENT_TYPE = AgentType.COPILOT
    LOCAL_DATA_DIR: Path | None = Path.home() / ".copilot"
    # File stem is always "events"; the canonical session_id is the parent
    # directory's UUID, set explicitly via ``_namespace_session_id``.
    NAMESPACE_SESSION_IDS = False

    def discover_session_files(self, data_dir: Path) -> list[Path]:
        """Scan ``session-state/<uuid>/events.jsonl`` files."""
        sessions_root = data_dir / "session-state"
        if not sessions_root.is_dir():
            return []
        return sorted(
            session_dir / "events.jsonl"
            for session_dir in sessions_root.iterdir()
            if session_dir.is_dir() and (session_dir / "events.jsonl").is_file()
        )

    def _namespace_session_id(self, file_path: Path) -> str:
        """Return the parent directory name — Copilot stores one session per dir."""
        return file_path.parent.name

    def _decode_file(self, file_path: Path, diagnostics: DiagnosticsCollector) -> list[dict] | None:
        """Read events.jsonl into a list of decoded events."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read %s: %s", file_path, exc)
            return None
        events = list(iter_jsonl_safe(content, diagnostics=diagnostics))
        return events or None

    def _extract_metadata(
        self, raw: list[dict], file_path: Path, diagnostics: DiagnosticsCollector
    ) -> Trajectory | None:
        """Build a Trajectory header from the session.start event."""
        session_start = next((e for e in raw if e.get("type") == "session.start"), None)
        data = (session_start or {}).get("data") or {}
        context = data.get("context") or {}
        cli_version = data.get("copilotVersion")
        extra = {
            k: v
            for k, v in (
                ("cli_version", cli_version),
                ("producer", data.get("producer")),
                ("head_commit", context.get("headCommit")),
                ("host_type", context.get("hostType")),
                ("repository", context.get("repository")),
                ("repository_host", context.get("repositoryHost")),
                ("git_branch", context.get("branch")),
            )
            if v is not None
        }
        return Trajectory(
            session_id=data.get("sessionId") or file_path.parent.name,
            agent=self.build_agent(version=cli_version),
            project_path=context.get("cwd"),
            extra=extra or None,
        )

    def _build_steps(
        self, raw: list[dict], traj: Trajectory, file_path: Path, diagnostics: DiagnosticsCollector
    ) -> list[Step]:
        """Walk parent-only events in order; build USER/AGENT Steps with paired tool calls.

        Events tagged with ``agentId`` belong to a sub-agent and are picked up
        in :meth:`_load_subagents`. Tool execution completes are indexed
        across the full event stream so a parent ToolCall can reach its
        completion event even though they share a ``toolCallId`` namespace.
        """
        parent_events = [e for e in raw if not e.get("agentId")]
        by_call_id = lambda d: d.get("toolCallId")  # noqa: E731
        complete_by_call_id = _index_events(raw, "tool.execution_complete", by_call_id)
        subagent_started = _index_events(raw, "subagent.started", by_call_id)
        subagent_completed = _index_events(raw, "subagent.completed", by_call_id)

        current_model: str | None = None
        current_reasoning_effort: str | None = None
        steps: list[Step] = []

        for event in parent_events:
            event_type = event.get("type")
            data = event.get("data") or {}

            if event_type == "session.model_change":
                current_model = data.get("newModel") or current_model
                current_reasoning_effort = data.get("reasoningEffort") or current_reasoning_effort
                continue

            if event_type == "session.shutdown":
                _attach_shutdown_summary(traj, data)
                continue

            if event_type == "session.compaction_complete":
                # Carries ``summaryContent`` — the rewritten conversation
                # context we'd otherwise lose. Surface it as a SYSTEM step
                # so the user can read what the post-compaction history
                # contained.
                step = _build_compaction_step(event, data)
                if step is not None:
                    steps.append(step)
                continue

            if event_type == "session.truncation":
                # Hard truncation event with token/message counts; preserve
                # as a SYSTEM step so the dashboard can show how aggressive
                # the truncation was.
                steps.append(_build_truncation_step(event, data))
                continue

            if event_type == "user.message":
                steps.append(_build_user_step(event, data))
                continue

            if event_type == "assistant.message":
                step = _build_assistant_step(
                    event,
                    data,
                    complete_by_call_id,
                    subagent_started,
                    subagent_completed,
                    current_model,
                    current_reasoning_effort,
                    diagnostics,
                )
                if step is not None:
                    steps.append(step)
                continue

            if event_type in _DROP_EVENT_TYPES:
                continue

            diagnostics.record_skip(f"unknown copilot event type {event_type!r}")

        if current_model and traj.agent.model_name is None:
            traj.agent.model_name = current_model

        # Build final_metrics from session-level model_metrics. Copilot doesn't
        # emit per-message input tokens, so the BaseParser per-step rollup
        # would understate prompt/cache totals.
        model_metrics = (traj.extra or {}).get("model_metrics")
        if model_metrics:
            traj.final_metrics = _aggregate_session_metrics(model_metrics, steps)

        return steps

    def _load_subagents(self, main: Trajectory, file_path: Path) -> list[Trajectory]:
        """Build child trajectories from sub-agent-tagged events.

        Copilot interleaves the spawned agent's events with the parent's in the
        same ``events.jsonl``; every sub-agent event carries the spawning
        ``toolCallId`` as ``agentId``. We re-read the file (cheap; same one the
        parent just consumed) and split events by ``agentId``, parsing each
        group as a child Trajectory linked to the main via
        ``parent_trajectory_ref``. The spawning ToolCall's observation gets a
        ``subagent_trajectory_ref`` so the UI can navigate down.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return []
        raw = list(iter_jsonl_safe(content))
        if not raw:
            return []

        subagent_started = _index_events(raw, "subagent.started", lambda d: d.get("toolCallId"))
        subagent_completed = _index_events(raw, "subagent.completed", lambda d: d.get("toolCallId"))
        complete_by_call_id = _index_events(
            raw, "tool.execution_complete", lambda d: d.get("toolCallId")
        )

        groups: dict[str, list[dict]] = {}
        for event in raw:
            agent_id = event.get("agentId")
            if not agent_id:
                continue
            groups.setdefault(agent_id, []).append(event)

        children: list[Trajectory] = []
        for agent_id, events in groups.items():
            traj = _build_subagent_trajectory(
                main_session_id=main.session_id,
                agent_id=agent_id,
                events=events,
                started_payload=subagent_started.get(agent_id),
                completed_payload=subagent_completed.get(agent_id),
                complete_by_call_id=complete_by_call_id,
                main_model=main.agent.model_name if main.agent else None,
            )
            if traj is not None:
                children.append(traj)
                attach_subagent_ref(main.steps, agent_id, traj.session_id)
        return children


# ---- Module helpers ----


def _index_events(raw: list[dict], event_type: str, key_fn) -> dict[str, dict]:
    """Build {key: event-data} for events of one type, skipping null keys."""
    out: dict[str, dict] = {}
    for event in raw:
        if event.get("type") != event_type:
            continue
        data = event.get("data") or {}
        key = key_fn(data)
        if key:
            out[key] = data
    return out


def _build_user_step(event: dict, data: dict) -> Step:
    """Build a USER step from a user.message event.

    Reads ``attachments[]`` paths and inlines image bytes as multimodal
    ``ContentPart`` entries so the UI can render them. When a path is gone
    (system-tmp cleanup is common for clipboard pastes), we record the
    placeholder in ``extra.attachments`` and rely on the inline ``[📷 ...]``
    text Copilot already wrote into ``content``.
    """
    content = data.get("content") or ""
    attachments = data.get("attachments") or []
    image_parts = _build_attachment_content_parts(attachments)
    message = build_multimodal_message(content, image_parts)

    extra_keep_attachments = [
        {"path": a.get("path"), "displayName": a.get("displayName"), "type": a.get("type")}
        for a in attachments
    ]
    extra = {
        k: v
        for k, v in (
            (
                "transformed_content",
                data.get("transformedContent")
                if data.get("transformedContent") != content
                else None,
            ),
            ("attachments", extra_keep_attachments or None),
            ("interaction_id", data.get("interactionId")),
        )
        if v is not None
    }
    return Step(
        step_id=event.get("id") or deterministic_id("copilot_user", content[:32]),
        timestamp=parse_iso_timestamp(event.get("timestamp")),
        source=StepSource.USER,
        message=message,
        extra=extra or None,
    )


def _build_attachment_content_parts(attachments: list[dict]) -> list[ContentPart]:
    """Read each attachment from disk and return image ContentParts.

    Skips attachments whose file is missing, exceeds the size cap, or whose
    mime type isn't image/*. Non-image attachments are out of current scope —
    see Future work in the module docstring.
    """
    parts: list[ContentPart] = []
    for att in attachments:
        path_str = att.get("path")
        if not path_str:
            continue
        path = Path(path_str)
        if not path.is_file():
            continue
        mime, _ = mimetypes.guess_type(path.name)
        if not mime or not mime.startswith("image/"):
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if len(data) > _MAX_IMAGE_BYTES:
            continue
        parts.append(
            ContentPart(
                type=ContentType.IMAGE,
                source=Base64Source(media_type=mime, base64=base64.b64encode(data).decode("ascii")),
            )
        )
    return parts


def _build_subagent_trajectory(
    main_session_id: str,
    agent_id: str,
    events: list[dict],
    started_payload: dict | None,
    completed_payload: dict | None,
    complete_by_call_id: dict[str, dict],
    main_model: str | None,
) -> Trajectory | None:
    """Assemble one sub-agent Trajectory from events tagged with ``agent_id``.

    Re-runs the same step-building logic the parent uses on its slice of
    events. Walks ``session.model_change`` so the child's model is correct
    even if the parent ran a different one.
    """
    started = started_payload or {}
    completed = completed_payload or {}
    sub_session_id = f"{main_session_id}:subagent:{agent_id}"
    agent_name = started.get("agentName") or "subagent"
    sub_model = completed.get("model") or main_model

    sub_extra: dict[str, Any] = {
        "agent_role": agent_name,
        "agent_nickname": started.get("agentDisplayName") or agent_name,
        "spawn_tool_call_id": agent_id,
    }
    if description := started.get("agentDescription"):
        sub_extra["agent_description"] = description
    for src, dst in (
        ("totalToolCalls", "subagent_total_tool_calls"),
        ("totalTokens", "subagent_total_tokens"),
        ("durationMs", "subagent_duration_ms"),
    ):
        if completed.get(src) is not None:
            sub_extra[dst] = completed[src]

    traj = Trajectory(
        session_id=sub_session_id,
        agent=Agent(name=AgentType.COPILOT.value, model_name=sub_model),
        parent_trajectory_ref=TrajectoryRef(session_id=main_session_id),
        extra=sub_extra,
    )

    current_model = sub_model
    current_reasoning: str | None = None
    steps: list[Step] = []
    diagnostics = DiagnosticsCollector()
    for event in events:
        event_type = event.get("type")
        data = event.get("data") or {}
        if event_type == "session.model_change":
            current_model = data.get("newModel") or current_model
            current_reasoning = data.get("reasoningEffort") or current_reasoning
            continue
        if event_type == "user.message":
            steps.append(_build_user_step(event, data))
            continue
        if event_type == "assistant.message":
            step = _build_assistant_step(
                event,
                data,
                complete_by_call_id,
                subagent_started={},
                subagent_completed={},
                current_model=current_model,
                current_reasoning_effort=current_reasoning,
                diagnostics=diagnostics,
            )
            if step is not None:
                steps.append(step)
    if not steps:
        return None
    if current_model and traj.agent.model_name is None:
        traj.agent.model_name = current_model
    traj.steps = steps
    return traj


def _build_assistant_step(
    event: dict,
    data: dict,
    complete_by_call_id: dict[str, dict],
    subagent_started: dict[str, dict],
    subagent_completed: dict[str, dict],
    current_model: str | None,
    current_reasoning_effort: str | None,
    diagnostics: DiagnosticsCollector,
) -> Step | None:
    """Build an AGENT step + paired tool_calls/observations."""
    message_id = data.get("messageId")
    text = data.get("content") or ""
    tool_requests = data.get("toolRequests") or []

    tool_calls: list[ToolCall] = []
    observation_results: list[ObservationResult] = []

    for req in tool_requests:
        call_id = req.get("toolCallId") or ""
        function_name = req.get("name") or ""
        tc_extra = _build_tool_call_extra(
            req, function_name, call_id, subagent_started, subagent_completed
        )
        tool_calls.append(
            ToolCall(
                tool_call_id=call_id,
                function_name=function_name,
                arguments=req.get("arguments"),
                extra=tc_extra or None,
            )
        )
        diagnostics.record_tool_call()

        complete = complete_by_call_id.get(call_id)
        if complete is not None:
            observation_results.append(_build_observation_from_complete(complete, call_id))
            diagnostics.record_tool_result()
        else:
            # In-flight: synthetic error so the UI surfaces the partial run.
            observation_results.append(
                ObservationResult(
                    source_call_id=call_id,
                    content="",
                    is_error=True,
                    extra={"in_flight": True},
                )
            )
            diagnostics.record_orphaned_call(call_id)

    output_tokens = data.get("outputTokens")
    metrics: Metrics | None = None
    if isinstance(output_tokens, int) and output_tokens > 0:
        metrics = Metrics.from_tokens(output_tokens=output_tokens)

    if not text and not tool_calls and metrics is None:
        return None

    extra = {
        k: v
        for k, v in (
            ("message_id", message_id),
            ("request_id", data.get("requestId")),
            ("interaction_id", data.get("interactionId")),
        )
        if v is not None
    }

    return Step(
        step_id=event.get("id") or deterministic_id("copilot_assistant", message_id or ""),
        timestamp=parse_iso_timestamp(event.get("timestamp")),
        source=StepSource.AGENT,
        model_name=current_model,
        reasoning_effort=current_reasoning_effort,
        message=text,
        tool_calls=tool_calls,
        observation=Observation(results=observation_results) if observation_results else None,
        metrics=metrics,
        extra=extra or None,
    )


def _build_tool_call_extra(
    req: dict,
    function_name: str,
    call_id: str,
    subagent_started: dict[str, dict],
    subagent_completed: dict[str, dict],
) -> dict[str, Any]:
    """Build ToolCall.extra: intention summary, tool title, sub-agent metadata."""
    extra: dict[str, Any] = {}
    if req.get("intentionSummary"):
        extra["intention_summary"] = req["intentionSummary"]
    if req.get("toolTitle"):
        extra["tool_title"] = req["toolTitle"]
    if function_name in _SUBAGENT_SPAWN_TOOLS:
        sa = _build_subagent_meta(subagent_started.get(call_id), subagent_completed.get(call_id))
        if sa:
            extra["subagent"] = sa
    return extra


def _build_subagent_meta(started: dict | None, completed: dict | None) -> dict[str, Any] | None:
    """Combine subagent.started + subagent.completed payloads into one dict."""
    out: dict[str, Any] = {}
    if started:
        for src, dst in (
            ("agentName", "agent_name"),
            ("agentDisplayName", "agent_display_name"),
            ("agentDescription", "agent_description"),
        ):
            if started.get(src):
                out[dst] = started[src]
    if completed:
        for src, dst in (
            ("model", "model"),
            ("totalToolCalls", "total_tool_calls"),
            ("totalTokens", "total_tokens"),
            ("durationMs", "duration_ms"),
        ):
            if completed.get(src) is not None:
                out[dst] = completed[src]
    return out or None


def _build_observation_from_complete(complete: dict, call_id: str) -> ObservationResult:
    """Convert a tool.execution_complete event into an ObservationResult."""
    data = complete.get("data") or complete  # `complete` may be either raw event or just data
    if "result" not in data and "data" in data:
        data = data["data"]
    result = data.get("result") or {}
    text = result.get("detailedContent") or result.get("content") or ""
    extra = {
        k: v
        for k, v in (("telemetry", data.get("toolTelemetry")), ("model", data.get("model")))
        if v
    }
    return ObservationResult(
        source_call_id=call_id,
        content=text,
        is_error=not data.get("success", True),
        extra=extra or None,
    )


def _build_compaction_step(event: dict, data: dict) -> Step | None:
    """Synthesise a SYSTEM step from a ``session.compaction_complete`` event.

    The interesting payload is ``summaryContent`` — the rewritten history
    Copilot keeps around after compaction. We surface it as the message
    body so the user can read what context survived; per-event token
    metrics ride along on ``extra``.
    """
    summary = (data.get("summaryContent") or "").strip()
    if not data.get("success", True) and not summary:
        return None
    extra: dict[str, Any] = {}
    for src, dst in (
        ("preCompactionTokens", "pre_compaction_tokens"),
        ("preCompactionMessagesLength", "pre_compaction_messages"),
        ("success", "success"),
    ):
        if data.get(src) is not None:
            extra[dst] = data[src]
    return Step(
        step_id=event.get("id") or deterministic_id("copilot_compact", event.get("timestamp", "")),
        timestamp=parse_iso_timestamp(event.get("timestamp")),
        source=StepSource.SYSTEM,
        message=summary or "[Context compacted]",
        is_compaction=True,
        extra=extra or None,
    )


def _build_truncation_step(event: dict, data: dict) -> Step:
    """Synthesise a SYSTEM step recording a ``session.truncation`` event.

    Truncation is a harder cut than compaction — Copilot drops messages
    outright when the model's window is exceeded. We keep the metrics
    so the dashboard can flag aggressive context loss.
    """
    extra: dict[str, Any] = {"is_truncation": True}
    for src, dst in (
        ("performedBy", "performed_by"),
        ("tokenLimit", "token_limit"),
        ("preTruncationTokensInMessages", "pre_truncation_tokens"),
        ("postTruncationTokensInMessages", "post_truncation_tokens"),
        ("tokensRemovedDuringTruncation", "tokens_removed"),
        ("preTruncationMessagesLength", "pre_truncation_messages"),
        ("postTruncationMessagesLength", "post_truncation_messages"),
        ("messagesRemovedDuringTruncation", "messages_removed"),
    ):
        if data.get(src) is not None:
            extra[dst] = data[src]
    removed_tokens = data.get("tokensRemovedDuringTruncation") or 0
    removed_msgs = data.get("messagesRemovedDuringTruncation") or 0
    return Step(
        step_id=event.get("id") or deterministic_id("copilot_truncate", event.get("timestamp", "")),
        timestamp=parse_iso_timestamp(event.get("timestamp")),
        source=StepSource.SYSTEM,
        message=f"[Context truncated: removed {removed_msgs} messages / {removed_tokens} tokens]",
        extra=extra,
    )


def _attach_shutdown_summary(traj: Trajectory, data: dict) -> None:
    """Stash session.shutdown payload onto traj.extra."""
    extra = dict(traj.extra or {})
    if data.get("codeChanges"):
        extra["code_changes"] = data["codeChanges"]
    summary_keys = (
        "totalApiDurationMs",
        "totalPremiumRequests",
        "sessionStartTime",
        "shutdownType",
    )
    summary = {k: data[k] for k in summary_keys if data.get(k) is not None}
    if summary:
        extra["session_summary"] = summary
    breakdown_keys = (
        "currentModel",
        "currentTokens",
        "systemTokens",
        "conversationTokens",
        "toolDefinitionsTokens",
    )
    breakdown = {k: data[k] for k in breakdown_keys if data.get(k) is not None}
    if breakdown:
        extra["token_breakdown"] = breakdown
    if data.get("modelMetrics"):
        extra["model_metrics"] = data["modelMetrics"]
    traj.extra = extra or None


def _aggregate_session_metrics(model_metrics: dict, steps: list) -> FinalMetrics:
    """Sum across every model bucket in modelMetrics; build daily breakdown.

    ``model_metrics``: {<model>: {requests: {count, cost}, usage: {inputTokens,
                                  outputTokens, cacheReadTokens, cacheWriteTokens, ...}}}
    Multi-model sessions (when ``session.model_change`` fires mid-stream) sum
    across all buckets.
    """
    total_input = total_output = total_cache_read = total_cache_write = 0
    total_cost = 0.0
    for bucket in model_metrics.values():
        usage = bucket.get("usage") or {}
        total_input += usage.get("inputTokens", 0) or 0
        total_output += usage.get("outputTokens", 0) or 0
        total_cache_read += usage.get("cacheReadTokens", 0) or 0
        total_cache_write += usage.get("cacheWriteTokens", 0) or 0
        total_cost += float((bucket.get("requests") or {}).get("cost", 0) or 0)

    return FinalMetrics(
        duration=_session_duration_seconds(steps),
        total_steps=len(steps),
        tool_call_count=sum(len(s.tool_calls or []) for s in steps),
        total_prompt_tokens=total_input + total_cache_read,
        total_completion_tokens=total_output,
        total_cache_read_tokens=total_cache_read,
        total_cache_write_tokens=total_cache_write,
        total_cost_usd=total_cost,
        daily_breakdown=_daily_breakdown(steps, total_input + total_output, total_cost),
    )


def _daily_breakdown(
    steps: list, total_tokens: int, total_cost: float
) -> dict[str, DailyBucket] | None:
    """Distribute aggregate tokens/cost across days proportional to message count."""
    counts: dict[str, int] = {}
    for s in steps:
        if s.timestamp is None:
            continue
        key = local_date_key(s.timestamp)
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    total_msgs = sum(counts.values())
    return {
        key: DailyBucket(
            messages=n,
            tokens=int(total_tokens * n / total_msgs),
            cost_usd=total_cost * n / total_msgs,
        )
        for key, n in counts.items()
    }


def _session_duration_seconds(steps: list) -> int:
    """Wall-clock duration between first and last step timestamps."""
    timestamps = [s.timestamp for s in steps if s.timestamp]
    if len(timestamps) < 2:
        return 0
    return int((max(timestamps) - min(timestamps)).total_seconds())
