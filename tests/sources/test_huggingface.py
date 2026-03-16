"""Tests for the HuggingFace data source with mocked HTTP."""

import json
from unittest.mock import patch

import pytest
import pytest_asyncio

from vibelens.db import init_db, query_sessions
from vibelens.models.requests import RemoteSessionsQuery
from vibelens.models.session import DataSourceType
from vibelens.sources.huggingface import HuggingFaceSource

SAMPLE_RECORDS = [
    {
        "session_id": f"session-{i}",
        "model": "claude-opus-4-6",
        "project": f"/home/user/project-{i % 3}",
        "git_branch": "main",
        "start_time": f"2025-01-{15 + i}T10:00:00Z",
        "end_time": f"2025-01-{15 + i}T10:30:00Z",
        "messages": [
            {
                "role": "user",
                "content": f"User message for session {i}",
                "timestamp": f"2025-01-{15 + i}T10:00:00Z",
            },
            {
                "role": "assistant",
                "content": f"Assistant response for session {i}",
                "timestamp": f"2025-01-{15 + i}T10:00:05Z",
                "tool_uses": [{"tool": "Read", "input": "file.py"}],
            },
        ],
        "stats": {
            "user_messages": 1,
            "assistant_messages": 1,
            "tool_uses": 1,
            "input_tokens": 1000,
            "output_tokens": 500,
        },
    }
    for i in range(5)
]

SAMPLE_METADATA = {
    "total_sessions": 5,
    "total_messages": 10,
    "export_date": "2025-01-20",
}


def _make_conversations_content() -> bytes:
    """Build JSONL bytes from sample records."""
    lines = [json.dumps(r) for r in SAMPLE_RECORDS]
    return ("\n".join(lines) + "\n").encode()


def _make_metadata_content() -> bytes:
    """Build metadata JSON bytes."""
    return json.dumps(SAMPLE_METADATA).encode()


@pytest_asyncio.fixture
async def db_conn(tmp_path):
    """Initialize a temporary database and return a connection."""
    import aiosqlite

    db_path = tmp_path / "test.db"
    await init_db(db_path)
    conn = await aiosqlite.connect(str(db_path))
    yield conn
    await conn.close()


@pytest.fixture
def hf_source(tmp_path) -> HuggingFaceSource:
    """Create a HuggingFaceSource with temporary data dir."""
    return HuggingFaceSource(tmp_path)


@pytest.fixture
def repo_id() -> str:
    return "test-org/test-dataset"


def _write_cached_files(source: HuggingFaceSource, repo_id: str) -> None:
    """Write conversations.jsonl and metadata.json to the cache dir."""
    repo_dir = source._repo_dir(repo_id)
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "conversations.jsonl").write_bytes(_make_conversations_content())
    (repo_dir / "metadata.json").write_bytes(_make_metadata_content())


class TestPullRepo:
    """Tests for HuggingFaceSource.pull_repo."""

    @pytest.mark.asyncio
    async def test_pull_from_cache(self, hf_source, db_conn, repo_id):
        """Pull with pre-cached files should import without downloading."""
        _write_cached_files(hf_source, repo_id)

        result = await hf_source.pull_repo(db_conn, repo_id)

        assert result.repo_id == repo_id
        assert result.sessions_imported == 5
        assert result.messages_imported == 10
        assert result.skipped == 0

    @pytest.mark.asyncio
    async def test_pull_idempotent(self, hf_source, db_conn, repo_id):
        """Second pull should skip all sessions."""
        _write_cached_files(hf_source, repo_id)

        await hf_source.pull_repo(db_conn, repo_id)
        result = await hf_source.pull_repo(db_conn, repo_id)

        assert result.sessions_imported == 0
        assert result.skipped == 5

    @pytest.mark.asyncio
    async def test_pull_force_reimports(self, hf_source, db_conn, repo_id):
        """Force refresh should delete and re-import."""
        _write_cached_files(hf_source, repo_id)

        await hf_source.pull_repo(db_conn, repo_id)

        async def mock_download(rid, filename, dest):
            if filename == "conversations.jsonl":
                dest.write_bytes(_make_conversations_content())
            elif filename == "metadata.json":
                dest.write_bytes(_make_metadata_content())

        with patch.object(hf_source, "_download_file", side_effect=mock_download):
            result = await hf_source.pull_repo(db_conn, repo_id, force_refresh=True)

        assert result.sessions_imported == 5
        assert result.skipped == 0

    @pytest.mark.asyncio
    async def test_pull_downloads_when_not_cached(self, hf_source, db_conn, repo_id):
        """Should call _download_file when files aren't cached."""
        download_calls = []

        async def mock_download(rid, filename, dest):
            download_calls.append((rid, filename))
            if filename == "conversations.jsonl":
                dest.write_bytes(_make_conversations_content())
            elif filename == "metadata.json":
                dest.write_bytes(_make_metadata_content())

        with patch.object(hf_source, "_download_file", side_effect=mock_download):
            result = await hf_source.pull_repo(db_conn, repo_id)

        assert len(download_calls) == 2
        filenames = {c[1] for c in download_calls}
        assert filenames == {"conversations.jsonl", "metadata.json"}
        assert result.sessions_imported == 5

    @pytest.mark.asyncio
    async def test_sessions_stored_in_db(self, hf_source, db_conn, repo_id):
        """Imported sessions should be queryable from the DB."""
        _write_cached_files(hf_source, repo_id)
        await hf_source.pull_repo(db_conn, repo_id)

        sessions = await query_sessions(db_conn, source_type="huggingface")
        assert len(sessions) == 5
        for s in sessions:
            assert s.source_type == DataSourceType.HUGGINGFACE
            assert s.source_name == repo_id

    @pytest.mark.asyncio
    async def test_source_name_set_on_summary(self, hf_source, db_conn, repo_id):
        """Pulled sessions should have source_name set to repo_id."""
        _write_cached_files(hf_source, repo_id)
        await hf_source.pull_repo(db_conn, repo_id)

        sessions = await query_sessions(db_conn, source_type="huggingface")
        for s in sessions:
            assert s.source_name == repo_id


