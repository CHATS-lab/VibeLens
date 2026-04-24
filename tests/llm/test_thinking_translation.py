"""Verify each backend translates config.thinking into its CLI/API surface."""

from unittest.mock import MagicMock

from vibelens.config.settings import InferenceConfig
from vibelens.llm.backends.aider_cli import AiderCliBackend
from vibelens.llm.backends.amp_cli import AmpCliBackend
from vibelens.llm.backends.claude_cli import ClaudeCliBackend
from vibelens.llm.backends.codex_cli import CodexCliBackend
from vibelens.llm.backends.cursor_cli import CursorCliBackend
from vibelens.llm.backends.gemini_cli import GeminiCliBackend
from vibelens.llm.backends.kimi_cli import KimiCliBackend
from vibelens.llm.backends.litellm import LiteLLMBackend
from vibelens.llm.backends.openclaw_cli import OpenClawCliBackend
from vibelens.llm.backends.opencode_cli import OpenCodeCliBackend
from vibelens.models.llm.inference import BackendType, InferenceRequest


def _cfg(
    thinking: bool, model: str = "", backend: BackendType = BackendType.MOCK
) -> InferenceConfig:
    return InferenceConfig(backend=backend, model=model, thinking=thinking)


def test_codex_thinking_on_sets_high_effort():
    """Codex thinking=True sets model_reasoning_effort=high."""
    backend = CodexCliBackend(config=_cfg(True, model="gpt-5.4-mini"))
    assert backend._thinking_args() == ["-c", "model_reasoning_effort=high"]


def test_codex_thinking_off_sets_none_effort_and_disables_web_search():
    """Codex thinking=False sets reasoning=none and disables web_search.

    ``none`` fully disables reasoning but conflicts with the default
    ``web_search`` tool, so we pair it with ``-c web_search=disabled``.
    """
    backend = CodexCliBackend(config=_cfg(False, model="gpt-5.4-mini"))
    assert backend._thinking_args() == [
        "-c",
        "web_search=disabled",
        "-c",
        "model_reasoning_effort=none",
    ]


def test_cursor_thinking_on_adds_reasoning_effort():
    """Cursor thinking=True emits --reasoning-effort medium."""
    backend = CursorCliBackend(config=_cfg(True, model="claude-sonnet-4-6"))
    assert backend._thinking_args() == ["--reasoning-effort", "medium"]


def test_cursor_thinking_off_omits_args():
    backend = CursorCliBackend(config=_cfg(False, model="claude-sonnet-4-6"))
    assert backend._thinking_args() == []


def test_aider_thinking_on_passes_both_flags():
    """Aider thinking=True emits both --reasoning-effort and --thinking-tokens."""
    backend = AiderCliBackend(config=_cfg(True, model="deepseek-v3"))
    args = backend._thinking_args()
    assert "--reasoning-effort" in args
    assert "medium" in args
    assert "--thinking-tokens" in args
    assert "4k" in args


def test_aider_thinking_off_disables_tokens():
    """Aider thinking=False emits --thinking-tokens 0 to explicitly disable."""
    backend = AiderCliBackend(config=_cfg(False, model="deepseek-v3"))
    assert backend._thinking_args() == ["--thinking-tokens", "0"]


def test_kimi_thinking_on_adds_flag():
    backend = KimiCliBackend(config=_cfg(True))
    assert backend._thinking_args() == ["--thinking"]


def test_kimi_thinking_off_adds_negated_flag():
    backend = KimiCliBackend(config=_cfg(False))
    assert backend._thinking_args() == ["--no-thinking"]


def test_openclaw_thinking_on_adds_native_flag():
    """OpenClaw agent subcommand has a native --thinking <level> flag."""
    backend = OpenClawCliBackend(config=_cfg(True, model="deepseek-v3"))
    assert backend._thinking_args() == ["--thinking", "medium"]


