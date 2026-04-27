"""Code Buddy session parser.

Code Buddy (https://codebuddy.tencent.com) stores sessions at
``~/.codebuddy/projects/<hash>/<sid>.jsonl`` with sibling sub-agent files at
``<sid>/subagents/agent-<short>.jsonl``. The directory shape mirrors Claude
Code's, but the wire format does NOT — events are flat (no envelope) and
shaped like the OpenAI Responses API rather than Anthropic Messages.

Each line is one event:

    {"id": "<uuid>", "parentId": "<uuid|null>", "timestamp": <ms>,
     "type": "message|reasoning|function_call|function_call_result|topic|file-history-snapshot",
     "sessionId": "<sid>", "cwd": "<path>", ...type-specific fields}

Event-specific shapes (verified by exhaustive key-path enumeration):

    message     role, status, content[].{type:"input_text"|"output_text", text},
                providerData.{model, agent, messageId, rawUsage, usage,
                              teammateMessage?, isSubAgent?, queuePosition?,
                              queueTotal?, agentColor?}
    reasoning   rawContent[].{type:"reasoning_text", text} — content array empty
    function_call    name, callId, arguments (JSON string), providerData.{...}
    function_call_result  name, callId, status, output.{type:"text", text},
                          providerData.toolResult.{content, renderer.{type, value}}
    topic       topic (string only — no id/parentId/sessionId)
    file-history-snapshot  snapshot.{messageId, trackedFileBackups}

Sub-agent linkage:
    parent: function_call_result.providerData.toolResult.renderer.value JSON
            with {name, taskId, prompt, color, teamName} — taskId names the
            child file (agent-<taskId>.jsonl). Regex on output.text is fallback.
    child:  filename + first user message wrapped in <teammate-message ...>
            + providerData.isSubAgent on subsequent steps

is_error caveat: all observed function_call_result.status values are
"completed". The error sentinel (`status != "completed"`) is inferred,
not verified.

Capability vs Claude reference parser:
  - text content                   ✓
  - reasoning content              ✓ (``reasoning`` events)
  - tool calls + observations      ✓
  - sub-agents (sibling files)     ✓ (``<sid>/subagents/`` dir)
  - multimodal images (inline)     ✓ (``image_blob_ref`` parts inlined as
                                     base64 ContentParts)
  - persistent output files        ✗ no large-output split.
  - continuation refs (prev/next)  ✗ no resume workflow.
  - compaction sessions            ✓ ``providerData.isCompactInternal`` and
                                     ``providerData.agent == "compact"`` mark
                                     the in-stream summarisation turn; we tag
                                     the affected steps with
                                     ``extra.is_compaction = True`` so the UI
                                     can render a boundary while preserving
                                     the surrounding conversation.

Future work:
  // TODO(file-history): file-history-snapshot.trackedFileBackups is dropped;
     surface as ATIF patches in a future revision.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import BaseParser
from vibelens.ingest.parsers.helpers import (
    is_skill_tool,
    iter_jsonl_safe,
    tag_step_compaction,
)
from vibelens.models.enums import AgentType, ContentType, StepSource
from vibelens.models.trajectories import (
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
)
from vibelens.models.trajectories.content import ContentPart, ImageSource
from vibelens.models.trajectories.trajectory_ref import TrajectoryRef
from vibelens.utils import deterministic_id, get_logger

logger = get_logger(__name__)

# Filename basename of sub-agent JSONL, e.g. agent-8c36227f.jsonl.
_SUBAGENTS_DIR_NAME = "subagents"
_TASK_ID_PATTERN = re.compile(r"task_id:\s*(agent-\w+)")
_TEAMMATE_MESSAGE_PREFIX = "<teammate-message"

# Code Buddy uses Claude-Code-style XML tags to record CLI command echoes,
# system reminders, and stdout dumps as user messages. They have content but
# aren't user-typed text — classify them as SYSTEM so the UI doesn't show
# them as empty user bubbles. Pattern matches with-or-without attributes
# (e.g. ``<system-reminder data-role="...">`` and ``<command-name>``).
_CODEBUDDY_SYSTEM_XML_TAGS = frozenset(
    {
        "system-reminder",
        "local-command-caveat",
        "local-command-stdout",
        "command-message",
        "command-name",
        "command-args",
        "task-notification",
        "user-prompt-submit-hook",
    }
)
_SYSTEM_TAG_PATTERN = re.compile(
    r"^\s*<(" + "|".join(re.escape(t) for t in _CODEBUDDY_SYSTEM_XML_TAGS) + r")[\s>]"
)


class CodebuddyParser(BaseParser):
    """Parser for Code Buddy CLI's flat-event JSONL session format."""

    AGENT_TYPE = AgentType.CODEBUDDY
    LOCAL_DATA_DIR: Path | None = Path.home() / ".codebuddy"
    # Filenames are UUIDs and parse() falls back to file_path.stem when the
    # event payload lacks sessionId, so the bare stem is canonical.
    NAMESPACE_SESSION_IDS = False

    # ---- Discovery ----
    def discover_session_files(self, data_dir: Path) -> list[Path]:
        """Return main session JSONLs under ``projects/`` (excluding subagents)."""
        projects_dir = data_dir / "projects"
        if not projects_dir.is_dir():
            return []
        files: list[Path] = []
        for jsonl in sorted(projects_dir.rglob("*.jsonl")):
            if _SUBAGENTS_DIR_NAME in jsonl.parts:
                continue
            files.append(jsonl)
        return files

    def get_session_files(self, session_file: Path) -> list[Path]:
        """Return main JSONL plus all sibling sub-agent JSONLs."""
        files = [session_file]
        subagent_dir = session_file.parent / session_file.stem / _SUBAGENTS_DIR_NAME
        if subagent_dir.is_dir():
            files.extend(sorted(subagent_dir.glob("agent-*.jsonl")))
        return files

    # ---- Pipeline ----
    def _decode_file(self, file_path: Path, diagnostics: DiagnosticsCollector) -> list[dict] | None:
        """Read JSONL into a list of decoded events."""
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
        """Build a Trajectory header from the first message-bearing event."""
        session_id: str | None = None
        cwd: str | None = None
        for event in raw:
            if not session_id and event.get("sessionId"):
                session_id = event["sessionId"]
            if not cwd and event.get("cwd"):
                cwd = event["cwd"]
            if session_id and cwd:
                break
        if not session_id:
            session_id = file_path.stem
        return Trajectory(session_id=session_id, agent=self.build_agent(), project_path=cwd)

    def _build_steps(
        self, raw: list[dict], traj: Trajectory, file_path: Path, diagnostics: DiagnosticsCollector
    ) -> list[Step]:
        """Walk events in time order; emit USER/AGENT steps with paired tools."""
        # Pre-scan function_call_result by callId for fast pairing.
        result_by_call_id: dict[str, dict] = {}
        for event in raw:
            if event.get("type") != "function_call_result":
                continue
            call_id = event.get("callId")
            if call_id:
                result_by_call_id[call_id] = event

        # Detect if this is a sub-agent file (has any providerData.isSubAgent).
        is_subagent_file = any(
            ((e.get("providerData") or {}).get("isSubAgent") is True)
            for e in raw
            if e.get("type") in {"message", "reasoning", "function_call"}
        )
        topic: str | None = None
        agent_role: str | None = None
        spawn_metadata: dict[str, Any] | None = None

        steps: list[Step] = []
        current: _AgentTurnBuilder | None = None
        last_model: str | None = None

        for event in raw:
            event_type = event.get("type")

            if event_type == "topic":
                topic = event.get("topic") or topic
                continue

            if event_type == "file-history-snapshot":
                continue

            provider_data = event.get("providerData") or {}
            message_id = provider_data.get("messageId")
            agent_role = provider_data.get("agent") or agent_role
            model = provider_data.get("model") or last_model
            if model:
                last_model = model
            # Compaction marker: either the user message that triggered it
            # (``isCompactInternal``) or any event the model emitted while
            # acting as the synthetic ``compact`` agent.
            event_is_compaction = bool(
                provider_data.get("isCompactInternal") or provider_data.get("agent") == "compact"
            )

            if event_type == "message":
                role = event.get("role")
                if role == "user":
                    if current is not None:
                        steps.append(current.build())
                        current = None
                    user_step = _build_user_step(event, is_subagent_file)
                    if user_step is None:
                        # CLI command echo (e.g. <command-name>/model</...>);
                        # has content but no conversational value — drop entirely
                        # so the UI doesn't show empty bubbles.
                        diagnostics.record_skip("cli command echo")
                        continue
                    if event_is_compaction:
                        user_step = tag_step_compaction(user_step, agent_role="compact")
                    steps.append(user_step)
                    if user_step.extra and user_step.extra.get("spawn"):
                        spawn_metadata = user_step.extra["spawn"]
                    continue

                if role == "assistant":
                    current = _ensure_turn(current, message_id, model, steps)
                    if event_is_compaction:
                        current.is_compaction = True
                    current.add_message(event)
                    continue
                # Other roles: ignore.
                continue

            if event_type == "reasoning":
                current = _ensure_turn(current, message_id, model, steps)
                if event_is_compaction:
                    current.is_compaction = True
                current.add_reasoning(event)
                continue

            if event_type == "function_call":
                current = _ensure_turn(current, message_id, model, steps)
                if event_is_compaction:
                    current.is_compaction = True
                call_id = event.get("callId") or ""
                fc_result = result_by_call_id.get(call_id)
                current.add_function_call(event, fc_result)
                diagnostics.record_tool_call()
                if fc_result is not None:
                    diagnostics.record_tool_result()
                else:
                    diagnostics.record_orphaned_call(call_id)
                continue

            if event_type == "function_call_result":
                # Already paired via the pre-scan; ignored here.
                continue

            diagnostics.record_skip(f"unknown codebuddy event type {event_type!r}")

        if current is not None:
            steps.append(current.build())

        # Backfill traj.agent.model_name and traj.extra.
        if last_model and traj.agent.model_name is None:
            traj.agent.model_name = last_model
        extra = dict(traj.extra or {})
        if topic:
            extra["topic"] = topic
        if is_subagent_file:
            extra["is_subagent"] = True
            if spawn_metadata:
                if "team_name" in spawn_metadata:
                    extra["team_name"] = spawn_metadata["team_name"]
                if "agent_color" in spawn_metadata:
                    extra["agent_color"] = spawn_metadata["agent_color"]
        traj.extra = extra or None

        return steps

    # ---- Sub-agent loading ----
    def _load_subagents(self, main: Trajectory, file_path: Path) -> list[Trajectory]:
        """Discover sub-agent JSONLs and build bidirectional refs."""
        subagent_dir = file_path.parent / file_path.stem / _SUBAGENTS_DIR_NAME
        if not subagent_dir.is_dir():
            return []

        children: list[Trajectory] = []
        for step in main.steps:
            if not step.tool_calls or not step.observation:
                continue
            for tc, obs in zip(step.tool_calls, step.observation.results, strict=False):
                if tc.function_name not in {"Agent", "Task"}:
                    continue
                task_id = (obs.extra or {}).get("spawn_task_id")
                if not task_id:
                    continue
                child_path = subagent_dir / f"{task_id}.jsonl"
                if not child_path.exists():
                    continue
                child = self._parse_trajectory(child_path)
                if child is None:
                    continue
                child.parent_trajectory_ref = TrajectoryRef(
                    session_id=main.session_id,
                    step_id=step.step_id,
                    tool_call_id=tc.tool_call_id,
                    trajectory_path=str(file_path),
                )
                obs.subagent_trajectory_ref = [TrajectoryRef(session_id=child.session_id)]
                children.append(child)
        return children


