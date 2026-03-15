"""Format parsers for ingesting agent trajectory data.

Each parser normalises a vendor-specific session format into the unified
(SessionSummary, list[Message]) representation so downstream analytics
can treat all agent sources identically.

Supported formats:
    - Claude Code   — Anthropic JSONL (one event per line, tool results in adjacent messages)
    - Codex CLI     — OpenAI rollout JSONL (RolloutItem envelope, function_call pairs)
    - Gemini CLI    — Google session JSON (single file per session, embedded tool results)
    - Dataclaw      — HuggingFace export JSONL (one complete session per line)
"""

from vibelens.ingest.base import BaseParser
from vibelens.ingest.claude_code import ClaudeCodeParser, count_history_entries
from vibelens.ingest.codex import CodexParser
from vibelens.ingest.correlator import CorrelatedGroup, CorrelatedSession, correlate_sessions
from vibelens.ingest.dataclaw import DataclawParser
from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.fingerprint import FormatMatch, fingerprint_file, parse_auto
from vibelens.ingest.gemini import GeminiParser
from vibelens.ingest.phase_detector import PhaseSegment, SessionPhase, detect_phases
from vibelens.ingest.tool_graph import ToolDependencyGraph, ToolEdge, build_tool_graph
from vibelens.ingest.tool_normalizers import (
    categorize_tool,
    summarize_tool_input,
    summarize_tool_output,
)

__all__ = [
    "BaseParser",
    "ClaudeCodeParser",
    "CodexParser",
    "CorrelatedGroup",
    "CorrelatedSession",
    "DataclawParser",
    "DiagnosticsCollector",
    "FormatMatch",
    "GeminiParser",
    "PhaseSegment",
    "SessionPhase",
    "ToolDependencyGraph",
    "ToolEdge",
    "build_tool_graph",
    "categorize_tool",
    "count_history_entries",
    "correlate_sessions",
    "detect_phases",
    "fingerprint_file",
    "parse_auto",
    "summarize_tool_input",
    "summarize_tool_output",
]
