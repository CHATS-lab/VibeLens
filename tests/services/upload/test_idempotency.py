"""Idempotency tests: re-uploading the same zip dedupes by content hash."""

import json

from vibelens.schemas.upload import UploadResult
from vibelens.services.upload.processor import find_prior_upload, load_prior_result


def _seed_metadata(upload_dir, *, upload_id, sha, agent_type, result_payload, totals=None):
    """Write a fake prior upload to upload_dir's metadata.jsonl + result.json."""
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / upload_id).mkdir(parents=True, exist_ok=True)
    result_rel = f"{upload_id}/result.json"
    (upload_dir / result_rel).write_text(
        json.dumps(result_payload), encoding="utf-8"
    )
    # Default to a successful upload so dedup considers the entry cacheable.
    # Tests can override ``totals`` to simulate failure cases.
    seeded_totals = totals if totals is not None else {"sessions_parsed": 5, "errors": 0}
    line = {
        "upload_id": upload_id,
        "agent_type": agent_type,
        "zip_sha256": sha,
        "uploaded_at": "2026-04-26T12:00:00+00:00",
        "result_path": result_rel,
        "filename": "x.zip",
        "session_token": None,
        "totals": seeded_totals,
    }
    with open(upload_dir / "metadata.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")
    return line


def test_find_prior_upload_matches_on_sha_and_agent(tmp_upload_dir):
    sha = "a" * 64
    _seed_metadata(
        tmp_upload_dir,
        upload_id="20260426120000_abcd",
        sha=sha,
        agent_type="claude",
        result_payload={"files_received": 1, "sessions_parsed": 5, "zip_sha256": sha},
    )
    entry = find_prior_upload(sha, "claude")
    assert entry is not None
    assert entry["upload_id"] == "20260426120000_abcd"


def test_find_prior_upload_does_not_cross_agent_types(tmp_upload_dir):
    """Same zip under a different agent isn't a hit — different parser run."""
    sha = "b" * 64
    _seed_metadata(
        tmp_upload_dir,
        upload_id="20260426120001_efgh",
        sha=sha,
        agent_type="claude",
        result_payload={"files_received": 1, "zip_sha256": sha},
    )
    assert find_prior_upload(sha, "kiro") is None
    assert find_prior_upload(sha, "claude") is not None


def test_find_prior_upload_returns_none_when_metadata_missing(tmp_upload_dir):
    assert find_prior_upload("c" * 64, "claude") is None


def test_find_prior_upload_skips_failed_uploads(tmp_upload_dir):
    """Don't dedup against an upload that parsed zero sessions — the user
    must be allowed to retry once the underlying issue is fixed."""
    sha = "d" * 64
    _seed_metadata(
        tmp_upload_dir,
        upload_id="20260426120002_failed",
        sha=sha,
        agent_type="codebuddy",
        result_payload={"files_received": 1, "sessions_parsed": 0, "zip_sha256": sha},
        totals={"sessions_parsed": 0, "errors": 1},
    )
    assert find_prior_upload(sha, "codebuddy") is None


def test_find_prior_upload_skips_uploads_with_errors(tmp_upload_dir):
    """Same as above but for the partial-success-with-errors case."""
    sha = "e" * 64
    _seed_metadata(
        tmp_upload_dir,
        upload_id="20260426120003_partial",
        sha=sha,
        agent_type="codebuddy",
        result_payload={"files_received": 1, "sessions_parsed": 2, "zip_sha256": sha},
        totals={"sessions_parsed": 2, "errors": 1},
    )
    assert find_prior_upload(sha, "codebuddy") is None


def test_load_prior_result_returns_validated_model(tmp_upload_dir):
    sha = "d" * 64
    entry = _seed_metadata(
        tmp_upload_dir,
        upload_id="20260426120002_ijkl",
        sha=sha,
        agent_type="codex",
        result_payload={
            "files_received": 1,
            "sessions_parsed": 3,
            "steps_stored": 42,
            "zip_sha256": sha,
            "upload_id": "20260426120002_ijkl",
        },
    )
    cached = load_prior_result(entry)
    assert isinstance(cached, UploadResult)
    assert cached.sessions_parsed == 3
    assert cached.zip_sha256 == sha


def test_load_prior_result_returns_none_when_file_missing(tmp_upload_dir):
    entry = {"result_path": "ghost/result.json"}
    assert load_prior_result(entry) is None


def test_load_prior_result_returns_none_when_path_blank(tmp_upload_dir):
    assert load_prior_result({}) is None


def test_legacy_metadata_lines_without_zip_sha256_are_ignored(tmp_upload_dir):
    """Old uploads predate idempotency; their lines must not break lookups."""
    tmp_upload_dir.mkdir(parents=True, exist_ok=True)
    legacy = {"upload_id": "old", "agent_type": "claude", "filename": "x.zip"}
    with open(tmp_upload_dir / "metadata.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(legacy) + "\n")
    assert find_prior_upload("anything", "claude") is None
