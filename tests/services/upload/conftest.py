"""Shared fixtures for upload tests."""

import io
import zipfile
from pathlib import Path

import pytest

from vibelens.deps import get_settings
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Agent, Step, Trajectory


@pytest.fixture
def tmp_upload_dir(tmp_path: Path, monkeypatch) -> Path:
    """Redirect settings.upload.dir to a temp dir for the duration of the test."""
    settings = get_settings()
    monkeypatch.setattr(settings.upload, "dir", tmp_path)
    return tmp_path


@pytest.fixture
def claude_zip_bytes() -> bytes:
    """Minimal valid Claude Code zip the parser will accept."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "projects/abc/sample.jsonl",
            '{"type":"user","sessionId":"sess-1","timestamp":"2026-01-01T00:00:00Z",'
            '"message":{"role":"user","content":[{"type":"text","text":"hi"}]}}\n',
        )
    return buf.getvalue()


@pytest.fixture
def sample_trajectory():
    """Factory: minimal Trajectory with one user step."""

    def _make(session_id: str = "test-1") -> Trajectory:
        return Trajectory(
            session_id=session_id,
            agent=Agent(name="claude"),
            steps=[
                Step(
                    step_id=f"{session_id}-s1",
                    source=StepSource.USER,
                    message="hello /Users/alice/file.txt",
                ),
            ],
        )

    return _make