class _AgentTurnBuilder:
    """Accumulate message/reasoning/function_call events into one AGENT Step."""

    def __init__(self, message_id: str | None, model: str | None) -> None:
        self.message_id = message_id
        self.model = model
        self.first_event_id: str | None = None
        self.first_timestamp: datetime | None = None
        self.text_parts: list[str] = []
        self.reasoning_parts: list[str] = []
        self.tool_calls: list[ToolCall] = []
        self.obs_results: list[ObservationResult] = []
        self.last_raw_usage: dict | None = None
        # Sticky once any contributing event has providerData.agent == "compact"
        # or providerData.isCompactInternal — preserves compaction tagging on
        # the assembled assistant step.
        self.is_compaction: bool = False

    def add_message(self, event: dict) -> None:
        self._record_first(event)
        for content_part in event.get("content") or []:
            text = content_part.get("text") or ""
            if text:
                self.text_parts.append(text)
        provider = event.get("providerData") or {}
        usage = provider.get("rawUsage")
        if usage:
            self.last_raw_usage = usage

    def add_reasoning(self, event: dict) -> None:
        self._record_first(event)
        for raw_part in event.get("rawContent") or []:
            text = raw_part.get("text") or ""
            if text:
                self.reasoning_parts.append(text)

    def add_function_call(self, event: dict, fc_result: dict | None) -> None:
        self._record_first(event)
        provider = event.get("providerData") or {}
        usage = provider.get("rawUsage")
        if usage:
            self.last_raw_usage = usage
        call_id = event.get("callId") or ""
        function_name = event.get("name") or ""
        raw_args = event.get("arguments")
        arguments: Any
        if isinstance(raw_args, str):
            try:
                arguments = json.loads(raw_args)
            except json.JSONDecodeError:
                arguments = raw_args
        else:
            arguments = raw_args
        tc_extra: dict[str, Any] = {}
        display = provider.get("argumentsDisplayText")
        if display:
            tc_extra["arguments_display_text"] = display
        if provider.get("queuePosition") is not None:
            tc_extra["queue_position"] = provider["queuePosition"]
        if provider.get("queueTotal") is not None:
            tc_extra["queue_total"] = provider["queueTotal"]
        if provider.get("agentColor"):
            tc_extra["agent_color"] = provider["agentColor"]
        self.tool_calls.append(
            ToolCall(
                tool_call_id=call_id,
                function_name=function_name,
                arguments=arguments,
                is_skill=True if is_skill_tool(function_name) else None,
                extra=tc_extra or None,
            )
        )
        if fc_result is None:
            return
        self.obs_results.append(_build_observation_from_result(fc_result, call_id))

    def _record_first(self, event: dict) -> None:
        if self.first_event_id is None:
            self.first_event_id = event.get("id")
            self.first_timestamp = _ms_to_datetime(event.get("timestamp"))

    def build(self) -> Step:
        text = "".join(self.text_parts)
        reasoning_content = "".join(self.reasoning_parts) or None
        metrics = _build_metrics_from_raw_usage(self.last_raw_usage)
        extra: dict[str, Any] = {}
        if self.message_id:
            extra["message_id"] = self.message_id
        if self.is_compaction:
            extra["agent_role"] = "compact"
        return Step(
            step_id=self.first_event_id
            or deterministic_id("codebuddy_agent", self.message_id or ""),
            timestamp=self.first_timestamp,
            source=StepSource.AGENT,
            model_name=self.model,
            message=text,
            reasoning_content=reasoning_content,
            tool_calls=self.tool_calls,
            observation=Observation(results=self.obs_results) if self.obs_results else None,
            metrics=metrics,
            is_compaction=True if self.is_compaction else None,
            extra=extra or None,
        )


