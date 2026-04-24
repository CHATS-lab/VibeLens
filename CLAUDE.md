# CLAUDE.md — VibeLens

Agent session visualization and personalization platform.

## Backend Layering

The `src/vibelens/` tree has a strict dependency direction. Each layer may import from layers above it in this list, never below:

1. `utils/` — base layer. **No intra-project deps.** Pure Python helpers only.
2. `models/` — Pydantic schemas. Depends on `utils/`.
3. `llm/`, `context/` — depend on `models/`, `utils/`. `context/` may depend on `llm/` (tokenizer).
4. `storage/` — depends on `models/`, `utils/`.
5. `services/` — depends on `llm/`, `context/`, `models/`, `storage/`, `utils/`.
6. `api/`, `deps/` — depend on `services/`, `schemas/`.

Rules of thumb:
- Shared helpers between `llm/` and `services/` live in `utils/`.
- Never move code into `utils/` if it requires a project import — extract the pure part, leave the rest at its layer.
- If a helper exists in `services/` but has no service-layer dep, it belongs in `utils/` or `context/`.
- `services/inference_shared.py` is the inference-orchestration hub.

## Frontend Conventions (React + Vite + Tailwind)

Refer to `DESIGN.md` for visual/layout conventions.

Code conventions:
- **I/O lives in `frontend/src/api/<domain>.ts`**. Components never call `fetchWithToken` directly — they take a client from the matching `<domain>Client(fetchWithToken)` factory. One factory per API domain (analysis, llm, sessions, dashboard, upload, donation, extensions). Memoize with `useMemo` so references are stable.
- **Cross-cutting state lives in `frontend/src/hooks/`**. Always reuse existing patterns.
- **Don't notify a parent via `useEffect`** (`useEffect(() => onChange?.(x), [x])`). Wrap the setter and call the callback at the state-change site.
- **Shared timing constants live in `frontend/src/constants.ts`** (`COPY_FEEDBACK_MS`, `JOB_POLL_INTERVAL_MS`, `SEARCH_DEBOUNCE_MS`). Don't redeclare per file.

Before commit (frontend changes):
- `cd frontend && npx tsc --noEmit` — type check (fast).
- `cd frontend && npm run test` — vitest suite (<1s).
- `cd frontend && npm run build` — build into `src/vibelens/static/`. Commit the static output.

## Testing

The full suite takes ~5m. Run only what you need:

- **Default during edits:** target the test file(s) that exercise the code you changed. `uv run pytest tests/<path>/<file>.py -v -s`.
- **Multi-file change:** run the test directory matching the area, e.g. `uv run pytest tests/storage/ tests/ingest/`.
- **Big change** (touching ≥3 areas, refactoring shared code, or changing public API): run the whole suite once at the end. `uv run pytest tests/`.
- **Always before commit:** `uv run ruff check src/ tests/`. Cheap.

Conventions:

- Tests should log detailed output with `print()` for manual verification, not just assertions.
- Use `-s` to see print output when iterating.

## Release

Canonical flow: [`docs/release.md`](docs/release.md). User-facing entry points: [`README.md`](README.md) (PyPI badge, [CHANGELOG](CHANGELOG.md) link).

Quick-reference for executing a release:

1. **Version bump**: update `version` in `pyproject.toml` and `__version__` in `src/vibelens/__init__.py`. They must match.
2. **CHANGELOG**: promote `[Unreleased]` entries into a new `## [X.Y.Z] - YYYY-MM-DD` section. Keep the `[Unreleased]` heading empty for the next cycle.
3. **Catalog**: Skip.
4. **Frontend** (only if `frontend/src/` changed): `cd frontend && npm run build && cd ..`. Commit `src/vibelens/static/`.
5. **Verify**: `uv run ruff check src/ tests/ && uv run pytest tests/ && uv build`.
6. **Tag and push**: `git commit -am "Release vX.Y.Z" && git tag vX.Y.Z && git push origin main --tags`. Trusted publishing on PyPI (`.github/workflows/publish.yml`) takes over from the tag push — no token, no `twine`.
7. **GitHub Release** (use the CHANGELOG entry as the body): `gh release create vX.Y.Z --title "vX.Y.Z" --notes "$(...)"`.
