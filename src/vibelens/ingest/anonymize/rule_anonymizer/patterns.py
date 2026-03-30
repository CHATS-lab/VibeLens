"""Regex patterns for credential, PII, and high-entropy secret detection.

Patterns are ordered most-specific-first within each category so that
narrow matches (e.g. ``sk-ant-api03-...``) take priority over broad ones
(e.g. generic bearer tokens) during scanning.
"""

import math
import re
from typing import NamedTuple

SHANNON_ENTROPY_THRESHOLD = 3.5
HIGH_ENTROPY_MIN_LENGTH = 40
NATURAL_TEXT_SPACE_RATIO = 0.10


class PatternDef(NamedTuple):
    """A named regex pattern used for secret scanning."""

    name: str
    pattern: re.Pattern[str]


def _compile(name: str, regex: str, flags: int = 0) -> PatternDef:
    """Helper to build a PatternDef with pre-compiled regex."""
    return PatternDef(name=name, pattern=re.compile(regex, flags))


# Credential patterns — most-specific first
CREDENTIAL_PATTERNS: list[PatternDef] = [
    # JWT tokens (three base64url segments separated by dots)
    _compile("jwt", r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    # Database URLs with credentials
    _compile("db_url_postgres", r"postgres(?:ql)?://[^\s\"'`]+:[^\s\"'`]+@[^\s\"'`]+"),
    _compile("db_url_mysql", r"mysql(?:\+[a-z]+)?://[^\s\"'`]+:[^\s\"'`]+@[^\s\"'`]+"),
    _compile("db_url_mongodb", r"mongodb(?:\+srv)?://[^\s\"'`]+:[^\s\"'`]+@[^\s\"'`]+"),
    # Anthropic API keys
    _compile("anthropic_key", r"sk-ant-(?:api03|admin01)-[A-Za-z0-9_-]{20,}"),
    # OpenAI API keys
    _compile("openai_key", r"sk-(?:proj-)?[A-Za-z0-9]{20,}"),
    # HuggingFace tokens
    _compile("huggingface_token", r"hf_[A-Za-z0-9]{20,}"),
    # Google Cloud service account / OAuth
    _compile("gcloud_key", r"AIza[A-Za-z0-9_-]{35}"),
    _compile("google_oauth_secret", r"GOCSPX-[A-Za-z0-9_-]{20,}"),
    # Stripe keys
    _compile("stripe_key", r"(?:sk|pk|rk)_(?:test|live)_[A-Za-z0-9]{20,}"),
    # GitHub tokens (classic + fine-grained)
    _compile("github_classic_token", r"ghp_[A-Za-z0-9]{36,}"),
    _compile("github_fine_grained", r"github_pat_[A-Za-z0-9_]{20,}"),
    _compile("github_oauth", r"gho_[A-Za-z0-9]{36,}"),
    _compile("github_app_token", r"(?:ghs|ghu)_[A-Za-z0-9]{36,}"),
    # GitLab tokens
    _compile("gitlab_token", r"glpat-[A-Za-z0-9_-]{20,}"),
    # AWS keys
    _compile("aws_access_key", r"AKIA[A-Z0-9]{16}"),
    _compile(
        "aws_secret_key",
        r"(?:aws_secret_access_key|AWS_SECRET_ACCESS_KEY)\s*[=:]\s*[A-Za-z0-9/+=]{40}",
    ),
    # Slack tokens
    _compile("slack_token", r"xox[bporas]-[A-Za-z0-9-]{10,}"),
    # Discord tokens
    _compile(
        "discord_token",
        r"(?:mfa\.[A-Za-z0-9_-]{80,}|[A-Za-z0-9_-]{24}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,})",
    ),
    # NPM tokens
    _compile("npm_token", r"npm_[A-Za-z0-9]{36,}"),
    # PyPI tokens
    _compile("pypi_token", r"pypi-[A-Za-z0-9_-]{50,}"),
    # PEM private keys (multiline — captured as header line only)
    _compile("pem_private_key", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    # CLI token flags (e.g. --token=abc123, --api-key "abc123")
    _compile(
        "cli_token_flag",
        r"--(?:token|api[_-]?key|secret|password)\s*[=\s]\s*['\"]?[^\s'\"]{8,}",
        re.IGNORECASE,
    ),
    # Environment secret assignments (e.g. SECRET_KEY=abc123)
    _compile(
        "env_secret",
        r"(?:SECRET|TOKEN|PASSWORD|API_KEY|PRIVATE_KEY|ACCESS_KEY)\s*=\s*['\"]?[^\s'\"]{8,}",
    ),
    # Generic bearer tokens in headers
    _compile("bearer_token", r"Bearer\s+[A-Za-z0-9_.-]{20,}"),
    # URL query params that look like secrets
    _compile(
        "url_secret_param",
        r"[?&](?:key|token|secret|password|api_key)=[^\s&]{8,}",
        re.IGNORECASE,
    ),
]

# PII patterns
PII_PATTERNS: list[PatternDef] = [
    _compile("email", r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    _compile(
        "public_ip",
        r"\b(?:"
        # IPv4 — exclude private ranges (10.x, 172.16-31.x, 192.168.x, 127.x)
        r"(?!10\.)(?!172\.(?:1[6-9]|2[0-9]|3[01])\.)(?!192\.168\.)(?!127\.)"
        r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]\d|\d)"
        r"(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}"
        r")\b",
    ),
]

# High-entropy quoted strings (potential embedded secrets)
HIGH_ENTROPY_PATTERNS: list[PatternDef] = [
    _compile("high_entropy_quoted", r"""['"]([\x20-\x7E]{40,})['"]"""),
]

# Allowlist — known-safe strings that should not be redacted
ALLOWLIST: frozenset[str] = frozenset(
    [
        # Safe example emails
        "user@example.com",
        "test@example.com",
        "admin@example.com",
        "noreply@example.com",
        "info@example.com",
        "support@example.com",
        "noreply@anthropic.com",
        "noreply@github.com",
        # Python/JS decorators and builtins that look like emails
        "@property",
        "@staticmethod",
        "@classmethod",
        "@abstractmethod",
        "@override",
        # Example DB URLs from docs
        "postgres://user:pass@localhost/db",
        "mysql://user:pass@localhost/db",
        "mongodb://user:pass@localhost/db",
        # Private IP ranges (commonly in configs)
        "127.0.0.1",
        "0.0.0.0",
        "localhost",
        # Public DNS servers
        "8.8.8.8",
        "8.8.4.4",
        "1.1.1.1",
        "1.0.0.1",
    ]
)


def compute_shannon_entropy(text: str) -> float:
    """Compute Shannon entropy (bits per character) of a string.

    Higher entropy indicates more randomness, suggesting the string
    may be a secret or key rather than natural language.

    Args:
        text: The string to analyze.

    Returns:
        Entropy in bits. Typical English text ~4.0, random base64 ~5.5+.
    """
    if not text:
        return 0.0
    length = len(text)
    freq: dict[str, int] = {}
    for char in text:
        freq[char] = freq.get(char, 0) + 1
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


def has_mixed_char_types(text: str) -> bool:
    """Check if text contains a mix of character types (letters, digits, symbols).

    Secrets typically mix character types while natural language tends to
    be mostly alphabetic with spaces.

    Args:
        text: The string to check.

    Returns:
        True if at least 3 of {uppercase, lowercase, digits, symbols} are present.
    """
    type_count = sum(
        [
            any(c.isupper() for c in text),
            any(c.islower() for c in text),
            any(c.isdigit() for c in text),
            any(not c.isalnum() and not c.isspace() for c in text),
        ]
    )
    MIN_MIXED_TYPES = 3
    return type_count >= MIN_MIXED_TYPES


def is_natural_text(text: str) -> bool:
    """Detect natural language by checking whether spaces make up >= 10% of characters.

    Tool descriptions, JSON schema descriptions, and other English prose
    consistently have space ratios of 13-17%, while secrets and base64 strings
    have 0%. The 10% threshold provides a wide safety margin.

    Args:
        text: The string to check.

    Returns:
        True if the text appears to be natural language.
    """
    if not text:
        return False
    space_count = sum(1 for c in text if c == " ")
    return (space_count / len(text)) >= NATURAL_TEXT_SPACE_RATIO


def is_allowlisted(text: str) -> bool:
    """Check whether a matched string is in the known-safe allowlist.

    Args:
        text: The matched text to check.

    Returns:
        True if the text exactly matches an allowlisted value.
    """
    return text in ALLOWLIST


def is_valid_high_entropy(text: str) -> bool:
    """Determine if a quoted string is likely a secret based on entropy and character mix.

    Used as a secondary filter for HIGH_ENTROPY_PATTERNS matches:
    the regex captures any quoted string >= 40 chars, and this function
    filters to only those with genuinely high randomness.

    Args:
        text: The inner content of a quoted string (without quotes).

    Returns:
        True if the string has high entropy AND mixed character types.
    """
    if len(text) < HIGH_ENTROPY_MIN_LENGTH:
        return False
    if is_natural_text(text):
        return False
    return compute_shannon_entropy(text) >= SHANNON_ENTROPY_THRESHOLD and has_mixed_char_types(text)
