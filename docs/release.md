# Releasing VibeLens

This document covers how VibeLens is packaged, built, and published to [PyPI](https://pypi.org/project/vibelens/).

## Package Layout

VibeLens uses [hatchling](https://hatch.pypa.io/) as its build backend. The key configuration lives in `pyproject.toml`:

```
pyproject.toml          # Package metadata, dependencies, build config
src/vibelens/           # Python source (hatchling packages this)
src/vibelens/static/    # Pre-built frontend assets (bundled into the wheel)
src/vibelens/py.typed   # PEP 561 marker for type checker support
LICENSE                 # MIT license (included in wheel automatically)
```

The `[tool.hatch.build.targets.wheel]` setting tells hatchling to package `src/vibelens/` as the top-level `vibelens` module. Everything under `src/vibelens/` — including `static/` and `py.typed` — is included in the wheel.

## Version Management

The version is defined in two places that must stay in sync:

1. `pyproject.toml` → `version = "X.Y.Z"`
2. `src/vibelens/__init__.py` → `__version__ = "X.Y.Z"`

Both must match before tagging a release.

## Building Locally

```bash
# Build wheel and sdist into dist/
uv build

# Inspect the wheel contents
unzip -l dist/vibelens-*.whl

# Install locally to test
pip install dist/vibelens-*.whl
vibelens version
```

The wheel is a zip file. You can verify it contains the frontend by checking for `vibelens/static/` entries.

## Frontend Assets

The frontend (React + Vite + Tailwind) must be built before packaging:

```bash
cd frontend
npm install
npm run build    # outputs to src/vibelens/static/
```

The publish workflow verifies that `static/` files exist in the wheel and fails if the frontend wasn't bundled. If you're building locally, make sure to build the frontend first.

## CI Workflow

**File:** `.github/workflows/ci.yml`

Runs on every push to `main` and every pull request. Tests against Python 3.12 and 3.13 in a matrix.

Steps:
1. Check out the repo
2. Install uv
3. Install the target Python version
4. `uv sync --extra dev` — install all dependencies including dev tools
5. `ruff check src/ tests/` — lint check
6. `pytest tests/ -v` — run test suite

A green CI check is required before merging PRs.

## Publishing to PyPI

**File:** `.github/workflows/publish.yml`

Publishing is fully automated via GitHub Actions. The workflow triggers when you push a tag matching `v*`.

### One-Time Setup

Before your first release, configure [trusted publishing](https://docs.pypi.org/trusted-publishers/) so GitHub Actions can publish without API tokens:

1. **PyPI:** Go to [pypi.org](https://pypi.org) → your account → Publishing → "Add a new pending publisher"
   - Package name: `vibelens`
   - Owner: `yejh123`
   - Repository: `VibeLens`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
2. **GitHub:** Go to repo Settings → Environments → create an environment named `pypi`

This uses OpenID Connect (OIDC) — PyPI trusts GitHub Actions directly, no secrets or API tokens needed.

### Release Steps

#### 1. Update version

Set the new version in both files (they must match):

- `pyproject.toml` → `version = "X.Y.Z"`
- `src/vibelens/__init__.py` → `__version__ = "X.Y.Z"`

#### 2. Update CHANGELOG.md

Add a new section at the top of `CHANGELOG.md` following the existing format. Organize entries by roadmap focus areas where applicable.

#### 3. Build the frontend (if changed)

```bash
cd frontend && npm run build && cd ..
```

#### 4. Verify locally

```bash
uv build
uv run ruff check src/ tests/
uv run pytest tests/ -v
```

#### 5. Commit, tag, and push

```bash
git add -A
git commit -m "Release vX.Y.Z"
git tag vX.Y.Z
git push origin main --tags
```

#### 6. Create a GitHub Release

```bash
gh release create vX.Y.Z --title "vX.Y.Z" --notes "$(cat <<'EOF'
Paste release notes here (use the CHANGELOG.md entry).
EOF
)"
```

Or create manually at `https://github.com/yejh123/VibeLens/releases/new`:
- **Choose tag:** `vX.Y.Z` (the tag you just pushed)
- **Release title:** `vX.Y.Z`
- **Description:** Copy the CHANGELOG.md entry for this version

The GitHub Release is what users see on the repo's Releases page. It is separate from PyPI publishing.

#### 7. Wait for PyPI publish

After pushing the tag, the `publish.yml` workflow automatically:
1. Builds the wheel with `uv build`
2. Verifies that frontend static files are present in the wheel
3. Publishes to PyPI via trusted publishing

Monitor the workflow at `https://github.com/yejh123/VibeLens/actions`.

Check the publish status:

```bash
gh run list --workflow=publish.yml --limit 1
```

#### 8. Verify the release

```bash
# Check PyPI has the new version
pip index versions vibelens

# Install from PyPI
pip install vibelens==X.Y.Z

# Or run without installing
uvx vibelens serve

# Check version
vibelens version
```

The package page will be live at [pypi.org/project/vibelens/](https://pypi.org/project/vibelens/).

### Manual Publishing

If you need to publish without GitHub Actions (e.g., debugging a failed workflow):

```bash
# Generate an API token at https://pypi.org/manage/account/token/
uv build
uv publish --token pypi-YOUR_API_TOKEN
```

### Note on GitHub Packages

The "Packages" sidebar on a GitHub Release page refers to [GitHub Packages](https://github.com/features/packages) (GitHub's own container/package registry). This is **not** PyPI. Python packages are published to PyPI only — ignore the "No packages published" message on GitHub.
