"""Anonymization configuration for redacting sensitive data from trajectories."""

from pydantic import BaseModel, Field

REDACTED_PLACEHOLDER = "[REDACTED]"
MIN_BARE_USERNAME_LENGTH = 4


class AnonymizeConfig(BaseModel):
    """Controls which categories of sensitive data are redacted from trajectories.

    Each flag independently enables a redaction category. When ``enabled``
    is False, no anonymization is performed regardless of other flags.
    """

    enabled: bool = Field(
        default=False,
        description="Master switch — when False, no anonymization is performed.",
    )
    redact_credentials: bool = Field(
        default=True,
        description="Redact API keys, tokens, JWTs, private keys, and database URLs.",
    )
    redact_pii: bool = Field(
        default=True,
        description="Redact emails and public IP addresses.",
    )
    anonymize_paths: bool = Field(
        default=True,
        description="Hash usernames found in file paths (macOS /Users/X/, Linux /home/X/).",
    )
    redact_high_entropy: bool = Field(
        default=False,
        description="Deprecated — accepted but ignored. High-entropy heuristic removed in v0.9.15.",
    )
    placeholder: str = Field(
        default=REDACTED_PLACEHOLDER,
        description="Replacement text inserted where redacted content was removed.",
    )
    custom_redact_strings: list[str] = Field(
        default_factory=list,
        description="Additional literal strings to redact (e.g. company-internal tokens).",
    )
    extra_usernames: list[str] = Field(
        default_factory=list,
        description="Additional usernames to hash in file paths beyond auto-detected ones.",
    )