def _ensure_turn(
    current: _AgentTurnBuilder | None, message_id: str | None, model: str | None, steps: list[Step]
) -> _AgentTurnBuilder:
    """Flush ``current`` if its messageId differs; return active turn builder."""
    if current is not None and (message_id is None or message_id == current.message_id):
        return current
    if current is not None:
        steps.append(current.build())
    return _AgentTurnBuilder(message_id=message_id, model=model)


def _build_user_step(event: dict, is_subagent_file: bool) -> Step | None:
    """Build a user-side step from a user message.

    CLI command echoes (``<command-name>``, ``<local-command-stdout>``,
    ``<system-reminder>``, etc.) are dropped entirely — they have content but
    no conversational value, and emitting them clutters the UI with empty
    bubbles. Caller records a diagnostics.skip for the drop.

    Multimodal content: when ``image_blob_ref`` parts appear alongside text,
    Step.message becomes a ``list[ContentPart]`` and each image is read from
    disk and inlined as base64 so the UI can render it. For text-only content,
    message stays a plain string.
    """
    text_parts: list[str] = []
    image_parts: list[dict] = []
    for part in event.get("content") or []:
        ptype = part.get("type")
        if ptype in {"input_text", "output_text"} and (text := part.get("text")):
            text_parts.append(text)
        elif ptype == "image_blob_ref":
            image_parts.append(part)
    text = "".join(text_parts)

    # Drop CLI command echoes (matches both bare and attribute-bearing tags).
    if _SYSTEM_TAG_PATTERN.match(text):
        return None

    extra: dict[str, Any] = {}
    if is_subagent_file and text.startswith(_TEAMMATE_MESSAGE_PREFIX):
        extra["is_spawn_prompt"] = True
        spawn = _parse_teammate_message(text)
        if spawn:
            extra["spawn"] = spawn

    if image_parts:
        parts: list[ContentPart] = []
        if text:
            parts.append(ContentPart(type=ContentType.TEXT, text=text))
        for img in image_parts:
            parts.append(_image_blob_ref_to_content_part(img))
        message: str | list[ContentPart] = parts
    else:
        message = text

    return Step(
        step_id=event.get("id") or deterministic_id("codebuddy_user", text[:32]),
        timestamp=_ms_to_datetime(event.get("timestamp")),
        source=StepSource.USER,
        message=message,
        extra=extra or None,
    )


