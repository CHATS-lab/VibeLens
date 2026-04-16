"""Tests for donation API endpoints — history isolation by session token."""

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from vibelens.app import create_app
from vibelens.services.donation import SENDER_INDEX_FILENAME
from vibelens.services.donation.history import hash_token


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Point settings.donation.dir at a temporary directory and return a TestClient."""
    donation_dir = tmp_path / "donations"

    class _Donation:
        dir = donation_dir
        url = "https://example.test"

    class _Settings:
        donation = _Donation()

    monkeypatch.setattr(
        "vibelens.services.donation.history.get_settings",
        lambda: _Settings(),
    )
    app = create_app()
    return TestClient(app)


def _write(path, *, donation_id, session_count, donated_at, token):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "donation_id": donation_id,
                    "session_count": session_count,
                    "donated_at": donated_at.isoformat(),
                    "session_token_hash": hash_token(token),
                }
            )
            + "\n"
        )


def test_history_empty_when_no_file(client, tmp_path):
    resp = client.get(
        "/api/sessions/donations/history",
        headers={"X-Session-Token": "browser-A"},
    )
    print(f"status = {resp.status_code}, body = {resp.json()}")
    assert resp.status_code == 200
    assert resp.json() == {"entries": []}


def test_history_returns_only_matching_token(client, tmp_path):
    path = tmp_path / "donations" / SENDER_INDEX_FILENAME
    _write(
        path,
        donation_id="a1",
        session_count=2,
        donated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        token="browser-A",
    )
    _write(
        path,
        donation_id="b1",
        session_count=1,
        donated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        token="browser-B",
    )

    resp_a = client.get(
        "/api/sessions/donations/history",
        headers={"X-Session-Token": "browser-A"},
    )
    resp_b = client.get(
        "/api/sessions/donations/history",
        headers={"X-Session-Token": "browser-B"},
    )
    resp_none = client.get("/api/sessions/donations/history")
    print(f"a = {resp_a.json()}, b = {resp_b.json()}, none = {resp_none.json()}")

    assert [e["donation_id"] for e in resp_a.json()["entries"]] == ["a1"]
    assert [e["donation_id"] for e in resp_b.json()["entries"]] == ["b1"]
    assert resp_none.json() == {"entries": []}


def test_history_never_leaks_token_hash(client, tmp_path):
    path = tmp_path / "donations" / SENDER_INDEX_FILENAME
    _write(
        path,
        donation_id="a1",
        session_count=2,
        donated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        token="browser-A",
    )

    resp = client.get(
        "/api/sessions/donations/history",
        headers={"X-Session-Token": "browser-A"},
    )
    body = resp.json()
    print(f"body = {body}")
    entry = body["entries"][0]
    assert "session_token_hash" not in entry
    assert set(entry.keys()) == {"donation_id", "session_count", "donated_at"}
