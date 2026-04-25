"""Tests for per-backend CLI output parsers.

Fixtures under ``tests/llm/fixtures/`` capture real stdout from each CLI
(installed ones via ``step 1`` of the plan; others synthesized from
documented examples). Each test feeds a fixture into its backend's
``_parse_output`` and asserts text, usage, model, and cost fields.
"""

from pathlib import Path

import pytest

from vibelens.config.settings import InferenceConfig
from vibelens.llm.backend import InferenceError
from vibelens.llm.backends.aider_cli import AiderCliBackend
from vibelens.llm.backends.amp_cli import AmpCliBackend
from vibelens.llm.backends.claude_cli import ClaudeCliBackend
from vibelens.llm.backends.codex_cli import CodexCliBackend
from vibelens.llm.backends.cursor_cli import CursorCliBackend
from vibelens.llm.backends.gemini_cli import GeminiCliBackend
from vibelens.llm.backends.kimi_cli import KimiCliBackend
from vibelens.llm.backends.openclaw_cli import OpenClawCliBackend
from vibelens.llm.backends.opencode_cli import OpenCodeCliBackend

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _cfg(model: str = "") -> InferenceConfig:
    """Minimal config for parser tests — only model matters."""
    return InferenceConfig(model=model)


def _load(name: str) -> str:
    """Read a fixture file as utf-8 text."""
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_claude_parses_envelope():
    """Claude emits a single JSON with result/usage/modelUsage/total_cost_usd."""
    backend = ClaudeCliBackend(config=_cfg())
    result = backend._parse_output(_load("claude_sample.json"), duration_ms=1000)
    assert result.text == "ok"
    assert result.metrics.prompt_tokens == 5
    assert result.metrics.completion_tokens == 6
    assert result.metrics.cache_write_tokens == 5220
    assert result.metrics.cache_read_tokens == 0
    assert result.metrics.cost_usd == pytest.approx(0.0328)
    assert result.metrics.duration_ms == 1000
    assert result.model == "claude-opus-4-6"
    print(f"claude: text={result.text!r} model={result.model} metrics={result.metrics}")


def test_claude_raises_on_non_json():
    """A bad envelope surfaces as InferenceError, not a silent fallback."""
    backend = ClaudeCliBackend(config=_cfg())
    with pytest.raises(InferenceError):
        backend._parse_output("not-json", duration_ms=10)


def test_codex_parses_ndjson_stream():
    """Codex concats agent_message item.text and picks usage from turn.completed."""
    backend = CodexCliBackend(config=_cfg("gpt-5.4-mini"))
    result = backend._parse_output(_load("codex_sample.ndjson"), duration_ms=1000)
    assert result.text == "ok"
    assert result.metrics.prompt_tokens == 10590
    assert result.metrics.completion_tokens == 18
    assert result.metrics.cache_read_tokens == 3456
    assert result.metrics.cost_usd is None
    assert result.metrics.duration_ms == 1000
    assert result.model == "gpt-5.4-mini"
    print(f"codex: text={result.text!r} model={result.model} metrics={result.metrics}")


def test_codex_skips_non_json_lines():
    """Codex prefixes NDJSON with stderr warnings — these must be skipped, not fatal."""
    backend = CodexCliBackend(config=_cfg("gpt-5.4-mini"))
    noisy = (
        "2026-04-16T14:51:19 ERROR something happened\n"
        '{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1,"cached_input_tokens":0}}\n'
    )
    result = backend._parse_output(noisy, duration_ms=5)
    assert result.text == "ok"
    assert result.metrics.prompt_tokens == 1


def test_gemini_parses_main_role_model():
    """Gemini's envelope may list several models; we pick the 'main' role."""
    backend = GeminiCliBackend(config=_cfg())
    result = backend._parse_output(_load("gemini_sample.json"), duration_ms=1000)
    assert result.text == "ok"
    # 'main' role is gemini-3-flash-preview (9324 input tokens), not the
    # utility_router (4308 input tokens)
    assert result.model == "gemini-3-flash-preview"
    assert result.metrics.prompt_tokens == 9324
    assert result.metrics.completion_tokens == 1
    assert result.metrics.cache_read_tokens == 0
    assert result.metrics.extra is not None
    assert result.metrics.extra["reasoning_tokens"] == 44
    assert result.metrics.cost_usd is None
    print(f"gemini: text={result.text!r} model={result.model} metrics={result.metrics}")