def _image_blob_ref_to_content_part(img: dict) -> ContentPart:
    """Convert an ``image_blob_ref`` part to ContentPart with inline base64.

    Code Buddy stores image blobs at ``~/.codebuddy/blobs/<hash>/<hash>.png``.
    The UI cannot render absolute filesystem paths directly (sandboxing), so
    we read the blob and inline it as base64. Falls back to path-only if the
    blob file isn't present on disk.
    """
    import base64

    media_type = img.get("mime") or "image/png"
    blob_path = img.get("blob_path") or ""
    b64 = ""
    if blob_path:
        try:
            b64 = base64.b64encode(Path(blob_path).read_bytes()).decode("ascii")
        except OSError:
            b64 = ""  # path-only fallback
    return ContentPart(
        type=ContentType.IMAGE,
        source=ImageSource(media_type=media_type, base64=b64, path=blob_path),
    )


def _parse_teammate_message(text: str) -> dict | None:
    """Extract teammate_id and summary from a <teammate-message ...> wrapper."""
    teammate_id = None
    summary = None
    m = re.search(r'teammate_id="([^"]+)"', text)
    if m:
        teammate_id = m.group(1)
    m = re.search(r'summary="([^"]+)"', text)
    if m:
        summary = m.group(1)
    if not teammate_id and not summary:
        return None
    return {"teammate_id": teammate_id, "summary": summary}


