# Parsed-trajectory parser

Round-trips Trajectory objects that VibeLens itself wrote to disk.

Code: [`src/vibelens/ingest/parsers/parsed.py`](../../../src/vibelens/ingest/parsers/parsed.py).

## Why this parser exists

VibeLens's [`DiskStore`](../../../src/vibelens/storage/trajectory/disk.py) saves Trajectory objects as JSON files. Reading them back uses the same parser-driven loading path as LocalStore so DiskStore doesn't need its own deserialiser. This parser is the bridge.

## File layout

```
<disk-store-root>/
  <session-id>.json        # JSON object OR array of trajectory dicts
```

Both shapes are accepted — a single trajectory dict or a JSON array of dicts. The parser handles both.

## Wire format

Whatever `Trajectory.model_dump()` produces. The only convention is that the JSON shape matches the Pydantic model's [ATIF schema](../spec-models-trajectory.md).

## Parsing strategy

```
parse(file_path)                                # multi-session-per-file: overrides parse()
  ├─ json.loads(file_path.read_text())          # array or single dict
  └─ for each item: Trajectory(**item)          # Pydantic deserialise
```

That's it. No format-specific logic.

## Index path / sub-agents / edge cases

- **Not in `LOCAL_PARSER_CLASSES`** — only DiskStore uses it.
- **No skeleton-only path** — parsing is already very cheap (Pydantic on a few KB of JSON).
- **Sub-agents**: whatever the source parser captured comes through unchanged. If the source had sub-agent linkage (Claude), `parent_trajectory_ref` and `subagent_trajectory_ref` round-trip correctly.
- **Decoding errors**: a malformed file logs a warning and yields no trajectories — DiskStore treats absent files as empty, so the caller never sees an exception.

## Tests

Round-trip coverage lives with DiskStore tests rather than parser-specific tests, since the parser is just a thin Pydantic constructor wrapper.
