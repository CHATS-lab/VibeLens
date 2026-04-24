# scripts/inference — Test, Verify, Report

Runner scripts for VibeLens analysis modes (`creation`, `evolution`, `recommendation`, `friction`). Use this directory when manually exercising the end-to-end inference pipeline against real sessions.

## Directory layout

| Script | Purpose |
|---|---|
| `_shared.py` | Common CLI arg parser, config overrides, session sampler, summary printers. |
| `run_creation.py` | One-shot skill-creation analysis. |
| `run_evolution.py` | One-shot skill-evolution analysis. |
| `run_recommendation.py` | One-shot recommendation analysis. |
| `run_friction.py` | One-shot friction analysis. |
| `run_all_backends.py` | Fan out one mode across multiple backends in parallel. |
| `verify.py` | Inspect an `inference.json` log to confirm reasoning/cost/config. |

## Standard workflow

Every non-trivial backend or service change follows a three-phase loop: **Test → Verify → Report**. Don't skip verification just because tests pass — `pytest` covers translation logic, not real CLI behavior.

### 1. Test — run against a real CLI

```bash
# Single backend, single mode
uv run python scripts/inference/run_evolution.py --backend codex --model gpt-5.4-mini --no-thinking --count 15

# All backends in parallel (default: 5 backends, thinking off, 15 sampled sessions)
uv run python scripts/inference/run_all_backends.py evolution

# Override per run
uv run python scripts/inference/run_all_backends.py friction --count 5
uv run python scripts/inference/run_all_backends.py creation --backends claude_code,codex
uv run python scripts/inference/run_all_backends.py evolution --sessions example-session-claude-01,other-session-id
```

Parameter reference for `run_all_backends.py`:

| Flag | Default | Purpose |
|---|---|---|
| `mode` (positional) | — | `creation` \| `evolution` \| `recommendation` \| `friction`. |
| `--backends` | `claude_code,codex,gemini,openclaw,opencode` | Comma-separated backend list. |
| `--model` | per-backend catalog default | Force one model across every backend. Don't pass a backend-specific name when fanning out — it will break other backends. |
| `--thinking` | off | Enable reasoning. Project policy is off. |
| `--count` | `15` | Random-sample N eligible sessions (≥10 steps). |
| `--sessions` | (empty) | Comma-separated explicit session IDs (overrides sampling). |

`--no-thinking` is the project default (see `config/settings.py`). Pass `--thinking` only when deliberately testing the reasoning path.

### 2. Verify — inspect the inference log

The runner prints a summary but does **not** verify that the runtime behavior matches the configured intent. Always confirm via `inference.json`:

```bash
# Latest run across any mode
uv run python scripts/inference/verify.py

# Latest for one mode
uv run python scripts/inference/verify.py --mode evolution

# A specific analysis id
uv run python scripts/inference/verify.py --id 20260424T192533-yKtuSqzm
```

The report surfaces every red flag we've hit in practice:

- `thinking=False` yet `reasoning_tokens > 0` — the CLI ignored the config, or our backend translated `thinking=False` to a non-zero effort level (e.g. Codex `low` instead of `none`).
- `cost_usd: null` on any call — `pricing.compute_cost_from_tokens` returned None (unknown model alias, or tokens missing in the envelope).
- Mismatched `config.backend` / `result.model` — the runtime backend and the log snapshot drifted (in practice, because `set_inference_backend` was called without also updating `settings.inference`).

Read the **FLAGS** block at the bottom of each report — it's the one line that tells you whether the run matched your intent. Any flag means the CLI ignored the config and the fix is likely a change in `src/vibelens/llm/backends/<backend>_cli.py`, not in the service layer.

Run locations:

| Mode | `inference.json` path |
|---|---|
| `creation` | `~/.vibelens/logs/personalization/creation/<id>/inference.json` |
| `evolution` | `~/.vibelens/logs/personalization/evolution/<id>/inference.json` |
| `recommendation` | `~/.vibelens/logs/personalization/recommendation/<id>/inference.json` |
| `friction` | `~/.vibelens/logs/friction/<id>/inference.json` |

