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

import json
from collections.abc import Iterator
from pathlib import Path

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import BaseParser
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Step, ToolCall, Trajectory
from vibelens.utils import coerce_to_string, deterministic_id, get_logger, parse_iso_timestamp

logger = get_logger(__name__)

# ATIF source mapping for dataclaw role names
_ROLE_TO_SOURCE = {"user": StepSource.USER, "assistant": StepSource.AGENT}

AGENT_NAME = "dataclaw"


class DataclawParser(BaseParser):
    """Parser for dataclaw-exported conversation datasets."""

    def parse(self, content: str, source_path: str | None = None) -> list[Trajectory]:
        """Parse dataclaw JSONL content into Trajectory objects.

        Args:
            content: Raw JSONL content (one session per line).
            source_path: Unused (dataclaw is self-contained).

        Returns:
            List of Trajectory objects, one per session.
        """
        collector = DiagnosticsCollector()
        trajectories = []
        for line in content.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            collector.total_lines += 1
            try:
                record = json.loads(stripped)
                collector.parsed_lines += 1
                trajectories.append(self.parse_session(record, collector))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                collector.record_skip("invalid record")
                continue
        return trajectories

    def parse_file(self, file_path: Path) -> list[Trajectory]:
        """Parse a dataclaw conversations.jsonl file.

        Args:
            file_path: Path to the conversations.jsonl file.

        Returns:
            List of Trajectory objects, one per session.
        """
        return list(self.iter_trajectories(file_path))

    def iter_trajectories(self, file_path: Path) -> Iterator[Trajectory]:
        """Yield trajectories one at a time for constant-memory processing.

        Args:
            file_path: Path to the conversations.jsonl file.

        Yields:
            Trajectory objects, one per valid session line.
        """
        collector = DiagnosticsCollector()
        for record in self.iter_jsonl_safe(file_path, diagnostics=collector):
            try:
                yield self.parse_session(record, collector)
            except (KeyError, TypeError, ValueError):
                logger.warning("Failed to parse dataclaw session", exc_info=True)
                continue

    def parse_session(
        self, record: dict, diagnostics: DiagnosticsCollector | None = None
    ) -> Trajectory:
        """Parse a single dataclaw session record into a Trajectory.

        Args:
            record: Parsed JSON object from a conversations.jsonl line.
            diagnostics: Optional collector for parse quality metrics.

        Returns:
            Trajectory with steps and metadata in extra.
        """
        # Dataclaw may omit session_id; derive a deterministic one from
        # project + start_time so parsing the same file twice yields the same ID.
        session_id = record.get("session_id") or deterministic_id(
            "sess", record.get("project", ""), record.get("start_time", "")
        )
        project = record.get("project", "")
        model = record.get("model", "")
        raw_messages = record.get("messages", [])
        steps = _build_steps(raw_messages, session_id, model)
        extra: dict | None = {"source_type": "huggingface"}
        if diagnostics:
            diag = diagnostics.to_diagnostics().model_dump()
            if any(v for v in diag.values()):
                extra["diagnostics"] = diag

        agent = self.build_agent(AGENT_NAME, model=model or None)
        return self.assemble_trajectory(
            session_id=session_id,
            agent=agent,
            steps=steps,
            project_path=project or None,
            extra=extra,
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

        source = _ROLE_TO_SOURCE.get(role, StepSource.USER)
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


def _build_tool_calls(
    raw_tool_uses: list, session_id: str, msg_idx: int
) -> list[ToolCall]:
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
