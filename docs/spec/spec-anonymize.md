# Anonymisation

The redaction layer that runs over every uploaded or donated `Trajectory` before it leaves the user's machine.

## Motivation

Sessions that get donated, shared, or even just uploaded carry whatever the user typed and whatever the agent saw — often including API keys, JWTs, database URLs, OS usernames embedded in absolute paths, customer email addresses, and the occasional company-internal identifier. The user has to be able to share session content with confidence, which means the platform has to redact the predictable categories before any sharing path runs.

The anonymiser is rule-based on purpose. LLM-based and NER-based variants are scaffolded as future modules, but the default has to be deterministic, fast, and inspectable: a regression on what gets redacted is a privacy bug, and "the model decided" is not a useful answer. Every redaction the user sees has a named rule behind it.

## Architecture

```
ingest/anonymize/
├── base.py                ABC + AnonymizeResult
├── traversal.py           deep-walk an ATIF Trajectory and apply str→str
└── rule_anonymizer/
    ├── anonymizer.py      RuleAnonymizer (orchestrator)
    ├── patterns.py        named credential / PII patterns + allowlist
    ├── redactor.py        scan + replace, end-to-start to preserve offsets
    └── path_hasher.py     username detection across OS path conventions
```

Two dimensions: *what to redact* (patterns + paths) and *where to redact* (deep-walked text fields, structural fields untouched). The two are kept separate so a future LLM- or NER-backed implementation can swap in the "what" while keeping the same "where".

## The transform

For each trajectory, `RuleAnonymizer` builds a `transform(text) -> text` closure that runs three phases in order:

1. **Pattern redaction.** Named credential and PII regexes scan the text. Overlaps are resolved earliest-wins, replacements are applied end-to-start so offsets stay valid through the rewrite.
2. **Custom literal redaction.** User-provided literal strings (company-internal tokens, project codenames) are replaced verbatim.
3. **Path-username hashing.** Detected usernames in absolute paths become `user_<8-hex>` (SHA-256 prefix). The same username on every platform variant — `/Users/`, `/home/`, the `-Users-` form Claude Code encodes into project hashes, `C:\Users\`, `/mnt/c/Users/`, plus camelCase / snake_case variants — maps to the same hash, so cross-session linkability is preserved without leaking the original.

`traversal.py` then walks the trajectory and applies the closure to every text field (messages, tool inputs, observations, paths, extras) while leaving identifiers, timestamps, and metrics alone.

`RuleAnonymizer.anonymize_batch` shares one `PathHasher` across all trajectories in a batch so a username keeps the same hash across an upload's worth of sessions.

## Pattern categories

- **Credentials** — JWTs, database connection strings, provider API keys (Anthropic, OpenAI, HuggingFace, AWS, GCloud, GitHub, GitLab, Stripe, Slack, Discord, npm, Vercel, Netlify, Supabase, Twilio, SendGrid, Firebase, Sentry, …), PEM blocks, auth headers, session cookies, secrets in JSON/YAML config, CLI flags carrying tokens, env-var assignments, bearer tokens, URL secret parameters.
- **PII** — email addresses, public IPv4, E.164 phone numbers, US SSNs, credit card numbers.
- **Allowlist** — exact strings that look credential-shaped but aren't (`user@example.com`, Python decorator `@property`, DNS / loopback IPs, example DB URLs).

Patterns are ordered most-specific-first so a provider-shaped key wins over a generic "long hex" rule.

## False-positive containment

The biggest hazard for a rule-based anonymiser is over-redacting. Two design choices keep that bounded:

- **Keyword-gated entropy.** Generic high-entropy patterns require structural context (`secret=`, `token=`, JSON keys named `"password"` / `"api_key"`, cookie-shaped headers). Pure-entropy heuristics are not used — natural-language paragraphs and traceback file paths defeat them.
- **Allowlist before pattern match.** Common safe-example values short-circuit before the regex bank runs.

Every regression risk surface (Python tracebacks, git hashes, natural text) is locked in by tests in `tests/ingest/anonymize/`.

## Configuration

`AnonymizeConfig` (`config/anonymize.py`) controls the pipeline:

| Field | Default | Effect |
|---|---|---|
| `enabled` | `False` | Master switch. Off → identity transform. |
| `redact_credentials` | `True` | Run the credential pattern bank. |
| `redact_pii` | `True` | Run the PII pattern bank. |
| `anonymize_paths` | `True` | Run the path-username hasher. |
| `placeholder` | `[REDACTED]` | Replacement text for pattern matches. |
| `custom_redact_strings` | `[]` | Extra literal strings to redact. |
| `extra_usernames` | `[]` | Extra usernames the hasher should treat as known. |

## Integration

The upload pipeline (`services/upload/processor.py`) calls `RuleAnonymizer.anonymize_batch` automatically when `AnonymizeConfig.enabled` is true; the donation pipeline does the same before zipping. Counts of what was redacted (`secrets_redacted`, `paths_anonymized`, `pii_redacted`) end up on `UploadResult` so the user sees what was changed.

## Out of scope (today)

- LLM- and NER-based anonymisers. The directories exist as placeholders; the contract (an `AnonymizeResult`-returning class) is in `base.py`.
- In-place redaction of agent-side state (e.g. the live conversation in another terminal). The anonymiser only runs at upload / donation time.
- Reversible mappings. Once a credential is replaced with `[REDACTED]`, there is no way back; once a username is hashed, the original is gone.