### 3. Report — raw CLI session logs (when in doubt)

`inference.json` is our own log. If something looks off (e.g. Gemini reporting `thoughts: 0` but responses arrive slowly), cross-check the CLI's own session log. These are authoritative for "did the model actually think?":

| Backend | Raw session log location |
|---|---|
| Claude Code | `~/.claude/projects/<workspace-hash>/*.jsonl` — scan for `"type":"thinking"` content blocks. |
| Gemini | `~/.gemini/tmp/<workspace-name>/chats/session-*.json` — check `stats.models.*.tokens.thoughts`. |
| Codex | Runs with `--ephemeral`, no session files by design. Trust `turn.completed` usage. |
| OpenClaw | `~/.openclaw/logs/gateway.log` — grep `reasoning|thinking`. |
| OpenCode | `~/.local/share/opencode/log/*.log` — contains full invocation args plus NDJSON stream. |

## Cross-backend parallel validation

When changing anything in `src/vibelens/llm/backends/` — prompt shaping, thinking translation, schema handling, metrics — fan out across all backends:

```bash
uv run python scripts/inference/run_all_backends.py evolution --count 1
uv run python scripts/inference/verify.py --mode evolution --all | tail -80
```

The `run_all_backends.py` table flags any backend that exits non-zero. Per-backend quirks to watch for:

- **Gemini flash-lite with `--no-thinking`**: strict-schema types like `start_step_id: str` are often emitted as ints. Model quality drops without reasoning; not a backend bug.
- **opencode**: each provider must be authenticated separately via `opencode providers login <google|anthropic|openai|...>`. The catalog default (`google/gemini-2.5-flash`) fails silently with "no text events" when only `amazon-bedrock` is authed. Switch to a Bedrock-available model or authenticate the matching provider before fanning out.
- **Codex `--ephemeral`**: no reusable session files; rely on `inference.json` + `turn.completed` usage counts.
- **OpenClaw writes `--json` to stderr** (not stdout) — the backend already handles this via `_select_output`; don't "fix" it.

## Config override rules (important)

The runner scripts update *both* `get_settings().inference` and the backend singleton via `_shared.apply_config_overrides`. If you write an ad-hoc driver, you must do the same or `InferenceLogWriter` will record the stale on-disk config even while the correct backend runs:

```python
from vibelens.deps import get_settings, set_inference_backend
from vibelens.llm.backends import create_backend_from_config

cfg = InferenceConfig(backend=..., model=..., thinking=False)
get_settings().inference = cfg              # <-- required
set_inference_backend(create_backend_from_config(cfg))
```

Omit the first line and `inference.json`'s `config` block will lie.

## Thinking disable matrix

Reference table — what each backend does when `thinking=False`:

| Backend | Mechanism |
|---|---|
| Claude Code | `CLAUDE_CODE_DISABLE_THINKING=1` env var. Fully disables. |
| Codex | `-c web_search=disabled -c model_reasoning_effort=none`. Fully disables. |
| OpenClaw | `--thinking off`. Native flag. |
| OpenCode | `--variant minimal`. Lowest core-supported level (see [sst/opencode#4316](https://github.com/sst/opencode/issues/4316)). |
| Gemini | Project-scoped `<cwd>/.gemini/settings.json` with custom alias `vibelens-nothink` (`thinkingBudget: 0`, `includeThoughts: false`). No env var exists upstream ([google-gemini/gemini-cli#25122](https://github.com/google-gemini/gemini-cli/issues/25122)). |
| LiteLLM | Omits `thinking` / `reasoning_effort` kwargs. |
| Aider / Cursor / Kimi | Per-CLI flag. See `_thinking_args` in each backend. |
| Amp | No-op — CLI has no control. |

Updates to this matrix must be accompanied by (a) a unit test in `tests/llm/test_thinking_translation.py`, (b) a real-run verification via the workflow above.
