"""Tests for regex patterns and allowlist utilities."""

import pytest

from vibelens.ingest.anonymize.rule_anonymizer.patterns import (
    CREDENTIAL_PATTERNS,
    PII_PATTERNS,
    is_allowlisted,
)
from vibelens.ingest.anonymize.rule_anonymizer.redactor import scan_text


class TestIsAllowlisted:
    def test_safe_emails_allowed(self) -> None:
        for email in ["user@example.com", "noreply@anthropic.com", "noreply@github.com"]:
            assert is_allowlisted(email) is True
            print(f"  allowlisted: {email}")

    def test_unknown_email_not_allowed(self) -> None:
        assert is_allowlisted("secret@company.com") is False

    def test_dns_ips_allowed(self) -> None:
        for ip in ["8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1"]:
            assert is_allowlisted(ip) is True
            print(f"  allowlisted: {ip}")


class TestCredentialPatterns:
    @pytest.mark.parametrize(
        ("name", "sample"),
        [
            (
                "jwt",
                "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
                ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
            ),
            ("anthropic_key", "sk-ant-api03-abcdefghijklmnop1234567890ABCDEF"),
            ("openai_key", "sk-proj-abcdefghijklmnopqrstuv"),
            ("github_classic_token", "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl"),
            ("aws_access_key", "AKIAIOSFODNN7EXAMPLE"),
            ("bearer_token", "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"),
            ("env_secret", "API_KEY=my_super_secret_value_12345"),
            ("pem_private_key", "-----BEGIN RSA PRIVATE KEY-----"),
            ("stripe_key", "sk_test_abcdefghijklmnopqrstuv"),
            ("db_url_postgres", "postgres://admin:p@ssw0rd@db.example.com:5432/mydb"),
            # New patterns
            (
                "slack_webhook",
                "https://hooks.slack.com/services/T03EXAMPLE/B05EXAMPLE/aBC123xYz789",
            ),
            (
                "discord_webhook",
                "https://discord.com/api/webhooks/1234567890/abcdefABCDEF_1234567890",
            ),
            ("basic_auth_url", "https://admin:secretpass@api.example.com/v1"),
            ("auth_header", "Authorization: Basic dXNlcjpwYXNz"),
            ("auth_header", "Authorization: Token abc12345defghijk"),
            ("vercel_token", "vercel_abcdefghijklmnopqrstuv"),
            ("netlify_token", "nfp_abcdefghijklmnopqrstuv"),
            ("supabase_key", "sbp_abcdefghijklmnopqrstuv"),
            ("twilio_key", "SK" + "0" * 32),
            ("sendgrid_key", "SG.abcdefghijk.lmnopqrstuvwxyz1234567890"),
            ("sentry_dsn", "https://abc123def456@o123456.ingest.sentry.io/789012"),
            (
                "session_cookie_token",
                "session_id=abc123def456ghi789jkl012mno345",
            ),
            (
                "json_yaml_secret",
                '"password": "my_super_secret_password"',
            ),
            ("azure_client_secret", "AZURE_CLIENT_SECRET=abcdef12345678"),
            (
                "gcp_service_account_key",
                '"private_key_id": "0123456789abcdef0123456789abcdef01234567"',
            ),
            ("datadog_api_key", "DD_API_KEY=0123456789abcdef0123456789abcdef"),
            (
                "long_hex_secret",
                "secret="
                + "a1b2c3d4e5f6" * 11,  # 66 hex chars
            ),
        ],
    )
    def test_credential_detected(self, name: str, sample: str) -> None:
        findings = scan_text(sample, CREDENTIAL_PATTERNS)
        matched_names = [f.name for f in findings]
        print(f"  {name}: matched={matched_names}")
        assert len(findings) >= 1, f"Expected {name} to be detected in: {sample}"


class TestFalsePositiveRegression:
    """Strings that must NOT be redacted — guards against over-matching."""

    @pytest.mark.parametrize(
        "label",
        [
            'File "/usr/lib/python3.12/site-packages/pip/_vendor/rich/console.py", line 42',
            'File "/home/dev/.local/lib/python3.11/site-packages/requests/adapters.py"',
            "  File \"/app/src/vibelens/ingest/parsers/claude.py\", line 128, in parse",
            "/usr/lib/python3.12/importlib/metadata/__init__.py",
        ],
    )
    def test_traceback_file_paths_not_redacted(self, label: str) -> None:
        """Python traceback file paths must not be flagged as secrets."""
        findings = scan_text(label, CREDENTIAL_PATTERNS)
        print(f"  traceback path findings: {[(f.name, f.matched_text) for f in findings]}")
        assert len(findings) == 0, f"False positive on traceback path: {findings}"

    @pytest.mark.parametrize(
        "text",
        [
            "d94e305a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e",
            "sha256:abc123def456abc123def456abc123def456abc123def456abc123def456abcd",
        ],
    )
    def test_git_hashes_and_checksums_not_redacted(self, text: str) -> None:
        """Bare git hashes and checksums must not be flagged."""
        findings = scan_text(text, CREDENTIAL_PATTERNS)
        print(f"  hash findings: {[(f.name, f.matched_text) for f in findings]}")
        assert len(findings) == 0, f"False positive on hash/checksum: {findings}"

    def test_natural_text_not_redacted(self) -> None:
        """Long natural-language strings must not be flagged."""
        text = "Launch a new agent to handle complex, multi-step tasks autonomously."
        findings = scan_text(text, CREDENTIAL_PATTERNS)
        assert len(findings) == 0


class TestPIIPatterns:
    def test_email_detected(self) -> None:
        text = "Contact me at real.person@company.com for details"
        findings = scan_text(text, PII_PATTERNS)
        print(f"  PII findings: {[(f.name, f.matched_text) for f in findings]}")
        assert any(f.name == "email" for f in findings)

    def test_private_ip_not_detected(self) -> None:
        text = "Server at 192.168.1.100 is internal"
        findings = scan_text(text, PII_PATTERNS)
        print(f"  PII findings for private IP: {[(f.name, f.matched_text) for f in findings]}")
        assert not any(f.name == "public_ip" for f in findings)

    def test_public_ip_detected(self) -> None:
        text = "External server at 203.0.113.50 exposed"
        findings = scan_text(text, PII_PATTERNS)
        print(f"  PII findings for public IP: {[(f.name, f.matched_text) for f in findings]}")
        assert any(f.name == "public_ip" for f in findings)

    def test_allowlisted_email_skipped(self) -> None:
        text = "Send to user@example.com"
        findings = scan_text(text, PII_PATTERNS)
        print(f"  PII findings for allowlisted email: {findings}")
        assert len(findings) == 0