def test_openclaw_thinking_off_passes_off_level():
    backend = OpenClawCliBackend(config=_cfg(False, model="deepseek-v3"))
    assert backend._thinking_args() == ["--thinking", "off"]


def test_claude_thinking_on_sets_high_effort():
    """Claude --effort high elevates the thinking budget when on."""
    backend = ClaudeCliBackend(config=_cfg(True))
    assert backend._thinking_args() == ["--effort", "high"]
    assert "CLAUDE_CODE_DISABLE_THINKING" not in backend._build_env()


def test_claude_thinking_off_uses_env_var_to_fully_disable():
    """Claude thinking=False sets CLAUDE_CODE_DISABLE_THINKING=1 in subprocess env."""
    backend = ClaudeCliBackend(config=_cfg(False))
    assert backend._thinking_args() == []
    assert backend._build_env().get("CLAUDE_CODE_DISABLE_THINKING") == "1"


def test_gemini_thinking_is_noop():
    backend = GeminiCliBackend(config=_cfg(True))
    assert backend._thinking_args() == []
    assert backend._thinking_prompt_prefix() == ""


def test_opencode_thinking_on_passes_variant_high():
    """OpenCode thinking=True shows blocks AND lifts reasoning effort to high."""
    backend = OpenCodeCliBackend(config=_cfg(True, model="google/gemini-2.5-flash"))
    assert backend._thinking_args() == ["--thinking", "--variant", "high"]


def test_opencode_thinking_off_passes_variant_minimal():
    """OpenCode thinking=False requests the minimal reasoning variant."""
    backend = OpenCodeCliBackend(config=_cfg(False, model="google/gemini-2.5-flash"))
    assert backend._thinking_args() == ["--variant", "minimal"]


def test_amp_thinking_is_noop():
    backend = AmpCliBackend(config=_cfg(True))
    assert backend._thinking_args() == []
    assert backend._thinking_prompt_prefix() == ""


def test_warn_thinking_unsupported_fires_once():
    """Backends without a translation log a one-time warning on first generate()."""
    backend = GeminiCliBackend(config=_cfg(True))
    assert not backend._thinking_warned
    mock_logger = MagicMock()
    import vibelens.llm.backends.cli_base as cli_base

    original = cli_base.logger
    cli_base.logger = mock_logger
    try:
        backend._warn_thinking_unsupported()
        backend._warn_thinking_unsupported()
    finally:
        cli_base.logger = original
    assert mock_logger.warning.call_count == 1
    assert backend._thinking_warned


def test_litellm_anthropic_thinking_adds_adaptive():
    """LiteLLM with Anthropic model + thinking=True sets thinking={'type': 'adaptive'}."""
    cfg = _cfg(True, model="anthropic/claude-haiku-4-5", backend=BackendType.LITELLM)
    backend = LiteLLMBackend(config=cfg)
    kwargs = backend._build_kwargs(InferenceRequest(system="s", user="u"))
    assert kwargs.get("thinking") == {"type": "adaptive"}


def test_litellm_openai_thinking_adds_reasoning_effort():
    """LiteLLM with OpenAI model + thinking=True sets reasoning_effort='medium'."""
    cfg = _cfg(True, model="openai/gpt-5", backend=BackendType.LITELLM)
    backend = LiteLLMBackend(config=cfg)
    kwargs = backend._build_kwargs(InferenceRequest(system="s", user="u"))
    assert kwargs.get("reasoning_effort") == "medium"


def test_litellm_thinking_off_omits_fields():
    """LiteLLM with thinking=False adds neither thinking nor reasoning_effort."""
    cfg = _cfg(False, model="anthropic/claude-haiku-4-5", backend=BackendType.LITELLM)
    backend = LiteLLMBackend(config=cfg)
    kwargs = backend._build_kwargs(InferenceRequest(system="s", user="u"))
    assert "thinking" not in kwargs
    assert "reasoning_effort" not in kwargs
