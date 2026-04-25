# Gemini parser

Parses Google Gemini CLI sessions in their native JSON format.

Code: [`src/vibelens/ingest/parsers/gemini.py`](../../../src/vibelens/ingest/parsers/gemini.py).

## File layout

```
~/.gemini/
  tmp/
    <project-hash>/                      # SHA-256 of project path
      .project_root                      # plaintext: original project path (when present)
      chats/
        session-<ISO>-<short-hash>.json  # one JSON file per session
  projects.json                          # path ↔ hash registry
```

Sub-agent sessions live in the same `chats/` directory but with `kind: subagent` inside the file (and share the parent's `sessionId`).

## Wire format

Each session is a **single JSON document** (not JSONL):

```json
{
  "sessionId": "...",
  "projectHash": "...",
  "startTime": "...",
  "lastUpdated": "...",
  "kind": "main",          // or "subagent"
  "messages": [
    {"type": "user",   "id": "...", "timestamp": "...", "content": [...]},
    {"type": "gemini", "id": "...", "timestamp": "...", "model": "...",
     "content": "...", "thoughts": [...], "toolCalls": [...], "tokens": {...}}
  ]
}
```

Important format differences from Claude/Codex:

- Tool calls and their results are **embedded inside the same gemini message**: `toolCalls[].result` is the result for the call. No cross-message pairing.
- Thinking is structured: `thoughts[]` of `{subject, description}`. We flatten to `[Subject] description` text.
- The assistant role is `type: "gemini"`; we map to `StepSource.AGENT`.
- Tokens reported as `{input, output, cached}` — `input` already includes any cached portion (so we do NOT add `cached` to `prompt_tokens` like the Anthropic-style helper).

## Parsing strategy

```
parse(content)
  ├─ json.loads(content)           # whole-file JSON
  ├─ _build_steps(messages)
  │    ├─ user messages    → coerce content list to text
  │    └─ gemini messages  → text + thoughts + toolCalls (with embedded results)
  ├─ _resolve_project              # 4-strategy chain (see below)
  └─ assemble_trajectory
```

### Project path resolution

Gemini stores files under a SHA-256 hash directory and keeps the real path elsewhere. We try four strategies in order:

1. **Filesystem layout**: file at `~/.gemini/tmp/<hash>/chats/...` → the hash dir is the cwd.
2. **`.project_root` fast path**: read `<gemini>/tmp/<hash>/.project_root` if present.
3. **`projects.json` reverse lookup**: scan path → hash mapping (current format) or `{path: {hash: ...}}` (legacy).
4. **Tool-arg inference**: walk `Step.tool_calls` for absolute paths in `file_path|path|filename|directory` arguments and take the common ancestor (or most-frequent directory). Reject paths shallower than 3 components (e.g. `/Users`).

Falls back to the hash string when nothing resolves — surfaces gracefully in the UI, just less readable.

## Index path (skeleton listing)

No fast index. `parse_session_index` returns `None` and the index builder falls through to `parse_skeleton_for_file` (default — full parse + clear steps), threaded.

A future fast-index option would be a head-of-document scan: load just `sessionId`, `startTime`, and the first user message's text without materialising the rest. Not implemented today.

## Sub-agent support

**Bidirectional**, via the shared `sessionId` on disk. Sub-agent files are identified by `kind: "subagent"` (vs `kind: "main"`) and share the parent's `sessionId`. The frontend places each sub-agent at the chronologically-correct main step using its `timestamp` (Phase 2 of `session-view.tsx`'s placement logic) since Gemini doesn't emit a per-tool-call spawn id.

**Child → parent**: a sub-agent file's `parse_session` gives the trajectory a **synthetic session_id from the filename stem** (e.g. `session-2026-03-14T16-41-97253fa9`) and writes the original in-file `sessionId` into `parent_trajectory_ref.session_id`. The synthetic id is needed because main and sub share the in-file `sessionId` — using it directly would collide in the index.

```python
if data["kind"] == "subagent":
    session_id = Path(source_path).stem            # synthetic, file-unique
    parent_ref = TrajectoryRef(session_id=data["sessionId"])  # → main
```

**Parent → child** loading: when the main session's `parse` runs, it scans the same `chats/` directory for sibling `session-*.json` files whose `kind == "subagent"` and `sessionId == main.sessionId`, parses each, and returns `[main, *subs]`. This way `store.load(main_sid)` materialises the whole tree in one call without the storage layer having to know about Gemini's file layout.

`parentSessionId` exists in the JSON schema but is observed `null` in real data (Gemini does not appear to populate it), so we don't rely on it.

## Edge cases / quirks

- **Empty content with thoughts only**: a gemini turn that produced thinking but no visible output. We use the thinking text as the message body so the turn isn't lost.
- **Tool errors**: `tool.status == "error"` → mark the observation result with `[ERROR] ` prefix.
- **Model-name drift**: Gemini doesn't persist a session-level model field. We use the most recent step's `model_name` so pricing lookup has something to match on.
- **Path inference threshold**: needs at least 2 absolute paths in tool args to attempt inference. With fewer, we skip and let the hash fall through.

## Tests

[`tests/ingest/parsers/test_gemini.py`](../../../tests/ingest/parsers/test_gemini.py) covers format decoding (toolCalls, thoughts, multimodal user content) and project-path resolution.
