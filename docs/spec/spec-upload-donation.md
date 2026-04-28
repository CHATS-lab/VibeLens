# Upload and Donation

Two features that move session data in and out of VibeLens. Upload imports a user's own agent sessions for analysis. Donation contributes sessions to academic research.

## Motivation

VibeLens analyses agent sessions, but the agents themselves write data to a dozen different on-disk layouts, with formats that vary across versions. The upload and donation features exist to make that data portable:

- **Upload (demo-mode only).** A visitor on the public demo doesn't have local data, so they zip their own agent's data on their machine, drag it into the wizard, and see their sessions inside a per-browser sandbox. No account, no server-side login.
- **Donation (both modes).** A user who wants their data preserved for research zips up the same content and ships it — together with the parsed trajectories and any git bundles needed to reproduce the analysis — to the configured research server.

The two flows share the zip-handling pipeline and a per-tab session token (`X-Session-Token`, a `crypto.randomUUID()` generated on page load) that scopes uploads to the browser tab that produced them.

## Architecture

```
                Frontend (React)
                      |
        +-------------+--------------+
        |                            |
   Upload wizard               Donate dialog
        |                            |
        v                            v
   POST /upload/zip          POST /sessions/donate
        |                            |
        v                            v
   processor.process_zip      session.donate_sessions
        |                            |
        v                            v
   per-upload DiskStore       sender.send_donation
        |                            |
        v                            v
  ~/.vibelens/uploads/        donation server
  {upload_id}/{...}              (httpx POST)
```

Uploads land on disk and become first-class stores resolved per session-token. Donations are zipped on the fly and POSTed; the receiver (demo only) simply files the zip away under `~/.vibelens/donations/`.

## Key files

| File | Role |
|------|------|
| `api/upload.py` | `GET /upload/agents`, `POST /upload/zip` |
| `api/donation.py` | `POST /sessions/donate`, `GET /sessions/donations/history`, `POST /donation/receive` |
| `services/upload/agents.py` | Per-agent registry (commands per OS, icon, friendly name) |
| `services/upload/processor.py` | Stream → validate → extract → parse → anonymize → store |
| `services/session/donation.py` | Orchestrates a donation: select sessions, delegate to sender |
| `services/donation/sender.py` | Bundle raw files + parsed trajectories + git bundles, POST to server |
| `services/donation/receiver.py` | Demo-side receiver: stream zip to disk, append to index |
| `services/session/store_resolver.py` | Per-token store lookup; the visibility boundary |
| `schemas/upload.py` | `UploadResult` |

## Storage layout

```
~/.vibelens/uploads/                      <- settings.upload.dir
+-- metadata.jsonl                        <- append-only manifest of every upload
+-- {upload_id}/
    +-- {upload_id}.zip                   <- original zip (kept for re-donation)
    +-- result.json                       <- UploadResult, served on dedup hit
    +-- index.jsonl                      <- per-upload session index
    +-- {session_id}.json                 <- parsed trajectory

~/.vibelens/donations/                    <- settings.donation.dir (demo only)
+-- index.jsonl
+-- {donation_id}.zip
```

`upload_id` format: `{YYYYMMDDHHMMSS}_{4-char-hex}`.

## Upload pipeline

`process_zip(file, agent_type, session_token, expected_sha256)`:

