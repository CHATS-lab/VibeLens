"""OpenClaw JSONL format parser.

OpenClaw stores each conversation event as a JSONL line with a top-level
``type``. ``type: "message"`` events wrap the actual chat message (its role
distinguishes user / assistant / toolResult). Other event types carry session
metadata (``session``, ``model_change``, ``custom: model-snapshot``).

Format quirks vs Claude Code:
  - Wrapped envelope: ``{"type": "message", "message": {"role": "..."}}``.
  - Tool calls are content blocks ``{"type": "toolCall", ...}`` (not ``tool_use``).
  - Tool results are separate ``role: "toolResult"`` messages linked by ``toolCallId``.
  - Usage uses short keys (``input``/``output``/``cacheRead``/``cacheWrite``) and
    cost is in source under ``usage.cost.total``.
"""

import json
from pathlib import Path
from uuid import uuid4

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import BaseParser
from vibelens.ingest.parsers.helpers import ROLE_TO_SOURCE, iter_jsonl_safe
from vibelens.models.enums import AgentType, StepSource
from vibelens.models.trajectories import (
    Agent,
    FinalMetrics,
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
)
from vibelens.utils import coerce_to_string, get_logger, normalize_timestamp

logger = get_logger(__name__)

SESSIONS_INDEX_FILENAME = "sessions.json"

# Non-session JSONL files that may share the sessions/ directory.
_EXCLUDED_SUFFIXES = ("-clean.jsonl",)


