# Ingest

The layer that turns a coding agent's native session files into ATIF `Trajectory` objects everything else can consume.

## Motivation

Each agent CLI invents its own log format. Claude writes JSONL with merge-by-message-id semantics; Codex writes per-day rollouts indexed by a SQLite file; Gemini writes JSON with `parts`-based content; Cursor, Hermes, Kilo, OpenCode use SQLite as the source of truth; Kiro mixes JSONL + JSON snapshots; OpenClaw uses event-based JSONL; CodeBuddy's events share an `id` across writes. Versions change.

Without a translation layer, every downstream service — search, dashboard, friction analysis, skill analysis, donation packaging — would need per-agent code paths and would break on every upstream format bump. Ingest is that translation layer. Per-agent parsers in, ATIF out.

## Architecture

```
~/.<agent>/...                     <- the user's local data directory
       |
       v
+--------------------+
| BaseParser ABC     |   four-stage lifecycle: discover → index → parse → build
+--------------------+
       |
       v
list[Trajectory]                   <- ATIF v1.6, validated by Pydantic
```

Each parser is a single class extending `BaseParser`, registered against an `AgentType` value. `get_parser(agent_type)` is the only entry point the rest of the codebase needs.

## Key files

| File | Role |
|---|---|
| `ingest/parsers/base.py` | `BaseParser` ABC + shared lifecycle hooks |
| `ingest/parsers/__init__.py` | `LOCAL_PARSER_CLASSES`, `ALL_PARSER_CLASSES`, `get_parser` |
| `ingest/parsers/<agent>.py` | One file per parser |
| `ingest/parsers/helpers.py` | Cross-parser utilities (JSONL iteration, content extraction, metric finalisation) |
| `ingest/diagnostics.py` | Per-session parse-quality counters |
| `ingest/index_builder.py` | Builds the listing-time skeleton index across all local parsers |
| `ingest/index_cache.py` | Persistent JSON cache for the skeleton index |
| `ingest/anonymize/` | `RuleAnonymizer` (paths, credentials, PII) — see `spec-anonymize.md` |

The session-loading layer (`storage/trajectory/local.py`) drives ingest at runtime; see [`session/spec-session-loading.md`](session/spec-session-loading.md) for the warm/cold path mechanics.

## Parser inventory

Two registry lists in `ingest/parsers/__init__.py` define what's available:

- `LOCAL_PARSER_CLASSES` — parsers whose agent stores session data on the user's machine. The session-loading layer scans these directories on cold start.
- `ALL_PARSER_CLASSES` — adds the external-export and internal formats (Claude Web, Dataclaw, the pre-parsed JSON loader). Used for upload, donation, and demo-mode pipelines.

For per-agent format details and the capability matrix, see [`docs/spec/parsers/README.md`](parsers/README.md). For the full set of conventions a new parser must follow, see [`docs/spec/parsers/add-parser-skill.md`](parsers/add-parser-skill.md).

## What `BaseParser` provides

The ABC has four roles:

1. **Discovery** — `discover_session_files(data_dir)` returns the parseable files in an agent data directory. Most parsers walk the agent's known layout; SQLite-backed parsers expose the `.db` plus its `-wal` / `-shm` sidecars via `ALLOWED_EXTENSIONS` so the upload pipeline preserves them in zips.
2. **Fast indexing** — `parse_session_index(data_dir)` (optional). Parsers with a native session index (Claude's `history.jsonl`, Codex's `state_5.sqlite`, OpenClaw's `sessions.json`) implement this; the listing layer uses it to skip orphan walks.
3. **Skeleton building** — `parse_skeleton_for_file(path)`. Default: full-parse and drop steps (always correct, slow). Override when the format permits a head-only scan (Claude does this for the JSONL listing path).
4. **Full parsing** — `parse_file(path) -> list[Trajectory]`. Each parser's main entry. Returns one or more trajectories per file (multi-session files are normal for Dataclaw, Claude Web, and parsed-JSON loaders).

`BaseParser` also enforces robustness conventions every parser opts into: `iter_jsonl_safe` skips malformed lines without raising, `find_first_user_text` and `truncate_first_message` produce the listing preview, and per-step Pydantic validation runs before a `Trajectory` is returned.

## Diagnostics

`DiagnosticsCollector` rides along with each parse and records:

- malformed JSONL lines skipped,
- orphaned `tool_call` / `tool_result` pairs,
- a per-session `completeness_score` from those counts.

Diagnostics are non-fatal — a session always completes; the score is what surfaces parser drift to the user.

## Index builder

`build_session_index(file_index, data_dirs)` is what session loading calls on a cold rebuild. For each local parser it tries the fast index first, falls back to walking orphans, and only resorts to full-parse fallback when neither yields a skeleton. Skeleton work runs in a small `ThreadPoolExecutor` because per-file time is dominated by I/O.

The result is reconciled (de-duplicated by `session_id`, validated against the existing in-memory file index) and continuation refs (`prev_/next_trajectory_ref`) are filled in by walking the skeletons. Final metrics are then enriched per file via `parser.parse_file` so `total_steps == len(traj.steps)` — the contract the dashboard relies on.

## Index cache

`~/.vibelens/session_index.json` carries the skeleton index across runs. See [`session/spec-session-loading.md`](session/spec-session-loading.md) for the cache contract (`CACHE_VERSION`, `[mtime_ns, size]` keys, dropped-paths set, atomic write).

## Why no auto-detection

Earlier designs tried to fingerprint a file's format from its content. That approach is pragmatic only when the user *doesn't know* which agent produced a file — but in VibeLens the agent is always known: the upload wizard asks for it, demo mode is per-store, self-mode iterates by registered local parsers. So format is supplied, not inferred, and the per-parser format probing logic lives inside each parser's discovery path rather than in a shared classifier.
