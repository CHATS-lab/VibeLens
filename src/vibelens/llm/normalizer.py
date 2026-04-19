"""Model name normalization.

Resolves raw model name strings (with provider prefixes, path prefixes,
date suffixes, case variations) to canonical model keys.
"""

import re

# Ordered prefix-to-canonical mapping, most specific first.
# Prefix matching handles date suffixes (e.g. claude-3-5-sonnet-20241022)
# and preview tags (e.g. gemini-2.5-flash-preview-04-17) naturally.
_MODEL_PREFIX_MAP: list[tuple[str, str]] = [
    # Anthropic — specific versions before base names
    ("claude-opus-4-7", "claude-opus-4-7"),
    ("claude-opus-4-6", "claude-opus-4-6"),
    ("claude-opus-4-1", "claude-opus-4-1"),
    ("claude-sonnet-4-6", "claude-sonnet-4-6"),
    ("claude-sonnet-4-5", "claude-sonnet-4-5"),
    ("claude-3-5-sonnet", "claude-3-5-sonnet"),
    ("claude-haiku-4-5", "claude-haiku-4-5"),
    ("claude-3-5-haiku", "claude-3-5-haiku"),
    # OpenAI — pro/mini/nano before base to avoid prefix collision
    ("gpt-5.4-pro", "gpt-5.4-pro"),
    ("gpt-5.4-mini", "gpt-5.4-mini"),
    ("gpt-5.4-nano", "gpt-5.4-nano"),
    ("gpt-5.4", "gpt-5.4"),
    ("gpt-5.3-codex", "gpt-5.3-codex"),
    ("gpt-5-mini", "gpt-5-mini"),
    ("gpt-5", "gpt-5"),
    ("gpt-4o-mini", "gpt-4o-mini"),
    ("gpt-4.1-mini", "gpt-4.1-mini"),
    ("gpt-4.1-nano", "gpt-4.1-nano"),
    ("gpt-4.1", "gpt-4.1"),
    ("o4-mini", "o4-mini"),
    ("o3-pro", "o3-pro"),
    ("o3", "o3"),
    # Google Gemini — more specific before less specific
    ("gemini-3.1-pro", "gemini-3.1-pro"),
    ("gemini-3-pro", "gemini-3-pro"),
    ("gemini-2.5-flash-lite", "gemini-2.5-flash-lite"),
    ("gemini-2.5-flash", "gemini-2.5-flash"),
    ("gemini-2.5-pro", "gemini-2.5-pro"),
    ("gemini-2.0-flash", "gemini-2.0-flash"),
    # xAI Grok — more specific before less specific
    ("grok-4.20", "grok-4.20-beta"),
    ("grok-4.1-fast", "grok-4.1-fast"),
    ("grok-4-fast", "grok-4-fast"),
    ("grok-4", "grok-4"),
    # DeepSeek
    ("deepseek-v3.2", "deepseek-v3.2"),
    ("deepseek-v3", "deepseek-v3"),
    ("deepseek-chat", "deepseek-chat"),
    # Mistral — more specific before less specific
    ("magistral-medium", "magistral-medium"),
    ("mistral-medium-3.1", "mistral-medium-3.1"),
    ("mistral-large", "mistral-large"),
    ("mistral-small-4", "mistral-small-4"),
    ("codestral", "codestral"),
    # Qwen
    ("qwen3.5-plus", "qwen3.5-plus"),
    ("qwen3-max", "qwen3-max"),
    ("qwen3-coder-next", "qwen3-coder-next"),
    # Moonshot Kimi — more specific before less specific
    ("kimi-k2.5", "kimi-k2.5"),
    ("kimi-k2-0905", "kimi-k2-0905"),
    ("kimi-k2-thinking", "kimi-k2-thinking"),
    ("kimi-k2", "kimi-k2"),
    # MiniMax
    ("minimax-m2.7", "minimax-m2.7"),
    ("minimax-m2.5", "minimax-m2.5"),
    # Zhipu GLM — more specific before less specific
    ("glm-5-code", "glm-5-code"),
    ("glm-5", "glm-5"),
    ("glm-4.7-flashx", "glm-4.7-flashx"),
    ("glm-4.7", "glm-4.7"),
    # ByteDance Seed — more specific before less specific
    ("seed-2.0-pro", "seed-2.0-pro"),
    ("seed-2.0-lite", "seed-2.0-lite"),
    ("seed-2.0-mini", "seed-2.0-mini"),
    ("seed-2.0-code", "seed-2.0-code"),
    # Meta Llama 4
    ("llama-4-maverick", "llama-4-maverick"),
    ("llama-4-scout", "llama-4-scout"),
]