class TestListRepos:
    """Tests for HuggingFaceSource.list_repos."""

    def test_no_repos(self, hf_source):
        assert hf_source.list_repos() == []

    def test_cached_repos_listed(self, hf_source, repo_id):
        _write_cached_files(hf_source, repo_id)
        repos = hf_source.list_repos()

        assert len(repos) == 1
        assert repos[0]["repo_id"] == repo_id
        assert repos[0]["cached"] is True
        assert repos[0]["metadata"]["total_sessions"] == 5

    def test_multiple_repos(self, hf_source):
        _write_cached_files(hf_source, "org/dataset-a")
        _write_cached_files(hf_source, "org/dataset-b")

        repos = hf_source.list_repos()
        assert len(repos) == 2
        repo_ids = {r["repo_id"] for r in repos}
        assert "org/dataset-a" in repo_ids
        assert "org/dataset-b" in repo_ids


class TestListSessions:
    """Tests for HuggingFaceSource.list_sessions."""

    @pytest.mark.asyncio
    async def test_list_sessions(self, hf_source, db_conn, repo_id):
        _write_cached_files(hf_source, repo_id)
        await hf_source.pull_repo(db_conn, repo_id)

        query = RemoteSessionsQuery(limit=10)
        sessions = await hf_source.list_sessions(db_conn, query)
        assert len(sessions) == 5

    @pytest.mark.asyncio
    async def test_list_sessions_with_project_filter(self, hf_source, db_conn, repo_id):
        _write_cached_files(hf_source, repo_id)
        await hf_source.pull_repo(db_conn, repo_id)

        query = RemoteSessionsQuery(project_id="project-0", limit=100)
        sessions = await hf_source.list_sessions(db_conn, query)
        for s in sessions:
            assert s.project_name == "project-0"

    @pytest.mark.asyncio
    async def test_list_sessions_pagination(self, hf_source, db_conn, repo_id):
        _write_cached_files(hf_source, repo_id)
        await hf_source.pull_repo(db_conn, repo_id)

        query = RemoteSessionsQuery(limit=2, offset=0)
        page1 = await hf_source.list_sessions(db_conn, query)
        assert len(page1) == 2

        query = RemoteSessionsQuery(limit=2, offset=2)
        page2 = await hf_source.list_sessions(db_conn, query)
        assert len(page2) == 2

        ids1 = {s.session_id for s in page1}
        ids2 = {s.session_id for s in page2}
        assert ids1.isdisjoint(ids2)


class TestGetSession:
    """Tests for HuggingFaceSource.get_session."""

    @pytest.mark.asyncio
    async def test_get_existing_session(self, hf_source, db_conn, repo_id):
        _write_cached_files(hf_source, repo_id)
        await hf_source.pull_repo(db_conn, repo_id)

        detail = await hf_source.get_session(db_conn, "session-0")
        assert detail is not None
        assert detail.summary.session_id == "session-0"
        assert len(detail.messages) == 2

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, hf_source, db_conn):
        detail = await hf_source.get_session(db_conn, "does-not-exist")
        assert detail is None


class TestListProjects:
    """Tests for HuggingFaceSource.list_projects."""

    @pytest.mark.asyncio
    async def test_list_projects(self, hf_source, db_conn, repo_id):
        _write_cached_files(hf_source, repo_id)
        await hf_source.pull_repo(db_conn, repo_id)

        projects = await hf_source.list_projects(db_conn)
        assert "project-0" in projects
        assert "project-1" in projects
        assert "project-2" in projects
        assert projects == sorted(projects)
