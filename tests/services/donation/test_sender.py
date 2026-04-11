"""Tests for vibelens.services.donation.sender — repo bundling, ZIP layout, manifest."""

import json
import tempfile
import zipfile
from pathlib import Path

from vibelens.services.donation.sender import (
    _create_donation_zip,
    _RepoBundle,
    _resolve_repo_bundles,
    _SessionCollectionResult,
    _SessionData,
)
from vibelens.utils.git import resolve_git_root

# VibeLens repo root (this test file lives inside it)
REPO_ROOT = Path(__file__).resolve().parents[3]

DONATION_ID = "20260401120000_test"


def _make_session(
    session_id: str, project_path: str | None = None, git_branch: str | None = None
) -> _SessionData:
    """Create a minimal _SessionData for testing."""
    return _SessionData(
        session_id=session_id,
        agent_type="claude_code",
        raw_files=[],
        parsed_json=json.dumps([{"session_id": session_id}]),
        trajectory_count=1,
        step_count=10,
        project_path=project_path,
        git_branch=git_branch,
    )


def test_resolve_repo_bundles_with_real_repo():
    """_resolve_repo_bundles creates a bundle for a real git repo."""
    sessions = [
        _make_session("sess-1", project_path=str(REPO_ROOT / "src")),
        _make_session("sess-2", project_path=str(REPO_ROOT / "tests")),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        bundles, repo_hash_map = _resolve_repo_bundles(sessions, Path(tmp))
        print(f"bundles = {bundles}")
        print(f"repo_hash_map = {repo_hash_map}")

        # Both sessions point to the same repo, so only one bundle
        assert len(bundles) == 1
        bundle = bundles[0]
        assert len(bundle.repo_hash) == 8
        assert bundle.bundle_path.exists()
        assert bundle.bundle_size > 0

        # Both sessions mapped to the same repo_hash
        assert repo_hash_map["sess-1"] == bundle.repo_hash
        assert repo_hash_map["sess-2"] == bundle.repo_hash

        # Bundle lists both session IDs
        assert sorted(bundle.session_ids) == ["sess-1", "sess-2"]

        # Original sessions are NOT mutated
        assert sessions[0].repo_hash is None
        assert sessions[1].repo_hash is None
        print(f"repo_hash = {bundle.repo_hash}, size = {bundle.bundle_size}")


def test_resolve_repo_bundles_skips_none_project_paths():
    """Sessions with None project_path are silently skipped."""
    sessions = [
        _make_session("sess-1", project_path=None),
        _make_session("sess-2", project_path=None),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        bundles, repo_hash_map = _resolve_repo_bundles(sessions, Path(tmp))
        print(f"bundles (all None) = {bundles}")
        assert bundles == []
        assert repo_hash_map == {}


def test_resolve_repo_bundles_skips_nonexistent_paths():
    """Sessions with non-existent project_path are skipped gracefully."""
    sessions = [_make_session("sess-1", project_path="/nonexistent/fake/path")]
    with tempfile.TemporaryDirectory() as tmp:
        bundles, repo_hash_map = _resolve_repo_bundles(sessions, Path(tmp))
        print(f"bundles (nonexistent) = {bundles}")
        assert bundles == []
        assert repo_hash_map == {}


def test_zip_layout_sessions_prefix():
    """ZIP entries use sessions/raw/ and sessions/parsed/ prefixes."""
    # Create a temp file to act as a raw session file
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as raw_file:
        raw_file.write(b'{"type": "test"}\n')
        raw_path = Path(raw_file.name)

    try:
        session = _make_session("sess-abc")
        session.raw_files = [(raw_path, "sessions/raw/claude_code/projects/test/sess-abc.jsonl")]

        collection = _SessionCollectionResult()
        collection.valid_sessions = [session]

        zip_path = _create_donation_zip(collection, DONATION_ID)
        try:
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                print(f"ZIP entries: {names}")

                # Check sessions/raw/ prefix
                raw_entries = [n for n in names if "/sessions/raw/" in n]
                assert len(raw_entries) == 1
                assert "sessions/raw/claude_code/" in raw_entries[0]

                # Check sessions/parsed/ prefix
                parsed_entries = [n for n in names if "/sessions/parsed/" in n]
                assert len(parsed_entries) == 1
                assert parsed_entries[0] == f"{DONATION_ID}/sessions/parsed/sess-abc.json"

                # Manifest at root level
                manifest_entry = f"{DONATION_ID}/manifest.json"
                assert manifest_entry in names
        finally:
            zip_path.unlink(missing_ok=True)
    finally:
        raw_path.unlink(missing_ok=True)


def test_zip_includes_repo_bundles():
    """ZIP includes repos/ entries when bundles are provided."""
    session = _make_session("sess-1", git_branch="main")
    session.repo_hash = "a1b2c3d4"

    collection = _SessionCollectionResult()
    collection.valid_sessions = [session]

    # Create a fake bundle file
    with tempfile.NamedTemporaryFile(suffix=".bundle", delete=False) as bf:
        bf.write(b"fake-bundle-data")
        bundle_path = Path(bf.name)

    try:
        bundles = [_RepoBundle(repo_hash="a1b2c3d4", bundle_path=bundle_path, bundle_size=16)]
        zip_path = _create_donation_zip(collection, DONATION_ID, bundles)
        try:
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                print(f"ZIP entries with bundle: {names}")

                bundle_entry = f"{DONATION_ID}/repos/a1b2c3d4.bundle"
                assert bundle_entry in names

                # Verify bundle content
                assert zf.read(bundle_entry) == b"fake-bundle-data"
        finally:
            zip_path.unlink(missing_ok=True)
    finally:
        bundle_path.unlink(missing_ok=True)


def test_manifest_contains_repos_and_session_fields():
    """Manifest includes repos array and per-session repo_hash/git_branch."""
    session = _make_session("sess-1", git_branch="feature-x")
    session.repo_hash = "deadbeef"

    collection = _SessionCollectionResult()
    collection.valid_sessions = [session]

    # Create a fake bundle
    with tempfile.NamedTemporaryFile(suffix=".bundle", delete=False) as bf:
        bf.write(b"x" * 100)
        bundle_path = Path(bf.name)

    try:
        bundles = [
            _RepoBundle(
                repo_hash="deadbeef",
                bundle_path=bundle_path,
                bundle_size=100,
                session_ids=["sess-1"],
            )
        ]
        zip_path = _create_donation_zip(collection, DONATION_ID, bundles)
        try:
            with zipfile.ZipFile(zip_path) as zf:
                manifest_raw = zf.read(f"{DONATION_ID}/manifest.json")
                manifest = json.loads(manifest_raw)
                print(f"manifest = {json.dumps(manifest, indent=2)}")

                # Top-level repos array with session_ids
                assert "repos" in manifest
                assert len(manifest["repos"]) == 1
                repo_entry = manifest["repos"][0]
                assert repo_entry["repo_hash"] == "deadbeef"
                assert repo_entry["bundle_file"] == "repos/deadbeef.bundle"
                assert repo_entry["bundle_size_bytes"] == 100
                assert repo_entry["session_ids"] == ["sess-1"]

                # Per-session fields
                sess_entry = manifest["sessions"][0]
                assert sess_entry["repo_hash"] == "deadbeef"
                assert sess_entry["git_branch"] == "feature-x"
        finally:
            zip_path.unlink(missing_ok=True)
    finally:
        bundle_path.unlink(missing_ok=True)


def test_manifest_omits_repos_when_empty():
    """Manifest does not include repos key when no bundles exist."""
    session = _make_session("sess-1")
    collection = _SessionCollectionResult()
    collection.valid_sessions = [session]

    zip_path = _create_donation_zip(collection, DONATION_ID, repo_bundles=[])
    try:
        with zipfile.ZipFile(zip_path) as zf:
            manifest = json.loads(zf.read(f"{DONATION_ID}/manifest.json"))
            print(f"manifest (no repos) = {json.dumps(manifest, indent=2)}")
            assert "repos" not in manifest
    finally:
        zip_path.unlink(missing_ok=True)


def test_resolve_repo_bundles_deduplicates_project_paths(monkeypatch):
    """Identical project_path strings only call resolve_git_root once."""
    same_path = str(REPO_ROOT / "src")
    sessions = [
        _make_session("sess-1", project_path=same_path),
        _make_session("sess-2", project_path=same_path),
        _make_session("sess-3", project_path=same_path),
    ]

    call_count = 0
    original_resolve = resolve_git_root

    def counting_resolve(path):
        nonlocal call_count
        call_count += 1
        return original_resolve(path)

    monkeypatch.setattr("vibelens.services.donation.sender.resolve_git_root", counting_resolve)

    with tempfile.TemporaryDirectory() as tmp:
        bundles, repo_hash_map = _resolve_repo_bundles(sessions, Path(tmp))
        print(f"resolve_git_root called {call_count} time(s) for 3 sessions")

        # Only one subprocess call despite 3 sessions with the same path
        assert call_count == 1
        assert len(bundles) == 1
        assert len(repo_hash_map) == 3
        assert sorted(bundles[0].session_ids) == ["sess-1", "sess-2", "sess-3"]
