"""Kiro CLI session parser.

Kiro (https://kiro.dev — AWS's agentic IDE/CLI) stores each chat session as a
paired JSONL + JSON at ``~/.kiro/sessions/cli/<sid>.jsonl`` and
``~/.kiro/sessions/cli/<sid>.json``.

Wire format
-----------

Each JSONL line is a versioned envelope::

    {
        "version": "v1",
        "kind": "Prompt|AssistantMessage|ToolResults|Compaction",
        "data": {...}
    }

``data.content`` (for ``Prompt`` / ``AssistantMessage`` / ``ToolResults``)
is an array of content blocks::

    {"kind": "text",       "data": "..."}
    {"kind": "toolUse",    "data": {"toolUseId", "name", "input"}}
    {"kind": "toolResult", "data": {"toolUseId", "content", "status"}}
    {"kind": "image",      "data": {"format": "png",
                                    "source": {"kind": "bytes", "data": [<int>, ...]}}}

The ``Compaction`` envelope's ``data`` is ``{"summary": "<rich text>"}``.

Sibling ``<sid>.json`` carries session-level metadata
(``session_id, cwd, title, created_at, updated_at, session_state``).

Capability vs Claude reference parser:
  - text content                  ✓ (``text`` content blocks)
  - reasoning content             ✗ // TODO(kiro-reasoning): Kiro supports
                                    Claude Opus 4.7 with extended thinking
                                    among other reasoning-capable models,
                                    but the session JSONL only persists
                                    text + toolUse blocks under
                                    ``AssistantMessage.content``. There is
                                    no ``reasoning`` / ``thinking`` envelope
                                    or content kind in observed data.
                                    Re-evaluate when Kiro starts emitting
                                    a reasoning block kind.
  - tool calls + observations     ✓ (``toolUse`` paired with ``toolResult``
                                    via ``toolUseId``)
  - sub-agents (inline output)    ✓ The ``subagent`` tool's
                                    ``toolResult.content[0].data`` carries
                                    the full child report as a single text
                                    block. We synthesise a 2-step child
                                    Trajectory (objective + report) so the
                                    UI can navigate down. The child's own
                                    Steps aren't recoverable — Kiro doesn't
                                    persist them — so the synthetic shape
                                    is the best we can do.
  - multimodal images (inline)    ✓ ``image`` content blocks carry a raw
                                    byte array under
                                    ``data.source.data`` (Uint8Array). We
                                    encode to base64 for ATIF and detect
                                    the mime via ``data.format`` (``png``
                                    is the universal default).
  - compaction                    ✓ ``kind: Compaction`` envelope holds
                                    ``data.summary`` rich text. Triggered
                                    by ``/compact`` or context-overflow
                                    auto-compaction (Kiro CLI 1.x feature).
  - skills                        ✗ // TODO(kiro-skills): Kiro's Skills
                                    activate by description-match against
                                    the user request and are loaded into
                                    the system prompt. There is no
                                    ``skill``/``Skill`` tool name in
                                    observed data, and the session JSONL
                                    has no marker indicating which skill
                                    (if any) was active for a given turn.
                                    Re-evaluate if Kiro adds a skill-
                                    activation event kind.
  - persistent output files       ✗ no large-output split.
  - continuation refs (prev/next) ✗ no resume-from-prior workflow.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import BaseParser
from vibelens.ingest.parsers.helpers import (
    attach_subagent_ref,
    build_multimodal_message,
    iter_jsonl_safe,
    make_compaction_step,
)
from vibelens.models.enums import AgentType, ContentType, StepSource
from vibelens.models.trajectories import (
    Agent,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
    TrajectoryRef,
)
from vibelens.models.trajectories.content import Base64Source, ContentPart
from vibelens.utils import get_logger, parse_iso_timestamp

logger = get_logger(__name__)

# Tool name that spawns Kiro sub-agents. Mirrors Gemini's
# ``codebase_investigator`` pattern: the spawn output is delivered inline
# in the ToolResults envelope rather than as a separate session file.
_SUBAGENT_TOOL_NAME = "subagent"


class KiroParser(BaseParser):
    """Parser for Kiro CLI's JSONL+JSON session format."""

    AGENT_TYPE = AgentType.KIRO
    LOCAL_DATA_DIR: Path | None = Path.home() / ".kiro"
    # Session ids are UUIDs (filename stem of <sid>.jsonl) — already unique.
    NAMESPACE_SESSION_IDS = False

    # ---- Discovery ----
    def discover_session_files(self, data_dir: Path) -> list[Path]:
        """Return all ``<sid>.jsonl`` files under ``sessions/cli/``.

        The sibling ``<sid>.json`` is a metadata snapshot read on demand
        in :meth:`_extract_metadata`; only the JSONL is the discovery target.
        """
        cli_dir = data_dir / "sessions" / "cli"
        if not cli_dir.is_dir():
            return []
        return sorted(cli_dir.glob("*.jsonl"))

    def get_session_files(self, session_file: Path) -> list[Path]:
        """Track both the JSONL and the paired snapshot for cache invalidation."""
        files = [session_file]
        snapshot = session_file.with_suffix(".json")
        if snapshot.is_file():
            files.append(snapshot)
        return files

    # ---- 4-stage parsing ----
    def _decode_file(self, file_path: Path, diagnostics: DiagnosticsCollector) -> _KiroRaw | None:
        """Read JSONL events + paired snapshot in one pass."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read Kiro session %s: %s", file_path, exc)
            return None
        events = list(iter_jsonl_safe(content, diagnostics=diagnostics))
        if not events:
            return None
        snapshot: dict | None = None
        snapshot_path = file_path.with_suffix(".json")
        if snapshot_path.is_file():
            try:
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                snapshot = None
        return _KiroRaw(events=events, snapshot=snapshot)

    def _extract_metadata(
        self, raw: _KiroRaw, file_path: Path, diagnostics: DiagnosticsCollector
    ) -> Trajectory | None:
        """Build the trajectory header from the snapshot when available."""
        snapshot = raw.snapshot or {}
        session_id = snapshot.get("session_id") or file_path.stem
        agent_name = (snapshot.get("session_state") or {}).get("agent_name") or None
        model_info = (
            (snapshot.get("session_state") or {}).get("rts_model_state", {}).get("model_info", {})
        )
        model_id = model_info.get("model_id") if isinstance(model_info, dict) else None
        return Trajectory(
            session_id=session_id,
            agent=self.build_agent(model_name=model_id),
            project_path=snapshot.get("cwd") or None,
            created_at=_parse_kiro_timestamp(snapshot.get("created_at")),
            updated_at=_parse_kiro_timestamp(snapshot.get("updated_at")),
            extra=_build_traj_extra(snapshot, agent_name),
        )

    def _build_steps(
        self,
        raw: _KiroRaw,
        traj: Trajectory,
        file_path: Path,
        diagnostics: DiagnosticsCollector,
    ) -> list[Step]:
        """Walk JSONL events, emit ATIF Steps. Tool results are paired by toolUseId.

        Pre-scan ``ToolResults`` envelopes by ``toolUseId`` so the assistant
        turn that originated the call gets its observation attached in O(1).
        """
        results_by_id = _index_tool_results(raw.events)
        steps: list[Step] = []
        for entry in raw.events:
            kind = entry.get("kind")
            data = entry.get("data") or {}
            timestamp = _parse_kiro_meta_timestamp(data)

            if kind == "Prompt":
                steps.append(_build_user_step(entry, data, timestamp))
            elif kind == "AssistantMessage":
                step = _build_assistant_step(entry, data, results_by_id, timestamp, diagnostics)
                if step is not None:
                    steps.append(step)
            elif kind == "ToolResults":
                # Already consumed via the pre-scan; standalone tool steps
                # would duplicate the assistant-side observation.
                continue
            elif kind == "Compaction":
                steps.append(
                    make_compaction_step(
                        step_id=data.get("message_id") or str(uuid4()),
                        timestamp=timestamp,
                        message=(data.get("summary") or "").strip() or "[Context compacted]",
                    )
                )
            else:
                diagnostics.record_skip(f"unknown kiro envelope kind {kind!r}")
        return steps

    def _load_subagents(self, main: Trajectory, file_path: Path) -> list[Trajectory]:
        """Synthesise child trajectories from inline ``subagent`` tool results.

        Kiro's ``subagent`` tool is similar to Gemini's
        ``codebase_investigator``: the entire child run (including its own
        tools, intermediate steps, etc.) is collapsed into a single text
        report on the parent's tool result. We can't reconstruct the
        child's individual Steps — Kiro never persists them — but we still
        build a 2-step Trajectory (objective + report) so the UI can
        navigate to the report.
        """
        children: list[Trajectory] = []
        for step in main.steps:
            if step.observation is None:
                continue
            for tool_call, obs_result in zip(
                step.tool_calls or [], step.observation.results, strict=False
            ):
                if tool_call.function_name != _SUBAGENT_TOOL_NAME:
                    continue
                child = _build_inline_subagent(
                    main_session_id=main.session_id,
                    tool_call=tool_call,
                    obs_result=obs_result,
                    main_model=main.agent.model_name if main.agent else None,
                    parent_step_timestamp=step.timestamp,
                )
                if child is None:
                    continue
                attach_subagent_ref(main.steps, tool_call.tool_call_id, child.session_id)
                children.append(child)
        return children


# ---- Module helpers ----


class _KiroRaw:
    """Stage-1 output: decoded JSONL events plus the paired snapshot dict.

    Carrying both through the pipeline avoids re-reading the snapshot file
    in stages 2 and 3.
    """

    __slots__ = ("events", "snapshot")

    def __init__(self, events: list[dict], snapshot: dict | None) -> None:
        self.events = events
        self.snapshot = snapshot


def _index_tool_results(events: list[dict]) -> dict[str, dict]:
    """Build ``toolUseId -> toolResult-data`` map from ToolResults envelopes."""
    out: dict[str, dict] = {}
    for entry in events:
        if entry.get("kind") != "ToolResults":
            continue
        for c in entry.get("data", {}).get("content", []) or []:
            if isinstance(c, dict) and c.get("kind") == "toolResult":
                inner = c.get("data") or {}
                tid = inner.get("toolUseId")
                if tid:
                    out[tid] = inner
    return out


def _build_user_step(entry: dict, data: dict, timestamp: datetime | None) -> Step:
    """Build a USER Step from a ``Prompt`` envelope."""
    text_parts: list[str] = []
    image_parts: list[ContentPart] = []
    for c in data.get("content", []) or []:
        if not isinstance(c, dict):
            continue
        ck = c.get("kind")
        if ck == "text":
            text = c.get("data") or ""
            if isinstance(text, str) and text:
                text_parts.append(text)
        elif ck == "image":
            image_part = _image_block_to_content_part(c.get("data") or {})
            if image_part is not None:
                image_parts.append(image_part)
    return Step(
        step_id=data.get("message_id") or str(uuid4()),
        source=StepSource.USER,
        message=build_multimodal_message("\n".join(text_parts), image_parts),
        timestamp=timestamp,
    )


def _build_assistant_step(
    entry: dict,
    data: dict,
    results_by_id: dict[str, dict],
    timestamp: datetime | None,
    diagnostics: DiagnosticsCollector,
) -> Step | None:
    """Build an AGENT Step from an ``AssistantMessage`` envelope.

    Pairs each ``toolUse`` with its result via ``toolUseId``. Steps with
    no text and no tool calls are dropped (Kiro emits a placeholder
    ``text=""`` block alongside every toolUse — that alone isn't a real
    turn).
    """
    text_parts: list[str] = []
    image_parts: list[ContentPart] = []
    tool_calls: list[ToolCall] = []
    obs_results: list[ObservationResult] = []
    for c in data.get("content", []) or []:
        if not isinstance(c, dict):
            continue
        ck = c.get("kind")
        if ck == "text":
            text = c.get("data") or ""
            if isinstance(text, str) and text:
                text_parts.append(text)
        elif ck == "image":
            image_part = _image_block_to_content_part(c.get("data") or {})
            if image_part is not None:
                image_parts.append(image_part)
        elif ck == "toolUse":
            tc, obs = _build_tool_pair(c.get("data") or {}, results_by_id, diagnostics)
            if tc is not None:
                tool_calls.append(tc)
            if obs is not None:
                obs_results.append(obs)

    text = "\n".join(text_parts).strip()
    if not text and not image_parts and not tool_calls:
        return None
    return Step(
        step_id=data.get("message_id") or str(uuid4()),
        source=StepSource.AGENT,
        message=build_multimodal_message(text, image_parts),
        tool_calls=tool_calls,
        observation=Observation(results=obs_results) if obs_results else None,
        timestamp=timestamp,
    )


def _build_tool_pair(
    tool_use_data: dict,
    results_by_id: dict[str, dict],
    diagnostics: DiagnosticsCollector,
) -> tuple[ToolCall | None, ObservationResult | None]:
    """Convert a ``toolUse`` block into ``(ToolCall, ObservationResult)``.

    Pairs against the pre-scanned ``results_by_id``. The result block
    carries an explicit ``status`` field (``success`` / ``error``) that
    we use as the canonical error signal.
    """
    call_id = tool_use_data.get("toolUseId") or ""
    function_name = tool_use_data.get("name") or ""
    diagnostics.record_tool_call()
    tc = ToolCall(
        tool_call_id=call_id,
        function_name=function_name,
        arguments=tool_use_data.get("input"),
    )
    result = results_by_id.get(call_id) if call_id else None
    if result is None:
        if call_id:
            diagnostics.record_orphaned_call(call_id)
        return tc, None
    diagnostics.record_tool_result()
    obs = ObservationResult(
        source_call_id=call_id,
        content=_format_tool_result_content(result.get("content")),
        is_error=result.get("status") == "error",
    )
    return tc, obs


def _format_tool_result_content(content: Any) -> str:
    """Coerce Kiro tool-result content array into a string body.

    Tool results carry mixed-kind blocks: ``text`` (string), ``json`` (dict
    serialised), or ``bytes``. We render text directly, dump JSON, and
    surface a placeholder for binary so the user still sees that something
    came back.
    """
    if not isinstance(content, list):
        return "" if content is None else str(content)
    chunks: list[str] = []
    for c in content:
        if not isinstance(c, dict):
            continue
        ck = c.get("kind")
        data = c.get("data")
        if ck == "text":
            if isinstance(data, str):
                chunks.append(data)
        elif ck == "json":
            chunks.append(json.dumps(data, ensure_ascii=False) if data is not None else "")
        elif ck == "bytes":
            chunks.append("[binary tool output]")
        else:
            # Unknown kind — preserve repr so it doesn't silently disappear.
            chunks.append(json.dumps({"kind": ck, "data": data}, ensure_ascii=False))
    return "\n".join(chunks)


def _image_block_to_content_part(data: dict) -> ContentPart | None:
    """Decode a Kiro ``image`` block into an inline image ContentPart.

    Kiro stores images as ``{format: "png", source: {kind: "bytes", data:
    [<int>, ...]}}`` — a list of integer byte values rather than base64.
    We re-encode to base64 for ATIF compatibility. Unknown ``format``
    values are mapped through ``image/<format>``.
    """
    fmt = data.get("format") or "png"
    source = data.get("source") or {}
    if not isinstance(source, dict) or source.get("kind") != "bytes":
        return None
    byte_array = source.get("data")
    if not isinstance(byte_array, list):
        return None
    try:
        raw = bytes(byte_array)
    except (TypeError, ValueError):
        return None
    return ContentPart(
        type=ContentType.IMAGE,
        source=Base64Source(
            media_type=f"image/{fmt}",
            base64=base64.b64encode(raw).decode("ascii"),
        ),
    )


def _build_inline_subagent(
    main_session_id: str,
    tool_call: ToolCall,
    obs_result: ObservationResult,
    main_model: str | None,
    parent_step_timestamp: datetime | None,
) -> Trajectory | None:
    """Synthesise a 2-step Trajectory from an inline ``subagent`` tool call.

    Mirrors Gemini's inline sub-agent pattern. The objective comes from the
    ToolCall arguments (``task`` field — Kiro's dedicated key); the report
    is the spawning observation's content. Returns ``None`` when the
    report is missing — without it the child has nothing meaningful to
    show.
    """
    report_text = (obs_result.content or "").strip()
    if not report_text:
        return None
    args = tool_call.arguments if isinstance(tool_call.arguments, dict) else {}
    objective = (
        args.get("task")
        or args.get("__tool_use_purpose")
        or f"(spawned via {tool_call.function_name}; objective not recorded by Kiro)"
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
        agent=Agent(name=AgentType.KIRO.value, model_name=main_model),
        parent_trajectory_ref=TrajectoryRef(session_id=main_session_id),
        steps=steps,
        extra={
            "agent_role": tool_call.function_name,
            "spawn_tool_call_id": tool_call.tool_call_id,
            "synthesized_inline": True,
        },
    )


def _build_traj_extra(snapshot: dict, agent_name: str | None) -> dict | None:
    """Build trajectory-level ``extra`` from snapshot fields.

    Only carries keys that downstream consumers might want and that aren't
    already promoted to typed fields. Empty / missing fields are dropped.
    """
    extra: dict[str, Any] = {}
    if agent_name:
        extra["kiro_agent_name"] = agent_name
    if title := snapshot.get("title"):
        extra["title"] = title
    rts = (snapshot.get("session_state") or {}).get("rts_model_state") or {}
    if isinstance(rts, dict):
        usage_pct = rts.get("context_usage_percentage")
        if usage_pct is not None:
            extra["context_usage_percentage"] = usage_pct
        info = rts.get("model_info")
        if isinstance(info, dict) and info.get("context_window_tokens"):
            extra["context_window_tokens"] = info["context_window_tokens"]
    return extra or None


def _parse_kiro_timestamp(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp. Returns None on missing / malformed input."""
    if not value:
        return None
    return parse_iso_timestamp(value)


def _parse_kiro_meta_timestamp(data: dict) -> datetime | None:
    """Parse ``data.meta.timestamp`` (unix seconds) into a datetime."""
    meta = data.get("meta") if isinstance(data, dict) else None
    if not isinstance(meta, dict):
        return None
    ts = meta.get("timestamp")
    if not isinstance(ts, (int, float)):
        return None
    try:
        from datetime import timezone as _tz

        return datetime.fromtimestamp(ts, tz=_tz.utc)
    except (TypeError, ValueError, OSError):
        return None
