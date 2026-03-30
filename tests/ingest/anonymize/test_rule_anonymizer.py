"""Tests for the full rule-based anonymization pipeline."""

import re

import pytest

from vibelens.config.anonymize import AnonymizeConfig
from vibelens.ingest.anonymize.rule_anonymizer.anonymizer import RuleAnonymizer
from vibelens.models.trajectories import Agent, Step, Trajectory


def _make_trajectory(message: str, **overrides) -> Trajectory:
    """Build a minimal Trajectory with a single step containing the given message."""
    defaults = {
        "session_id": "test-anon-001",
        "agent": Agent(name="test-agent"),
        "project_path": "/Users/testuser/code/project",
        "steps": [
            Step(step_id="s1", source="user", message=message),
        ],
    }
    defaults.update(overrides)
    return Trajectory(**defaults)


class TestRuleAnonymizer:
    def test_disabled_returns_original(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USER", "testuser")
        config = AnonymizeConfig(enabled=False)
        anon = RuleAnonymizer(config)
        t = _make_trajectory("sk-ant-api03-SECRET1234567890abcdefgh")
        result_t, result = anon.anonymize_trajectory(t)
        print(f"  disabled: secrets={result.secrets_redacted}")
        assert result.secrets_redacted == 0
        # Original message preserved
        assert "sk-ant-api03" in result_t.steps[0].message

    def test_credential_redaction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USER", "testuser")
        config = AnonymizeConfig(
            enabled=True,
            redact_credentials=True,
            redact_pii=False,
            anonymize_paths=False,
        )
        anon = RuleAnonymizer(config)
        t = _make_trajectory("my key: sk-ant-api03-ABCDEF1234567890abcdefgh")
        result_t, result = anon.anonymize_trajectory(t)
        print(f"  credential: secrets={result.secrets_redacted}, msg='{result_t.steps[0].message}'")
        assert result.secrets_redacted >= 1
        assert "sk-ant-api03" not in result_t.steps[0].message

    def test_pii_redaction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USER", "testuser")
        config = AnonymizeConfig(
            enabled=True,
            redact_credentials=False,
            redact_pii=True,
            anonymize_paths=False,
        )
        anon = RuleAnonymizer(config)
        t = _make_trajectory("email: alice@company.com")
        result_t, result = anon.anonymize_trajectory(t)
        print(f"  pii: pii_redacted={result.pii_redacted}, msg='{result_t.steps[0].message}'")
        assert result.pii_redacted >= 1
        assert "alice@company.com" not in result_t.steps[0].message

    def test_path_anonymization(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USER", "testuser")
        config = AnonymizeConfig(
            enabled=True,
            redact_credentials=False,
            redact_pii=False,
            anonymize_paths=True,
        )
        anon = RuleAnonymizer(config)
        t = _make_trajectory("file at /Users/testuser/project/main.py")
        result_t, result = anon.anonymize_trajectory(t)
        print(
            f"  paths: paths_anonymized={result.paths_anonymized}, "
            f"msg='{result_t.steps[0].message}'"
        )
        assert result.paths_anonymized >= 1
        assert "testuser" not in result_t.steps[0].message

    def test_high_entropy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USER", "testuser")
        config = AnonymizeConfig(
            enabled=True,
            redact_credentials=False,
            redact_pii=False,
            redact_high_entropy=True,
            anonymize_paths=False,
        )
        anon = RuleAnonymizer(config)
        # A high-entropy quoted string (>40 chars, mixed types)
        secret = "aB3cD4eF5gH6iJ7kL8mN9oP0qR1sT2uV3wX4yZ5!@#$"
        t = _make_trajectory(f'the value is "{secret}" here')
        result_t, result = anon.anonymize_trajectory(t)
        msg = result_t.steps[0].message
        print(f"  high_entropy: secrets={result.secrets_redacted}, msg='{msg}'")
        assert secret not in msg

    def test_tool_description_not_redacted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tool descriptions should survive high-entropy redaction."""
        monkeypatch.setenv("USER", "testuser")
        config = AnonymizeConfig(
            enabled=True,
            redact_credentials=False,
            redact_pii=False,
            redact_high_entropy=True,
            anonymize_paths=False,
        )
        anon = RuleAnonymizer(config)
        description = "Launch a new agent to handle complex, multi-step tasks autonomously."
        t = _make_trajectory(f'"description": "{description}"')
        result_t, result = anon.anonymize_trajectory(t)
        msg = result_t.steps[0].message
        print(f"  tool_description: secrets={result.secrets_redacted}, msg='{msg}'")
        assert description in msg
        assert result.secrets_redacted == 0

    def test_credential_only_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When only credentials are enabled, PII and paths are untouched."""
        monkeypatch.setenv("USER", "testuser")
        config = AnonymizeConfig(
            enabled=True,
            redact_credentials=True,
            redact_pii=False,
            anonymize_paths=False,
            redact_high_entropy=False,
        )
        anon = RuleAnonymizer(config)
        t = _make_trajectory(
            "key=sk-ant-api03-ABCDEF1234567890abcdefgh email=alice@real.com path=/Users/testuser/x/"
        )
        result_t, result = anon.anonymize_trajectory(t)
        msg = result_t.steps[0].message
        print(f"  cred-only: msg='{msg}'")
        assert "sk-ant-api03" not in msg
        # Email and path should still be present
        assert "alice@real.com" in msg
        assert "testuser" in msg

    def test_custom_strings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USER", "testuser")
        config = AnonymizeConfig(
            enabled=True,
            redact_credentials=False,
            redact_pii=False,
            anonymize_paths=False,
            custom_redact_strings=["ACME-INTERNAL"],
        )
        anon = RuleAnonymizer(config)
        t = _make_trajectory("token: ACME-INTERNAL")
        result_t, result = anon.anonymize_trajectory(t)
        msg = result_t.steps[0].message
        print(f"  custom: msg='{msg}', secrets={result.secrets_redacted}")
        assert "ACME-INTERNAL" not in msg

    def test_custom_placeholder(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USER", "testuser")
        config = AnonymizeConfig(
            enabled=True,
            redact_credentials=True,
            placeholder="***MASKED***",
            anonymize_paths=False,
        )
        anon = RuleAnonymizer(config)
        t = _make_trajectory("key=sk-ant-api03-ABCDEF1234567890abcdefgh")
        result_t, _ = anon.anonymize_trajectory(t)
        msg = result_t.steps[0].message
        print(f"  custom placeholder: msg='{msg}'")
        assert "***MASKED***" in msg

    def test_full_pipeline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """All categories enabled — credentials, PII, paths all redacted."""
        monkeypatch.setenv("USER", "testuser")
        config = AnonymizeConfig(enabled=True)
        anon = RuleAnonymizer(config)
        t = _make_trajectory(
            "key=sk-ant-api03-ABCDEF1234567890abcdefgh "
            "email=alice@company.com "
            "path=/Users/testuser/code/main.py"
        )
        result_t, result = anon.anonymize_trajectory(t)
        msg = result_t.steps[0].message
        print(
            f"  full pipeline: secrets={result.secrets_redacted}, "
            f"pii={result.pii_redacted}, paths={result.paths_anonymized}"
        )
        print(f"  msg='{msg}'")
        assert "sk-ant-api03" not in msg
        assert "alice@company.com" not in msg
        assert "testuser" not in msg


class TestRuleAnonymizerBatch:
    def test_shared_path_hasher(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Same username maps to same hash across trajectories in a batch."""
        monkeypatch.setenv("USER", "testuser")
        config = AnonymizeConfig(enabled=True, redact_credentials=False, redact_pii=False)
        anon = RuleAnonymizer(config)
        t1 = _make_trajectory(
            "/Users/testuser/project1/a.py",
            session_id="batch-1",
        )
        t2 = _make_trajectory(
            "/Users/testuser/project2/b.py",
            session_id="batch-2",
        )
        results = anon.anonymize_batch([t1, t2])
        msg1 = results[0][0].steps[0].message
        msg2 = results[1][0].steps[0].message
        print(f"  batch msg1: '{msg1}'")
        print(f"  batch msg2: '{msg2}'")
        # Both should have the same hash for "testuser"
        assert "testuser" not in msg1
        assert "testuser" not in msg2
        # Extract the hashed username — it should appear in both
        hashes1 = re.findall(r"user_[0-9a-f]{8}", msg1)
        hashes2 = re.findall(r"user_[0-9a-f]{8}", msg2)
        assert hashes1 and hashes2
        assert hashes1[0] == hashes2[0]

    def test_disabled_returns_originals(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USER", "testuser")
        config = AnonymizeConfig(enabled=False)
        anon = RuleAnonymizer(config)
        t = _make_trajectory("sk-ant-api03-ABCDEF1234567890abcdefgh")
        results = anon.anonymize_batch([t])
        assert "sk-ant-api03" in results[0][0].steps[0].message

    def test_independent_result_counts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Each trajectory gets its own result counts."""
        monkeypatch.setenv("USER", "testuser")
        config = AnonymizeConfig(enabled=True, anonymize_paths=False, redact_pii=False)
        anon = RuleAnonymizer(config)
        t1 = _make_trajectory(
            "sk-ant-api03-ABCDEF1234567890abcdefgh",
            session_id="batch-a",
        )
        t2 = _make_trajectory(
            "nothing sensitive here",
            session_id="batch-b",
        )
        results = anon.anonymize_batch([t1, t2])
        print(f"  t1 secrets: {results[0][1].secrets_redacted}")
        print(f"  t2 secrets: {results[1][1].secrets_redacted}")
        assert results[0][1].secrets_redacted >= 1
        assert results[1][1].secrets_redacted == 0
