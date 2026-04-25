"""Dataclaw JSONL format parser.

Parses HuggingFace dataclaw datasets that contain Claude Code conversation
histories exported as structured JSONL.

Unlike the local CLI parsers (claude_code, codex, gemini) where each file
holds one session, dataclaw packs **one complete session per JSONL line**.
Each line is a self-contained JSON object with session metadata, message
array, and pre-computed stats — so ``parse_file`` can return multiple
Trajectory objects from a single file.

The format is a third-party export format (dataclaw tool), not a native
agent format, so field names and structures differ from all three CLI
agents.  Tool calls use a flat ``tool_uses`` array without result data
(dataclaw strips tool outputs during privacy scrubbing).
"""

from collections.abc import Iterator
from pathlib import Path

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import BaseParser
from vibelens.ingest.parsers.helpers import ROLE_TO_SOURCE, iter_jsonl_safe
from vibelens.models.enums import AgentType, StepSource
from vibelens.models.trajectories import Step, ToolCall, Trajectory
from vibelens.utils import (
    coerce_to_string,
    deterministic_id,
    get_logger,
    parse_iso_timestamp,
)

logger = get_logger(__name__)


class DataclawParser(BaseParser):
    """Parser for dataclaw-exported conversation datasets."""

    AGENT_TYPE = AgentType.DATACLAW

    def parse(self, file_path: Path) -> list[Trajectory]:
        """Parse a dataclaw ``conversations.jsonl`` file: one session per line."""
        return list(self.iter_trajectories(file_path))

    def iter_trajectories(self, file_path: Path) -> Iterator[Trajectory]:
        """Yield trajectories one at a time for constant-memory processing of large datasets."""
        diagnostics = DiagnosticsCollector()
        for record in iter_jsonl_safe(file_path, diagnostics=diagnostics):
            try:
                traj = self._record_to_trajectory(record)
            except (KeyError, TypeError, ValueError):
                logger.warning("Failed to parse dataclaw session", exc_info=True)
                continue
            if traj is not None and traj.steps:
                yield self._finalize(traj, diagnostics)

    def _record_to_trajectory(self, record: dict) -> Trajectory | None:
        """Convert one ``conversations.jsonl`` line into a Trajectory header + steps."""
        # Dataclaw may omit session_id; derive a deterministic one from
        # project + start_time so re-parses are stable.
        session_id = record.get("session_id") or deterministic_id(
            "sess", record.get("project", ""), record.get("start_time", "")
        )
        model = record.get("model") or None
        steps = _build_steps(record.get("messages", []), session_id, model or "")
        return Trajectory(
            session_id=session_id,
            agent=self.build_agent(model_name=model),
            project_path=record.get("project") or None,
            steps=steps,
            extra={"source_type": "huggingface"},
        )


def _build_steps(raw_messages: list, session_id: str, session_model: str) -> list[Step]:
    """Convert dataclaw message dicts into Step objects.

    Dataclaw does not include per-message model or token data — the model
    is session-level and only applied to agent steps.  Step IDs
    are generated since dataclaw strips original IDs for privacy.
    """
    steps = []
    for idx, raw in enumerate(raw_messages):
        if not isinstance(raw, dict):
            continue

        role = raw.get("role", "")
        if role not in ("user", "assistant"):
            continue

        source = ROLE_TO_SOURCE.get(role, StepSource.USER)
        content = coerce_to_string(raw.get("content", ""))
        reasoning_content = raw.get("thinking") or None
        timestamp = parse_iso_timestamp(raw.get("timestamp"))

        raw_tool_uses = raw.get("tool_uses", [])
        tool_calls = _build_tool_calls(raw_tool_uses, session_id, idx)

        steps.append(
            Step(
                step_id=deterministic_id("msg", session_id, str(idx), role),
                source=source,
                message=content,
                reasoning_content=reasoning_content,
                model_name=(session_model or None) if role == "assistant" else None,
                timestamp=timestamp,
                tool_calls=tool_calls,
            )
        )
    return steps


def _build_tool_calls(raw_tool_uses: list, session_id: str, msg_idx: int) -> list[ToolCall]:
    """Convert dataclaw tool_uses into ToolCall objects.

    Dataclaw only records tool name and input; outputs are stripped
    during privacy scrubbing, so observation stays None on the parent step.
    """
    calls = []
    for tc_idx, tool in enumerate(raw_tool_uses):
        if not isinstance(tool, dict):
            continue
        tool_name = tool.get("tool", "unknown")
        calls.append(
            ToolCall(
                tool_call_id=deterministic_id(
                    "tc", session_id, str(msg_idx), tool_name, str(tc_idx)
                ),
                function_name=tool_name,
                arguments=tool.get("input"),
            )
        )
    return calls
