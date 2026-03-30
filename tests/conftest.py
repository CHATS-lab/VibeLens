"""Shared test fixtures for VibeLens."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import vibelens.deps as deps
from vibelens.app import create_app


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Clear all cached singletons between tests for full isolation."""
    deps.reset_singletons()
    yield
    deps.reset_singletons()


@pytest.fixture
def test_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Create a FastAPI test client with temporary Claude directory."""
    monkeypatch.setenv("VIBELENS_CLAUDE_DIR", str(tmp_path / "claude"))

    app = create_app()
    return TestClient(app)
