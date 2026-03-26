"""Token counting for LLM prompt budgeting.

Uses tiktoken with the cl100k_base encoding (shared by Claude, GPT-4,
and most modern LLMs) for accurate token counting.

The encoder is lazily loaded on first use and cached as a module-level
singleton to avoid repeated initialization overhead.
"""

import tiktoken

ENCODING_NAME = "cl100k_base"

_encoder: tiktoken.Encoding | None = None


def _get_encoder() -> tiktoken.Encoding:
    """Return the cached tiktoken encoder, initializing on first call."""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding(ENCODING_NAME)
    return _encoder


def count_tokens(text: str) -> int:
    """Count the exact number of tokens in a text string.

    Uses the cl100k_base encoding shared by Claude and GPT-4 models.

    Args:
        text: Input text to tokenize.

    Returns:
        Exact token count.
    """
    if not text:
        return 0
    return len(_get_encoder().encode(text))
