"""Regex patterns for credential and PII secret detection.

Patterns are ordered most-specific-first within each category so that
narrow matches (e.g. ``sk-ant-api03-...``) take priority over broad ones
(e.g. generic bearer tokens) during scanning.
"""

import re
from typing import NamedTuple


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
    # Generic basic-auth URLs (user:pass@host) — after specific DB patterns
    _compile("basic_auth_url", r"https?://[^\s\"'`]+:[^\s\"'`]+@[^\s\"'`]+"),
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
    # Slack tokens and webhooks
    _compile("slack_token", r"xox[bporas]-[A-Za-z0-9-]{10,}"),
    _compile(
        "slack_webhook",
        r"https://hooks\.slack\.com/services/T[A-Za-z0-9]+/B[A-Za-z0-9]+/[A-Za-z0-9]+",
    ),
    # Discord tokens and webhooks
    _compile(
        "discord_token",
        r"(?:mfa\.[A-Za-z0-9_-]{80,}|[A-Za-z0-9_-]{24}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,})",
    ),
    _compile(
        "discord_webhook",
        r"https://discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+",
    ),
    # NPM tokens
    _compile("npm_token", r"npm_[A-Za-z0-9]{36,}"),
    # PyPI tokens
    _compile("pypi_token", r"pypi-[A-Za-z0-9_-]{50,}"),
    # Vercel tokens
    _compile("vercel_token", r"vercel_[A-Za-z0-9_-]{20,}"),
    # Netlify tokens
    _compile("netlify_token", r"nfp_[A-Za-z0-9_-]{20,}"),
    # Supabase keys
    _compile("supabase_key", r"sbp_[A-Za-z0-9_-]{20,}"),
    # Twilio keys (SK + 32 hex chars)
    _compile("twilio_key", r"SK[0-9a-fA-F]{32}"),
    # SendGrid keys
    _compile("sendgrid_key", r"SG\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    # Firebase FCM server keys
    _compile("firebase_key", r"AAAA[A-Za-z0-9_-]{7,}:[A-Za-z0-9_-]{100,}"),
    # Sentry DSN
    _compile("sentry_dsn", r"https://[0-9a-f]+@[^\s\"'`]*\.sentry\.io/\d+"),
    # PEM private keys (full block with body)
    _compile(
        "pem_key_body",
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
        r"[\s\S]*?"
        r"-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
        re.DOTALL,
    ),
    # PEM private keys (header-only fallback for partial content)
    _compile("pem_private_key", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    # Non-Bearer auth headers (Basic, Token)
    _compile(
        "auth_header",
        r"Authorization:\s*(?:Basic|Token)\s+[A-Za-z0-9_./+=-]{8,}",
        re.IGNORECASE,
    ),
    # Session cookie tokens (keyword-gated)
    _compile(
        "session_cookie_token",
        r"(?:session_id|sessionid|JSESSIONID|connect\.sid)\s*=\s*[A-Za-z0-9_./-]{16,}",
        re.IGNORECASE,
    ),
    # JSON/YAML secret values (quoted key + quoted value)
    _compile(
        "json_yaml_secret",
        r"""(?:"(?:password|secret|api_key|apikey|token|private_key|client_secret)"\s*:\s*"[^"]{8,}")""",
        re.IGNORECASE,
    ),
    # Azure client secret
    _compile(
        "azure_client_secret",
        r"AZURE_CLIENT_SECRET\s*=\s*[^\s\"']{8,}",
    ),
    # GCP service account private key ID (40-char hex in JSON)
    _compile(
        "gcp_service_account_key",
        r""""private_key_id"\s*:\s*"[0-9a-f]{40}""",
    ),
    # Datadog API key (env var assignment with 32 hex chars)
    _compile("datadog_api_key", r"DD_API_KEY\s*=\s*[0-9a-fA-F]{32}"),
    # Long hex secret (keyword-gated to avoid git hash false positives)
    _compile(
        "long_hex_secret",
        r"(?:secret|token|key|password)\s*=\s*[0-9a-fA-F]{64,}",
        re.IGNORECASE,
    ),
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


def is_allowlisted(text: str) -> bool:
    """Check whether a matched string is in the known-safe allowlist.

    Args:
        text: The matched text to check.

    Returns:
        True if the text exactly matches an allowlisted value.
    """
    return text in ALLOWLIST
