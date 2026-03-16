"""Shared test fixtures for VibeLens."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import vibelens.api.deps as deps
import vibelens.db as db
from vibelens.app import create_app


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset module-level singletons between tests."""
    deps._settings = None
    deps._local_source = None
    deps._hf_source = None
    deps._mongodb_target = None
    deps._mongodb_source = None
    db._db_path = None
    yield
    deps._settings = None
    deps._local_source = None
    deps._hf_source = None
    deps._mongodb_target = None
    deps._mongodb_source = None
    db._db_path = None


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Return a temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def test_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Create a FastAPI test client with temporary database."""
    monkeypatch.setenv("VIBELENS_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("VIBELENS_CLAUDE_DIR", str(tmp_path / "claude"))

    app = create_app()
    return TestClient(app)
