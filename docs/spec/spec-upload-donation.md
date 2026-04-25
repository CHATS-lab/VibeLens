# Upload and Donation

Two features that move session data in and out of VibeLens. Upload imports external agent sessions into the platform. Donation contributes sessions for academic research.

## Purpose

Upload is demo-mode only (hidden in self-use mode). It lets users bring their agent session data into VibeLens for analysis via ZIP file upload. Donation works in both modes: sessions are packaged into a ZIP and sent to the configured research server. Both features share ZIP handling infrastructure and session isolation via ephemeral browser tokens.

## Architecture

```
                     Frontend (React)
                          |
           +--------------+--------------+
           |              |              |
      Upload Dialog   Donate Button   Session Token
           |              |         (ephemeral UUID)
           v              v              |
      POST /upload/zip  POST /sessions/donate
           |              |              |
           v              v              v
     processor.      donation.       store_resolver
     process_zip()   donate_sessions()  (per-user isolation)
           |              |
           v              v
     DiskStore       sender.send_donation()
     (per-upload)    (collect + ZIP + POST)
           |              |
           v              v
     {upload_dir}/   receiver.receive_donation()
     {upload_id}/    (demo mode only)
```

## Key Files

| File | Role |
|------|------|
| `services/upload/processor.py` | Upload pipeline: stream, validate, extract, parse, anonymize, store |
| `services/upload/commands.py` | CLI command generation for agent data zipping |
| `services/donation/sender.py` | Collect sessions, bundle repos, create ZIP, send to server |
| `services/donation/receiver.py` | Receive donation ZIP (demo mode) |
| `services/session/donation.py` | Orchestration: filter donatable IDs, delegate to sender |
| `services/session/store_resolver.py` | Per-user store resolution and session isolation |
| `api/upload.py` | Upload endpoints |
| `api/donation.py` | Donation endpoints |
| `schemas/upload.py` | Upload request/response models |

## Storage Layout

### Uploads

```
~/.vibelens/uploads/                     <- settings.upload_dir
+-- metadata.jsonl                       <- Global upload manifest (append-only)
+-- {upload_id}/                         <- Per-upload subdirectory
    +-- {upload_id}.zip                  <- Original zip (permanent archive)
    +-- _index.jsonl                     <- Session index (tagged with _upload_id)
    +-- {session_id}.json                <- Parsed trajectory
```

### Donations (Receiver)

```
~/.vibelens/donations/                   <- settings.donation_dir
+-- index.jsonl                          <- Append-only donation index
+-- {donation_id}.zip                    <- Received donation ZIP
```

## Upload Feature

### Upload ID Format

`{YYYYMMDDHHMMSS}_{4-char-hex}` (e.g., `20260329143012_a1b2`)

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/upload/commands` | Platform-specific CLI command for zipping agent data |
| `POST` | `/upload/zip` | Accept multipart ZIP upload |

### Upload Pipeline

`process_zip(file, agent_type, session_token)`:

1. **Stream to disk** -- Write ZIP in chunks. Abort if exceeds `max_zip_bytes`.
2. **Validate and extract** -- Reject path traversal, symlinks, oversized archives, non-allowed extensions.
3. **Discover session files** -- Agent-specific discovery logic.
4. **Parse, anonymize, store** -- Create per-upload DiskStore. Parse via agent parser, run through `RuleAnonymizer`, save trajectories.
5. **Record metadata** -- Append to `metadata.jsonl`.
6. **Register and invalidate** -- Make upload visible via `register_upload_store()`. Invalidate search/dashboard caches.
7. **Cleanup** -- Remove extracted directory, keep ZIP.

## Session Isolation

Each browser tab generates a `crypto.randomUUID()` on page load (never persisted). Sent as `X-Session-Token` on every request.

- **Demo with uploads**: `store_resolver` returns only the user's registered DiskStores
- **Demo without uploads**: falls back to shared example sessions
- **Self-use**: delegates to single `LocalStore`, no token filtering

On restart, `reconstruct_upload_registry()` reads `metadata.jsonl` and restores per-token store mappings.

## Donation Feature

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions/donate` | Initiate donation from frontend |
| `POST` | `/api/donation/receive` | Server-to-server: receive donation ZIP |

### Sender Pipeline

`send_donation(session_ids, session_token)`:

1. **Collect sessions** -- Resolve source files from store. For uploads: include original ZIP. For local: include raw JSONL (with sub-agents for Claude Code).
2. **Bundle repos** -- Resolve git roots, deduplicate, run `git bundle create --all` per repo.
3. **Create ZIP** -- Package sessions, parsed trajectories, repo bundles, and manifest.
4. **Send** -- POST to `{donation_url}/api/donation/receive` via httpx (120s timeout).
5. **Cleanup** -- Delete temp files.

### Manifest Format

```json
{
  "donation_id": "20260330120000_abcd",
  "timestamp": "2026-03-30T15:30:45+00:00",
  "vibelens_version": "0.9.15",
  "sessions": [
    {
      "session_id": "uuid-1",
      "agent_type": "claude_code",
      "repo_hash": "a1b2c3d4",
      "trajectory_count": 3,
      "step_count": 142,
      "raw_files": ["sessions/raw/claude_code/projects/.../uuid.jsonl"]
    }
  ],
  "repos": [
    {
      "repo_hash": "a1b2c3d4",
      "bundle_file": "repos/a1b2c3d4.bundle",
      "session_ids": ["uuid-1"]
    }
  ]
}
```

### Receiver Pipeline

`receive_donation(file)`: Stream ZIP to disk -> read manifest -> rename file -> append to index.

### Consent

Frontend requires explicit agreement to four statements before donating: data may contain code/paths, used for academic research (CHATS-Lab at Northeastern), user has reviewed for no credentials, may be shared in anonymized form.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `upload_dir` | `~/.vibelens/uploads` | Upload storage base |
| `examples_dir` | `~/.vibelens/examples` | Demo example sessions |
| `donation_url` | `https://vibelens.chats-lab.org` | Donation server URL |
| `donation_dir` | `~/.vibelens/donations` | Received donations (demo) |
| `max_zip_bytes` | 10 GB | Max ZIP file size |
| `max_extracted_bytes` | 20 GB | Max uncompressed size |
| `max_file_count` | 10,000 | Max files in archive |
| `stream_chunk_size` | 64 KB | Streaming chunk size |

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Upload in self-use mode | 400 "Uploads not supported" |
| Non-ZIP file | 400 "Only .zip files accepted" |
| Unknown agent_type | 400 "Unknown agent_type" |
| ZIP exceeds size limit | 400, partial file deleted |
| Path traversal in ZIP | ValueError during validation |
| Single file parse failure | Logged, added to errors, other files continue |
| Session not accessible for donation | Per-session error |
| Example session donation | "Example sessions cannot be donated" |
| HTTP error during send | Error in response, `donated: 0` |