1. **Stream zip to disk.** 64 KB chunks; abort over `max_zip_bytes`. Reject mismatched body hash if the client sent `X-Zip-Sha256`.
2. **Validate and extract.** Path-traversal guard, symlink rejection, file-count and uncompressed-size caps. Each parser declares its own `ALLOWED_EXTENSIONS`; everything else is silently skipped (so SQLite-backed parsers extract `.db`/`-wal`/`-shm` while plain-JSON parsers don't pull random binaries).
3. **Discover.** Active parser scans the extracted tree for session files.
4. **Parse, anonymize, store.** Each session file goes through the parser, then `RuleAnonymizer`, then a per-upload `DiskStore`.
5. **Record.** Append a line to `metadata.jsonl`; write `result.json`.
6. **Register.** Bind the new store to the requesting `session_token` so the upload becomes visible without restart, and invalidate search/dashboard caches.
7. **Cleanup.** Drop the extracted dir; keep the zip for later donation.

### Idempotency / dedup

The same content uploaded twice (same `(zip_sha256, agent_type)`) reuses the prior result instead of reparsing. There are two dedup paths:

- **Header dedup** — the client computes the zip's SHA-256 in the browser and sends it as `X-Zip-Sha256`. The server scans `metadata.jsonl`, and on a hit returns the cached `result.json` *without reading the request body*. The new token is registered against the prior store so the dedup'd response is actually visible.
- **Body dedup** — when no header is sent, the server hashes during streaming and falls back to the same lookup once the bytes have landed.

Failed prior uploads (`sessions_parsed == 0` or `errors > 0`) are skipped during dedup so the user can retry once the underlying issue is fixed.

### Per-tab visibility

Every browser tab generates a `crypto.randomUUID()` on load and sends it as `X-Session-Token`. The upload registry maps `token -> [DiskStore, ...]`. `store_resolver` returns:

- demo + uploads in registry → only that token's stores
- demo + nothing in registry → shared example sessions
- self-use → the single `LocalStore`, no token filtering

On server restart, `reconstruct_upload_registry()` replays `metadata.jsonl` to rebuild the mapping.

### Error behaviour

Per-file parse errors don't fail the upload — they're logged into `UploadResult.errors` (each entry has a friendly `summary` and the raw `details`), and the rest of the zip is processed. The friendly mapping covers JSON decode errors, SQLite encryption / corruption, missing files, encoding issues, parser-bug `duplicate step IDs` from Pydantic, and zip size-limit breaches. Anything unmatched falls back to a generic message that names the exception class.

## Donation pipeline

`donate_sessions(session_ids, session_token)`:

1. **Filter.** Drop session IDs not visible to this token; reject example sessions (`"Example sessions cannot be donated"`).
2. **Collect raw files.** For uploads, include the original zip. For local sessions, include the agent's raw files (Claude Code includes sub-agent JSONLs).
3. **Bundle repos.** Resolve git roots from the trajectories, deduplicate, run `git bundle create --all` per repo.
4. **Package.** Produce a single zip containing raw files, parsed trajectory JSON, repo bundles, and a manifest (donation_id, timestamp, vibelens_version, session entries with `repo_hash`/`raw_files`, repo entries with `bundle_file`).
5. **Send.** POST to `{donation_url}/api/donation/receive` (httpx, 120 s timeout).
6. **Record.** Append to local donation history (token-scoped, hashed).

Donation history is keyed by `sha256(session_token)` so multi-user demo deployments don't leak history across browsers.

The receiver (`POST /donation/receive`, demo only) streams the zip to `~/.vibelens/donations/{donation_id}.zip` and appends to `index.jsonl`.

### Consent

The frontend gates the donate button on four explicit acknowledgements: data may contain code/paths, used for academic research (CHATS-Lab at Northeastern), user has reviewed for credentials, may be shared in anonymized form.

## Configuration

| Setting | Default |
|---|---|
| `upload.dir` | `~/.vibelens/uploads` |
| `upload.max_zip_bytes` | 10 GB |
| `upload.max_extracted_bytes` | 20 GB |
| `upload.max_file_count` | 10000 |
| `upload.stream_chunk_size` | 64 KB |
| `donation.url` | `https://vibelens.chats-lab.org` |
| `donation.dir` | `~/.vibelens/donations` |
| `storage.examples_dir` | `~/.vibelens/examples` |

## Error responses

| Scenario | Response |
|---|---|
| Upload in self-use mode | 400, "Uploads not supported in self-use mode" |
| Non-zip filename | 400, "Only .zip files are accepted" |
| Unknown `agent_type` | 400, "Unknown agent_type: …" |
| Body hash mismatches `X-Zip-Sha256` | 400, header/body diverged |
| Zip exceeds size / file-count / path-traversal checks | 400, friendly summary in body |
| Per-file parse failure | logged into `UploadResult.errors`, processing continues |
| Donation of an example session | per-session error in `DonateResult.errors` |
| Donation server unreachable | result returned with `donated: 0` and the network error |
