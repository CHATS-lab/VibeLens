"""Cross-parser format fingerprinting and auto-detection.

Probes a file's first few lines to determine which agent format it
uses, returning confidence scores so callers can select the right
parser automatically.
"""

import json
from pathlib import Path

from pydantic import BaseModel, Field

from vibelens.models.trajectories import Trajectory

MAX_PROBE_LINES = 10
MAX_PROBE_BYTES = 8192

_MIN_CONFIDENCE = 0.5


class FormatMatch(BaseModel):
    """A candidate format match with confidence score."""

    format_name: str = Field(
        description="Format identifier: claude_code, codex, gemini, dataclaw."
    )
    confidence: float = Field(description="Confidence from 0.0 to 1.0.")
    parser_class: str = Field(description="Parser class name to instantiate.")


def fingerprint_file(file_path: Path) -> list[FormatMatch]:
    """Probe a file and return ranked format matches.

    Args:
        file_path: Path to the data file.

    Returns:
        List of FormatMatch sorted by confidence descending.
    """
    if not file_path.exists():
        return []

    suffix = file_path.suffix.lower()
    if suffix == ".json":
        return _probe_json(file_path)
    if suffix == ".jsonl":
        return _probe_jsonl(file_path)
    return []


def parse_auto(file_path: Path) -> list[Trajectory]:
    """Auto-detect format and parse a file.

    Args:
        file_path: Path to the data file.

    Returns:
        List of Trajectory objects.

    Raises:
        ValueError: If no format matches with >= 0.5 confidence.
    """
    matches = fingerprint_file(file_path)
    if not matches or matches[0].confidence < _MIN_CONFIDENCE:
        best = f"{matches[0].format_name} ({matches[0].confidence:.2f})" if matches else "none"
        raise ValueError(f"Cannot auto-detect format for {file_path}: best match {best}")

    parser = _instantiate_parser(matches[0].parser_class)
    return parser.parse_file(file_path)


def _probe_json(file_path: Path) -> list[FormatMatch]:
    """Probe a JSON file for Gemini format signatures."""
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(data, dict):
        return []

    matches: list[FormatMatch] = []

    gemini_score = _score_gemini(data)
    if gemini_score > 0:
        matches.append(
            FormatMatch(
                format_name="gemini",
                confidence=min(gemini_score, 1.0),
                parser_class="GeminiParser",
            )
        )

    return matches


def _score_gemini(data: dict) -> float:
    """Score a JSON object for Gemini CLI format signatures.

    Args:
        data: Parsed JSON root object.

    Returns:
        Confidence score from 0.0 to 1.0.
    """
    score = 0.0
    if "sessionId" in data:
        score += 0.4
    if "messages" in data and isinstance(data.get("messages"), list):
        score += 0.2
    messages = data.get("messages", [])
    if isinstance(messages, list) and messages:
        first = messages[0] if isinstance(messages[0], dict) else {}
        if first.get("type") in ("user", "gemini"):
            score += 0.3
    if "startTime" in data:
        score += 0.1
    return score


def _probe_jsonl(file_path: Path) -> list[FormatMatch]:
    """Probe a JSONL file for Claude Code, Codex, or Dataclaw format."""
    lines = _read_probe_lines(file_path)
    if not lines:
        return []

    scores: dict[str, float] = {"claude_code": 0.0, "codex": 0.0, "dataclaw": 0.0}

    for line_data in lines:
        if not isinstance(line_data, dict):
            continue
        _score_claude_code(line_data, scores)
        _score_codex(line_data, scores)
        _score_dataclaw(line_data, scores)

    matches = [
        FormatMatch(
            format_name=name, confidence=min(score, 1.0), parser_class=_PARSER_CLASSES[name]
        )
        for name, score in scores.items()
        if score > 0
    ]
    matches.sort(key=lambda m: m.confidence, reverse=True)
    return matches


def _read_probe_lines(file_path: Path) -> list[dict]:
    """Read up to MAX_PROBE_LINES parsed JSON dicts from a JSONL file."""
    results: list[dict] = []
    try:
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                if len(results) >= MAX_PROBE_LINES:
                    break
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, dict):
                        results.append(parsed)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return results


def _score_claude_code(line_data: dict, scores: dict[str, float]) -> None:
    """Score a line for Claude Code format signatures."""
    entry_type = line_data.get("type", "")
    if entry_type in ("user", "assistant"):
        scores["claude_code"] += 0.25
    if "sessionId" in line_data:
        scores["claude_code"] += 0.15
    if "uuid" in line_data:
        scores["claude_code"] += 0.1
    if "message" in line_data and isinstance(line_data.get("message"), dict):
        scores["claude_code"] += 0.1


def _score_codex(line_data: dict, scores: dict[str, float]) -> None:
    """Score a line for Codex format signatures."""
    entry_type = line_data.get("type", "")
    if entry_type in ("session_meta", "response_item", "turn_context", "event_msg"):
        scores["codex"] += 0.3
    if "payload" in line_data and isinstance(line_data.get("payload"), dict):
        scores["codex"] += 0.15
    if "timestamp" in line_data and isinstance(line_data.get("timestamp"), str):
        scores["codex"] += 0.05


def _score_dataclaw(line_data: dict, scores: dict[str, float]) -> None:
    """Score a line for Dataclaw format signatures."""
    if "session_id" in line_data:
        scores["dataclaw"] += 0.2
    if "messages" in line_data and isinstance(line_data.get("messages"), list):
        scores["dataclaw"] += 0.3
    if "stats" in line_data and isinstance(line_data.get("stats"), dict):
        scores["dataclaw"] += 0.2
    if "project" in line_data:
        scores["dataclaw"] += 0.1


_PARSER_CLASSES: dict[str, str] = {
    "claude_code": "ClaudeCodeParser",
    "codex": "CodexParser",
    "gemini": "GeminiParser",
    "dataclaw": "DataclawParser",
}


def _instantiate_parser(class_name: str):
    """Instantiate a parser by class name.

    Args:
        class_name: Parser class name string.

    Returns:
        Parser instance.
    """
    from vibelens.ingest.parsers.claude_code import ClaudeCodeParser
    from vibelens.ingest.parsers.codex import CodexParser
    from vibelens.ingest.parsers.dataclaw import DataclawParser
    from vibelens.ingest.parsers.gemini import GeminiParser

    registry = {
        "ClaudeCodeParser": ClaudeCodeParser,
        "CodexParser": CodexParser,
        "GeminiParser": GeminiParser,
        "DataclawParser": DataclawParser,
    }
    return registry[class_name]()