def _build_observation_from_result(fc_result: dict, call_id: str) -> ObservationResult:
    """Convert a function_call_result event into an ObservationResult."""
    output = fc_result.get("output") or {}
    text = output.get("text") if isinstance(output, dict) else None
    text = text or ""
    status = fc_result.get("status")
    is_error = status is not None and status != "completed"

    extra: dict[str, Any] = {}
    provider = fc_result.get("providerData") or {}
    tool_result = provider.get("toolResult") or {}
    renderer = tool_result.get("renderer") or {}
    if renderer.get("type"):
        extra["renderer_type"] = renderer["type"]

    # Sub-agent task_id discovery
    task_id = _extract_task_id(fc_result)
    if task_id:
        extra["spawn_task_id"] = task_id

    return ObservationResult(
        source_call_id=call_id, content=text, is_error=is_error, extra=extra or None
    )


def _extract_task_id(fc_result: dict) -> str | None:
    """Extract a task_id (agent-<short>) from an Agent tool result.

    Primary source: providerData.toolResult.renderer.value JSON {taskId}.
    Fallback: regex `task_id:\\s*(agent-\\w+)` on output.text.
    """
    provider = fc_result.get("providerData") or {}
    tool_result = provider.get("toolResult") or {}
    renderer = tool_result.get("renderer") or {}
    raw_value = renderer.get("value")
    if isinstance(raw_value, str):
        try:
            data = json.loads(raw_value)
            task_id = data.get("taskId")
            if task_id:
                return task_id
        except (json.JSONDecodeError, AttributeError):
            pass
    output = fc_result.get("output") or {}
    output_text = output.get("text") if isinstance(output, dict) else None
    if not output_text:
        return None
    match = _TASK_ID_PATTERN.search(output_text)
    return match.group(1) if match else None


def _build_metrics_from_raw_usage(raw_usage: dict | None) -> Metrics | None:
    """Build a Metrics from a Code Buddy providerData.rawUsage payload.

    Code Buddy reports ``credit`` (Tencent's billing unit, NOT verified to be
    USD) — we stash it in ``Metrics.extra.credit`` rather than ``cost_usd`` to
    avoid claiming a dollar amount we cannot verify. If a future audit confirms
    the unit, move to ``cost_usd``.
    """
    if not raw_usage:
        return None
    input_tokens = raw_usage.get("prompt_tokens", 0) or 0
    output_tokens = raw_usage.get("completion_tokens", 0) or 0
    cache_read = raw_usage.get("cache_read_input_tokens", 0) or 0
    cache_write = raw_usage.get("cache_creation_input_tokens", 0) or 0
    credit = raw_usage.get("credit")
    reasoning = (raw_usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0) or 0
    if not any((input_tokens, output_tokens, cache_read, cache_write, credit, reasoning)):
        return None
    extra: dict | None = None
    if reasoning or credit is not None:
        extra = {}
        if reasoning:
            extra["reasoning_output_tokens"] = reasoning
        if credit is not None:
            extra["credit"] = credit
    return Metrics.from_tokens(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        cost_usd=None,  # Tencent's `credit` is not verified to be USD; see docstring.
        extra=extra,
    )


def _ms_to_datetime(value: Any) -> datetime | None:
    """Convert a millisecond Unix epoch into a UTC datetime."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
