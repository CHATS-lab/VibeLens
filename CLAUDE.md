# CLAUDE.md — VibeLens

Agent session visualization and personalization platform.

## Key Concepts

- **Trajectory**: Root container for a single agent session — includes steps, agent metadata, final metrics, and cross-references.
- **Step**: One turn in a conversation (user prompt, agent response, or system message) with optional tool calls and observations.

## Frontend Conventions (React + Vite + Tailwind)

Refer to `DESIGN.md`

## Testing

- Ruff: `ruff check src/ tests/`
- Run: `pytest tests/ -v -s` (use `-s` to see print output).
- Tests should log detailed output with `print()` for manual verification, not just assertions.

## Release

See [`docs/release.md`](docs/release.md) for the full release flow. Short version:

1. **Version bump**: Update `version` in both `pyproject.toml` and `src/vibelens/__init__.py` (must match).
2. **Changelog**: Move `[Unreleased]` entries into a new `## [x.y.z] - YYYY-MM-DD` section.
3. **Frontend** (if changed): `cd frontend && npm run build && cd ..`.
4. **Verify**: `uv build && uv run ruff check src/ tests/ && uv run pytest tests/ -v`.
5. **Commit, tag, push**: `git commit -am "Release vX.Y.Z" && git tag vX.Y.Z && git push origin main --tags`.
6. **GitHub Release**: `gh release create vX.Y.Z --title "vX.Y.Z" --notes "..."`.
7. **PyPI**: automated by `.github/workflows/publish.yml` on tag push (trusted publishing). No twine, no API token.
