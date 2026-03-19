"""Format parsers for ingesting agent trajectory data.

Each parser normalises a vendor-specific session format into ATIF
Trajectory objects so downstream analytics can treat all agent
sources identically.

Supported formats:
    - Claude Code   — Anthropic JSONL (one event per line, tool results in adjacent messages)
    - Codex CLI     — OpenAI rollout JSONL (RolloutItem envelope, function_call pairs)
    - Gemini CLI    — Google session JSON (single file per session, embedded tool results)
    - Dataclaw      — HuggingFace export JSONL (one complete session per line)

Note: Analysis modules (correlator, phase_detector, tool_graph) are in
vibelens.analysis — import from there directly to avoid circular imports.
"""

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.fingerprint import FormatMatch, fingerprint_file, parse_auto
from vibelens.ingest.parsers import (
    BaseParser,
    ClaudeCodeParser,
    CodexParser,
    DataclawParser,
    GeminiParser,
    count_history_entries,
)

__all__ = [
    "BaseParser",
    "ClaudeCodeParser",
    "CodexParser",
    "DataclawParser",
    "DiagnosticsCollector",
    "FormatMatch",
    "GeminiParser",
    "count_history_entries",
    "fingerprint_file",
    "parse_auto",
]
