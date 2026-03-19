"""Shared test fixtures for VibeLens."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import vibelens.deps as deps
from vibelens.app import create_app


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset module-level singletons between tests."""
    deps._settings = None
    deps._store = None
    yield
    deps._settings = None
    deps._store = None


@pytest.fixture
def test_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Create a FastAPI test client with temporary Claude directory."""
    monkeypatch.setenv("VIBELENS_CLAUDE_DIR", str(tmp_path / "claude"))

    app = create_app()
    return TestClient(app)