def test_cursor_parses_envelope():
    """Cursor's envelope exposes only `result`; usage stays at defaults."""
    backend = CursorCliBackend(config=_cfg("claude-sonnet-4-6"))
    result = backend._parse_output(_load("cursor_sample.json"), duration_ms=1420)
    assert result.text == "ok"
    assert result.metrics.prompt_tokens == 0
    assert result.metrics.completion_tokens == 0
    assert result.metrics.cost_usd is None
    assert result.metrics.duration_ms == 1420
    assert result.model == "claude-sonnet-4-6"
    print(f"cursor: text={result.text!r} model={result.model}")


def test_amp_parses_ndjson_stream():
    """Amp pulls text and usage from the last assistant event."""
    backend = AmpCliBackend(config=_cfg())
    result = backend._parse_output(_load("amp_sample.ndjson"), duration_ms=1000)
    assert result.text == "ok"
    assert result.metrics.prompt_tokens == 12
    assert result.metrics.completion_tokens == 1
    assert result.metrics.cache_read_tokens == 8
    assert result.metrics.cache_write_tokens == 0
    print(f"amp: text={result.text!r} model={result.model} metrics={result.metrics}")


def test_amp_falls_back_to_result_event():
    """If no assistant event appears, amp uses the trailing result event."""
    backend = AmpCliBackend(config=_cfg())
    result = backend._parse_output(
        '{"type":"initial"}\n{"type":"result","result":"fallback"}\n', duration_ms=5
    )
    assert result.text == "fallback"
    assert result.metrics.prompt_tokens == 0
    assert result.metrics.completion_tokens == 0


def test_amp_raises_when_stream_has_no_text():
    """All-malformed or text-free streams must fail loudly, not silently."""
    backend = AmpCliBackend(config=_cfg())
    with pytest.raises(InferenceError):
        backend._parse_output("not-json-at-all\nalso-not-json\n", duration_ms=5)


def test_codex_raises_when_stream_has_no_agent_message():
    """Codex with no agent_message items must fail loudly, not silently."""
    backend = CodexCliBackend(config=_cfg("gpt-5.4-mini"))
    with pytest.raises(InferenceError):
        backend._parse_output(
            '{"type":"thread.started","thread_id":"T-1"}\n'
            '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":0,'
            '"cached_input_tokens":0}}\n',
            duration_ms=5,
        )


def test_opencode_parses_ndjson_stream():
    """OpenCode run --format json emits NDJSON events; we aggregate text + tokens."""
    backend = OpenCodeCliBackend(config=_cfg("gemini-2.5-flash"))
    result = backend._parse_output(_load("opencode_sample.ndjson"), duration_ms=1000)
    assert result.text == "ok"
    assert result.metrics.prompt_tokens == 11743
    assert result.metrics.completion_tokens == 26
    assert result.metrics.cache_read_tokens == 1840
    assert result.model == "gemini-2.5-flash"


def test_aider_strips_ansi_escapes():
    """Aider may emit ANSI color codes; we strip them before returning text."""
    backend = AiderCliBackend(config=_cfg("deepseek-v3"))
    result = backend._parse_output("\x1b[32mok\x1b[0m", duration_ms=5)
    assert result.text == "ok"
    assert result.metrics.prompt_tokens == 0
    assert result.metrics.duration_ms == 5
    assert result.model == "deepseek-v3"


def test_openclaw_parses_json_envelope():
    """OpenClaw agent --json emits payloads[].text + meta.agentMeta.lastCallUsage."""
    backend = OpenClawCliBackend(config=_cfg("deepseek-v3"))
    result = backend._parse_output(_load("openclaw_sample.json"), duration_ms=5)
    assert result.text == "ok"
    assert result.metrics.prompt_tokens == 10
    assert result.metrics.completion_tokens == 1
    assert result.metrics.duration_ms == 5
    assert result.model == "claude-haiku-4-5"


def test_kimi_plain_text():
    """Kimi --final-message-only emits plain text."""
    backend = KimiCliBackend(config=_cfg())
    result = backend._parse_output(_load("kimi_sample.txt").strip(), duration_ms=5)
    assert result.text == "ok"
    assert result.metrics.prompt_tokens == 0
    assert result.metrics.duration_ms == 5