class OpenClawParser(BaseParser):
    """Parser for OpenClaw's native JSONL session format."""

    AGENT_TYPE = AgentType.OPENCLAW
    LOCAL_DATA_DIR: Path | None = Path.home() / ".openclaw"

    # ---- Discovery ----
    def discover_session_files(self, data_dir: Path) -> list[Path]:
        """Scan ``agents/*/sessions/*.jsonl`` excluding the index + clean files."""
        agents_dir = data_dir / "agents"
        if not agents_dir.is_dir():
            return []
        files: list[Path] = []
        for jsonl_file in sorted(agents_dir.rglob("*.jsonl")):
            if jsonl_file.name == SESSIONS_INDEX_FILENAME:
                continue
            if any(jsonl_file.name.endswith(suffix) for suffix in _EXCLUDED_SUFFIXES):
                continue
            if "sessions" not in jsonl_file.parts:
                continue
            files.append(jsonl_file)
        return files

    # ---- Indexing ----
    def parse_session_index(self, data_dir: Path) -> list[Trajectory] | None:
        """Build skeleton trajectories from ``sessions.json`` for fast listing."""
        index_file = data_dir / "agents" / "main" / "sessions" / SESSIONS_INDEX_FILENAME
        if not index_file.exists():
            return None
        try:
            raw = json.loads(index_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.debug("Cannot read sessions.json at %s", index_file)
            return None
        if not isinstance(raw, dict):
            return None

        trajectories: list[Trajectory] = []
        for entry in raw.values():
            if not isinstance(entry, dict):
                continue
            session_id = entry.get("sessionId")
            if not session_id:
                continue
            timestamp = normalize_timestamp(entry.get("updatedAt"))
            trajectories.append(
                Trajectory(
                    session_id=session_id,
                    agent=Agent(name=self.AGENT_TYPE.value),
                    steps=[
                        Step(
                            step_id="index-0",
                            source=StepSource.USER,
                            message="",
                            timestamp=timestamp,
                        )
                    ],
                    final_metrics=FinalMetrics(),
                    extra={"is_skeleton": True},
                )
            )
        return trajectories or None

    # ---- parsing ----
    def _decode_file(self, file_path: Path, diagnostics: DiagnosticsCollector) -> list[dict] | None:
        """Stage 1: read + JSONL-parse the file into entries."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read OpenClaw file %s: %s", file_path, exc)
            return None
        entries = list(iter_jsonl_safe(content, diagnostics=diagnostics))
        return entries or None

    def _extract_metadata(
        self, raw: list[dict], file_path: Path, diagnostics: DiagnosticsCollector
    ) -> Trajectory | None:
        """Stage 2: pull session id / model / cwd from header events."""
        meta = _extract_session_meta(raw)
        session_id = meta["session_id"] or file_path.stem or str(uuid4())
        return Trajectory(
            session_id=session_id,
            agent=self.build_agent(model_name=meta["model"]),
            project_path=meta["cwd"],
        )

    def _build_steps(
        self, raw: list[dict], traj: Trajectory, file_path: Path, diagnostics: DiagnosticsCollector
    ) -> list[Step]:
        """Stage 3: build steps; pair toolCall blocks with their toolResult messages."""
        message_entries = [e for e in raw if e.get("type") == "message"]
        tool_result_map = _collect_tool_results(message_entries)
        seen_call_ids: set[str] = set()

        steps: list[Step] = []
        for entry in message_entries:
            msg = entry.get("message", {})
            role = msg.get("role", "")
            # toolResult messages are consumed via the pre-scan map, not as steps.
            if role == "toolResult":
                continue
            source = ROLE_TO_SOURCE.get(role)
            if source is None:
                continue

            text, reasoning, tool_calls = _decompose_content(msg.get("content", ""))
            metrics = _build_metrics(msg.get("usage")) if source == StepSource.AGENT else None
            observation = _build_observation(tool_calls, tool_result_map)

            for tc in tool_calls:
                if tc.tool_call_id:
                    seen_call_ids.add(tc.tool_call_id)
                    diagnostics.record_tool_call()

            steps.append(
                Step(
                    step_id=entry.get("id", str(uuid4())),
                    source=source,
                    message=text,
                    reasoning_content=reasoning,
                    model_name=msg.get("model") or None,
                    timestamp=normalize_timestamp(entry.get("timestamp") or msg.get("timestamp")),
                    metrics=metrics,
                    tool_calls=tool_calls,
                    observation=observation,
                )
            )

        for tc_id in seen_call_ids - tool_result_map.keys():
            diagnostics.record_orphaned_call(tc_id)
        for tr_id in tool_result_map.keys() - seen_call_ids:
            diagnostics.record_orphaned_result(tr_id)
        return steps


def _extract_session_meta(entries: list[dict]) -> dict:
    """Scan entries for session_id / cwd / model. Header events can be interleaved
    with early ``delivery-mirror`` system messages, so we don't break at first message.
    The first real assistant message's ``model`` is the last-resort fallback.
    """
    meta: dict = {"session_id": None, "cwd": None, "model": None}
    first_assistant_model: str | None = None

    for entry in entries:
        event_type = entry.get("type")
        if event_type == "session":
            meta["session_id"] = entry.get("id")
            meta["cwd"] = entry.get("cwd")
        elif event_type == "model_change":
            meta["model"] = _format_model(entry.get("provider"), entry.get("modelId"))
        elif event_type == "custom" and entry.get("customType") == "model-snapshot":
            data = entry.get("data", {})
            if not meta["model"] and data.get("modelId"):
                meta["model"] = _format_model(data.get("provider"), data["modelId"])
        elif event_type == "message" and not first_assistant_model:
            msg = entry.get("message", {})
            model_name = msg.get("model", "")
            # ``delivery-mirror`` is a placeholder for non-LLM events; ignore it.
            if msg.get("role") == "assistant" and model_name and model_name != "delivery-mirror":
                first_assistant_model = model_name

    if not meta["model"] and first_assistant_model:
        meta["model"] = first_assistant_model
    return meta


def _collect_tool_results(message_entries: list[dict]) -> dict[str, dict]:
    """Index ``role: toolResult`` messages by their ``toolCallId``."""
    results: dict[str, dict] = {}
    for entry in message_entries:
        msg = entry.get("message", {})
        if msg.get("role") != "toolResult":
            continue
        tool_call_id = msg.get("toolCallId", "")
        if not tool_call_id:
            continue
        results[tool_call_id] = {
            "output": coerce_to_string(msg.get("content", "")),
            "is_error": bool(msg.get("isError", False)),
            "details": msg.get("details") if isinstance(msg.get("details"), dict) else None,
        }
    return results


def _decompose_content(raw_content: str | list) -> tuple[str, str | None, list[ToolCall]]:
    """Split content blocks into (text, reasoning, tool_calls)."""
    if isinstance(raw_content, str):
        return raw_content.strip(), None, []
    if not isinstance(raw_content, list):
        return "", None, []

    text_parts: list[str] = []
    thinking_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in raw_content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type", "text")
        if block_type == "text" and block.get("text"):
            text_parts.append(block["text"])
        elif block_type == "thinking" and block.get("thinking"):
            thinking_parts.append(block["thinking"])
        elif block_type == "toolCall":
            tool_calls.append(
                ToolCall(
                    tool_call_id=block.get("id", ""),
                    function_name=block.get("name", ""),
                    arguments=block.get("arguments"),
                )
            )
    return (
        "\n\n".join(text_parts).strip(),
        "\n\n".join(thinking_parts).strip() or None,
        tool_calls,
    )


def _format_model(provider: str | None, model_id: str | None) -> str | None:
    """Combine provider + modelId into ``provider/modelId`` (or just modelId)."""
    if not model_id:
        return None
    return f"{provider}/{model_id}" if provider else model_id


def _build_metrics(usage: dict | None) -> Metrics | None:
    """Map OpenClaw usage shape to Metrics. Cost lives in source at ``usage.cost.total``."""
    if not usage:
        return None
    cost_data = usage.get("cost")
    return Metrics.from_tokens(
        input_tokens=usage.get("input") or 0,
        output_tokens=usage.get("output") or 0,
        cache_read_tokens=usage.get("cacheRead") or 0,
        cache_write_tokens=usage.get("cacheWrite") or 0,
        cost_usd=cost_data.get("total") if isinstance(cost_data, dict) else None,
    )


def _build_observation(
    tool_calls: list[ToolCall], tool_result_map: dict[str, dict]
) -> Observation | None:
    """Build an Observation by pairing each tool_call with its pre-scanned result."""
    if not tool_calls:
        return None
    obs_results: list[ObservationResult] = []
    for tc in tool_calls:
        result = tool_result_map.get(tc.tool_call_id)
        if not result:
            continue
        obs_results.append(
            ObservationResult(
                source_call_id=tc.tool_call_id,
                content=result["output"],
                is_error=result["is_error"],
                extra=result.get("details"),
            )
        )
    return Observation(results=obs_results) if obs_results else None
