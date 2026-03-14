"""Shared test fixtures for VibeLens."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibelens.app import create_app


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