# Strips Gemini path prefixes like "models/" or "accounts/abc/models/"
_GEMINI_PATH_PREFIX_RE = re.compile(r"^(?:models/|accounts/[^/]+/models/)")

# Strips provider prefixes like "anthropic/", "qwen/", "openai/gpt-5.4"
# Matches one or more slash-separated segments before the model name,
# where provider segments are alphanumeric with hyphens/underscores/dots.
_PROVIDER_PREFIX_RE = re.compile(r"^[a-zA-Z0-9._-]+[/:]")

# Some clients (Hermes, early wrappers) emit Anthropic model names with a
# dotted major.minor version, e.g. "claude-opus-4.7". The canonical form
# used by our pricing catalog is dashed ("claude-opus-4-7"). Rewrite only
# when the segment preceding the dot looks like "-<digit>+", so non-Anthropic
# names (``gpt-5.4``) are left untouched.
_ANTHROPIC_DOT_VERSION_RE = re.compile(r"^(claude-[a-z]+-\d+)\.(\d+)(?=$|[^0-9])")


def _strip_prefixes(raw_name: str) -> str:
    """Strip provider and path prefixes from a raw model name.

    Handles multiple formats:
      - Provider slash: "qwen/qwen3-max" -> "qwen3-max"
      - Provider colon: "anthropic:claude-opus-4-6" -> "claude-opus-4-6"
      - Gemini path: "models/gemini-2.5-flash" -> "gemini-2.5-flash"
      - Deep path: "accounts/abc/models/gemini-2.5-pro" -> "gemini-2.5-pro"
      - Nested provider: "org/provider/model-name" -> "model-name"

    Args:
        raw_name: Whitespace-stripped, lowercased model name.

    Returns:
        Model name with all known prefixes removed.
    """
    # Gemini-style path prefixes first (more specific pattern)
    name = _GEMINI_PATH_PREFIX_RE.sub("", raw_name)

    # Strip provider prefix(es): "qwen/qwen3-max" -> "qwen3-max"
    # Loop handles nested prefixes like "org/provider/model"
    while _PROVIDER_PREFIX_RE.match(name):
        separator_pos = name.index("/" if "/" in name else ":")
        name = name[separator_pos + 1 :]

    return name


def normalize_model_name(raw_name: str | None) -> str | None:
    """Normalize a raw model name to a canonical key.

    Handles provider prefixes (qwen/model), path prefixes (Gemini),
    date suffixes (Claude), preview tags, and case variations.
    Returns None for unrecognized models.

    Args:
        raw_name: Raw model name string from trajectory data.

    Returns:
        Canonical model key or None if unrecognized.
    """
    if not raw_name:
        return None

    name = _strip_prefixes(raw_name.strip().lower())
    if not name:
        return None

    # Accept the dotted Anthropic shape ("claude-opus-4.7") that some
    # wrappers emit by rewriting it to the dashed canonical form before
    # prefix-matching.
    name = _ANTHROPIC_DOT_VERSION_RE.sub(r"\1-\2", name)

    for prefix, canonical in _MODEL_PREFIX_MAP:
        if name.startswith(prefix):
            return canonical
    return None
