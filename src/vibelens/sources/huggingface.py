"""HuggingFace dataclaw data source.

Downloads dataclaw-exported datasets from HuggingFace and stores
them in the local SQLite database.
"""

from pathlib import Path
from urllib.parse import quote, unquote

import aiosqlite
import httpx

from vibelens.db import (
    delete_sessions_by_source,
    insert_messages,
    insert_session,
    query_session_detail,
    query_sessions,
)
from vibelens.ingest.dataclaw import DataclawParser
from vibelens.models.requests import PullResult, RemoteSessionsQuery
from vibelens.models.session import SessionDetail, SessionSummary
from vibelens.utils import get_logger, load_json_file
from vibelens.utils.paths import ensure_dir

logger = get_logger(__name__)

HF_RAW_URL = "https://huggingface.co/datasets/{repo_id}/resolve/main/{filename}"
DATASETS_DIR_NAME = "datasets"
CONVERSATIONS_FILE = "conversations.jsonl"
METADATA_FILE = "metadata.json"


class HuggingFaceSource:
    """Pull sessions from HuggingFace dataclaw datasets."""

    def __init__(self, data_dir: Path, hf_token: str = ""):
        """Initialize with local data directory and optional token.

        Args:
            data_dir: Base directory for cached datasets (~/.vibelens).
            hf_token: Optional HuggingFace API token for private repos.
        """
        self._data_dir = data_dir / DATASETS_DIR_NAME
        self._hf_token = hf_token
        self._parser = DataclawParser()

    @property
    def source_type(self) -> str:
        return "huggingface"

    @property
    def display_name(self) -> str:
        return "HuggingFace"

    async def pull_repo(
        self, conn: aiosqlite.Connection, repo_id: str, force_refresh: bool = False
    ) -> PullResult:
        """Download a dataclaw dataset and import into SQLite.

        Args:
            conn: Active database connection.
            repo_id: HuggingFace repo (e.g. "REXX-NEW/my-personal-claude-code-data").
            force_refresh: Re-download and re-import even if cached.

        Returns:
            PullResult with import counts.
        """
        repo_dir = self._repo_dir(repo_id)
        conversations_path = repo_dir / CONVERSATIONS_FILE
        metadata_path = repo_dir / METADATA_FILE

        is_cached = conversations_path.exists()

        if force_refresh and is_cached:
            await delete_sessions_by_source(conn, repo_id)
            await conn.commit()

        if force_refresh or not is_cached:
            ensure_dir(repo_dir)
            await self._download_file(repo_id, CONVERSATIONS_FILE, conversations_path)
            await self._download_file(repo_id, METADATA_FILE, metadata_path)

        parsed = self._parser.parse_file(conversations_path)

        sessions_imported = 0
        messages_imported = 0
        skipped = 0

        for summary, messages in parsed:
            summary.source_name = repo_id

            was_inserted = await insert_session(conn, summary)
            if was_inserted:
                msg_count = await insert_messages(conn, messages)
                sessions_imported += 1
                messages_imported += msg_count
            else:
                skipped += 1

        await conn.commit()

        return PullResult(
            repo_id=repo_id,
            sessions_imported=sessions_imported,
            messages_imported=messages_imported,
            skipped=skipped,
        )

    def list_repos(self) -> list[dict]:
        """List locally cached HuggingFace repos.

        Returns:
            List of dicts with repo_id and file info.
        """
        if not self._data_dir.exists():
            return []

        repos = []
        for repo_dir in sorted(self._data_dir.iterdir()):
            if not repo_dir.is_dir():
                continue

            conversations_path = repo_dir / CONVERSATIONS_FILE
            if not conversations_path.exists():
                continue

            repo_id = self._decode_repo_id(repo_dir.name)
            metadata_path = repo_dir / METADATA_FILE
            metadata = load_json_file(metadata_path) or {} if metadata_path.exists() else {}

            repos.append(
                {
                    "repo_id": repo_id,
                    "cached": True,
                    "conversations_file": str(conversations_path),
                    "metadata": metadata,
                }
            )

        return repos

    async def list_sessions(
        self,
        conn: aiosqlite.Connection,
        query: RemoteSessionsQuery,
    ) -> list[SessionSummary]:
        """Query stored HuggingFace sessions from SQLite.

        Args:
            conn: Active database connection.
            query: Filtering and pagination parameters.

        Returns:
            List of SessionSummary objects.
        """
        return await query_sessions(
            conn,
            source_type="huggingface",
            project=query.project_id,
            limit=query.limit,
            offset=query.offset,
        )

    async def get_session(
        self,
        conn: aiosqlite.Connection,
        session_id: str,
    ) -> SessionDetail | None:
        """Retrieve full session detail from SQLite.

        Args:
            conn: Active database connection.
            session_id: Session UUID.

        Returns:
            SessionDetail or None if not found.
        """
        summary, messages = await query_session_detail(conn, session_id)
        if summary is None:
            return None
        return SessionDetail(summary=summary, messages=messages)

    async def list_projects(self, conn: aiosqlite.Connection) -> list[str]:
        """List distinct project names from HuggingFace sessions.

        Args:
            conn: Active database connection.

        Returns:
            Sorted list of project names.
        """
        cursor = await conn.execute(
            """
            SELECT DISTINCT project_name FROM sessions
            WHERE source_type = 'huggingface' AND project_name != ''
            ORDER BY project_name
            """
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def _download_file(self, repo_id: str, filename: str, dest: Path) -> None:
        """Download a file from HuggingFace using httpx streaming.

        Args:
            repo_id: HuggingFace repo identifier.
            filename: File to download from the repo.
            dest: Local destination path.
        """
        url = HF_RAW_URL.format(repo_id=repo_id, filename=filename)
        headers = {}
        if self._hf_token:
            headers["Authorization"] = f"Bearer {self._hf_token}"

        logger.info("Downloading %s from %s", filename, repo_id)

        async with (
            httpx.AsyncClient(follow_redirects=True, timeout=300) as client,
            client.stream("GET", url, headers=headers) as response,
        ):
            response.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    f.write(chunk)

        logger.info("Downloaded %s (%d bytes)", filename, dest.stat().st_size)

    def _repo_dir(self, repo_id: str) -> Path:
        """Return the local cache directory for a repo."""
        encoded = quote(repo_id, safe="")
        return self._data_dir / encoded

    @staticmethod
    def _decode_repo_id(encoded: str) -> str:
        """Decode a directory name back to a repo_id."""
        return unquote(encoded)
