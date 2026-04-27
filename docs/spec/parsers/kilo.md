# Kilo parser

Kilo (https://github.com/Kilo-Org/kilocode) is a fork of OpenCode and uses an identical Drizzle SQLite schema. The parser is a thin subclass of [`OpencodeParser`](opencode.md).

Code: [`src/vibelens/ingest/parsers/kilo.py`](../../../src/vibelens/ingest/parsers/kilo.py).

## File layout

```
~/.local/share/kilo/
  kilo.db                # PRIMARY — same Drizzle schema as opencode.db
  kilo.db-shm/-wal       # WAL companions
  storage/, snapshot/, log/   # ignored (same handling as opencode)
```

## Differences from OpenCode

| | OpenCode | Kilo |
|---|---|---|
| Database file | `opencode.db` | `kilo.db` |
| `project.icon_url_override` column | exists | absent |
| `message.data.editorContext` | always null | `{openTabs: [paths], shell: "<shell>"}` per message |

`KiloParser` inherits everything else. It overrides only:

```python
class KiloParser(OpencodeParser):
    AGENT_TYPE = AgentType.KILO
    LOCAL_DATA_DIR = Path.home() / ".local" / "share" / "kilo"
    DB_FILENAME = "kilo.db"
```

## editorContext capture (no override needed)

`OpencodeParser._build_step_from_message` opportunistically captures `message.data.editorContext` if present:

```python
editor_ctx = msg_data.get("editorContext")
if editor_ctx:
    extra["editor_context"] = editor_ctx
```

For OpenCode this is a no-op (the field is null on every observed message). For Kilo it populates `Step.extra.editor_context = {open_tabs, shell}` automatically — no override required in `KiloParser`.

## icon_url_override

The `project` table in Kilo's schema lacks the `icon_url_override` column that OpenCode has. `OpencodeParser._build_project_lookup` introspects the table via `PRAGMA table_info` and only selects columns that actually exist, so the missing column never raises.

## Sub-agent linkage

Identical to OpenCode (`tool.state.metadata.sessionId` for parent → child; `session.parent_id` for child → parent). Verified — Kilo's `task` tool metadata has `{sessionId, model.{modelID, providerID}, truncated}`, same shape. Bidirectional, depth 1 in observed data (1 parent + 4 parallel children).

## Field coverage

### Populated
- All [OpenCode populated fields](opencode.md#populated) apply (KiloParser inherits behaviour).
- **Additional**: `Step.extra.editor_context = {openTabs, shell}` from `message.data.editorContext`.

### Dropped
- Same as OpenCode minus `project.icon_url_override` (column absent in kilo; nothing to drop).

## Tests

[`tests/ingest/parsers/test_kilo.py`](../../../tests/ingest/parsers/test_kilo.py) covers OpencodeParser inheritance, editor_context population, LOCAL_DATA_DIR resolution, missing icon_url_override tolerance, kilo.db discovery, malformed db handling.
