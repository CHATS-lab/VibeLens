# Anonymization

Rule-based anonymizer that removes secrets, PII, and usernames from ATIF trajectories before sharing or donation.

## Purpose

Donated or shared trajectories must not leak credentials, personal information, or OS usernames. The anonymizer applies three-phase regex-based redaction to all text fields in a trajectory while preserving structural fields (IDs, timestamps, metrics) and minimizing false positives.

## Architecture

```
ingest/anonymize/
  base.py                       BaseAnonymizer ABC, AnonymizeResult model
  traversal.py                  Deep-walk ATIF fields, apply str->str transform
  rule_anonymizer/
    anonymizer.py               RuleAnonymizer -- orchestrates patterns + paths
    patterns.py                 PatternDef, CREDENTIAL_PATTERNS, PII_PATTERNS, ALLOWLIST
    redactor.py                 scan_text(), redact_patterns(), redact_custom_strings()
    path_hasher.py              PathHasher -- username detection, hashing, variants
  llm_anonymizer/               (future) LLM-based anonymizer
  ner_anonymizer/               (future) NER-based anonymizer
```

## Redaction Pipeline

For each trajectory, `RuleAnonymizer` builds a `transform(text) -> text` closure chaining three phases:

1. **Regex pattern redaction** -- Scans against `CREDENTIAL_PATTERNS` (37 patterns) and `PII_PATTERNS` (5 patterns). Matches deduplicated (overlapping ranges resolved earliest-wins), replaced end-to-start to preserve offsets.
2. **Custom literal redaction** -- Replaces user-provided literal strings (e.g., company-internal tokens).
3. **Path username hashing** -- `PathHasher` detects usernames in `/Users/X/`, `/home/X/`, and encoded `-Users-X-` paths, replaces with `user_<8-hex>` (SHA-256 prefix). Also derives camelCase variants.

`traversal.py` deep-walks the ATIF Trajectory tree and applies the transform to all text fields (messages, paths, arguments, extras) while leaving structural fields untouched.

## Configuration

`AnonymizeConfig` in `config/anonymize.py`:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `bool` | `False` | Master switch |
| `redact_credentials` | `bool` | `True` | Redact API keys, tokens, JWTs, database URLs |
| `redact_pii` | `bool` | `True` | Redact emails and public IPs |
| `anonymize_paths` | `bool` | `True` | Hash usernames in file paths |
| `placeholder` | `str` | `[REDACTED]` | Replacement text |
| `custom_redact_strings` | `list[str]` | `[]` | Additional literal strings to redact |
| `extra_usernames` | `list[str]` | `[]` | Additional usernames to hash |

## Pattern Categories

### Credentials (37 patterns)

Ordered most-specific-first. Includes: JWT, database URLs (Postgres/MySQL/MongoDB), provider API keys (Anthropic, OpenAI, HuggingFace, GCloud, Stripe, GitHub, GitLab, AWS, Slack, Discord, npm, PyPI, Vercel, Netlify, Supabase, Twilio, SendGrid, Firebase, Sentry), PEM keys, auth headers, session cookies, JSON/YAML secrets, CLI token flags, env vars, bearer tokens, URL secret params.

### PII (5 patterns)

Email addresses, public IPv4 (excluding private ranges), E.164 phone numbers, US SSNs, credit card numbers.

### Allowlist

Exact-match strings never redacted: safe example emails (`user@example.com`), Python decorators (`@property`), example DB URLs, DNS/loopback IPs.

## False Positive Strategy

An earlier Shannon entropy heuristic (>= 3.5 bits for 40+ char strings) was removed due to false positives on Python traceback file paths and config values. The current approach uses **structural prefixes or keyword gates** for each pattern:

- `long_hex_secret` requires `secret=`/`token=`/`key=` before hex strings
- `json_yaml_secret` requires specific key names (`"password"`, `"api_key"`)
- `session_cookie_token` requires cookie-name keywords

## Path Anonymization

`PathHasher` handles username detection across platforms:

| Platform | Pattern |
|----------|---------|
| macOS/Linux | `/Users/X/`, `/home/X/` |
| Encoded | `-Users-X-` (Claude Code project encoding) |
| Windows | `C:\Users\X\` |
| WSL | `/mnt/c/Users/X/` |
| Bare | Word-boundary match (usernames >= 4 chars) |
| CamelCase | `JohnDoe` also catches `john_doe`, `JOHN-DOE`, etc. |

All variants of the same username map to the same `user_<8-hex>` hash for consistency across trajectories.

## Integration

The upload pipeline (`services/upload/processor.py`) auto-applies anonymization when `AnonymizeConfig.enabled` is True. `RuleAnonymizer.anonymize_batch()` shares a single `PathHasher` across all trajectories in an upload for consistent username hashing.

## Testing

- `tests/ingest/anonymize/test_patterns.py` -- every credential/PII pattern and allowlist entry
- `tests/ingest/anonymize/test_rule_anonymizer.py` -- full pipeline with config combinations
- `TestFalsePositiveRegression` -- guards against regressions with traceback paths, git hashes, natural text

Run: `pytest tests/ingest/anonymize/ -v -s`
