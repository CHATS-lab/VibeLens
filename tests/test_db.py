"""Unit tests for vibelens.db database layer."""

from pathlib import Path

import aiosqlite
import pytest

from vibelens.db import SCHEMA_SQL, get_connection, init_db


class TestInitDb:
    """Test database initialization."""

    async def test_creates_database_file(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        await init_db(db_path)
        assert db_path.exists()

    async def test_creates_parent_directories(self, tmp_path: Path):
        db_path = tmp_path / "nested" / "dir" / "test.db"
        await init_db(db_path)
        assert db_path.exists()

    async def test_sessions_table_created(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        await init_db(db_path)

        async with aiosqlite.connect(str(db_path)) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
            )
            row = await cursor.fetchone()
            assert row is not None

    async def test_messages_table_created(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        await init_db(db_path)

        async with aiosqlite.connect(str(db_path)) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
            )
            row = await cursor.fetchone()
            assert row is not None

    async def test_messages_session_index_created(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        await init_db(db_path)

        async with aiosqlite.connect(str(db_path)) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_messages_session'"
            )
            row = await cursor.fetchone()
            assert row is not None

    async def test_idempotent(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        await init_db(db_path)
        await init_db(db_path)

        async with aiosqlite.connect(str(db_path)) as db:
            cursor = await db.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'"
            )
            row = await cursor.fetchone()
            assert row[0] == 2

    async def test_sessions_schema_columns(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        await init_db(db_path)

        expected_columns = {
            "session_id", "project_id", "project_name", "timestamp",
            "duration", "message_count", "tool_call_count", "models",
            "first_message", "source_type", "source_name", "source_host",
        }
        async with aiosqlite.connect(str(db_path)) as db:
            cursor = await db.execute("PRAGMA table_info(sessions)")
            rows = await cursor.fetchall()
            column_names = {row[1] for row in rows}
            assert expected_columns == column_names

    async def test_messages_schema_columns(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        await init_db(db_path)

        expected_columns = {
            "uuid", "session_id", "parent_uuid", "role", "type",
            "content", "thinking", "model", "timestamp",
            "is_sidechain", "usage", "tool_calls",
        }
        async with aiosqlite.connect(str(db_path)) as db:
            cursor = await db.execute("PRAGMA table_info(messages)")
            rows = await cursor.fetchall()
            column_names = {row[1] for row in rows}
            assert expected_columns == column_names


class TestGetConnection:
    """Test get_connection function."""

    async def test_raises_before_init(self, tmp_path: Path):
        import vibelens.db
        original = vibelens.db._db_path
        vibelens.db._db_path = None
        try:
            with pytest.raises(RuntimeError, match="Database not initialized"):
                await get_connection()
        finally:
            vibelens.db._db_path = original

    async def test_returns_connection_after_init(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        await init_db(db_path)
        conn = await get_connection()
        assert conn is not None
        await conn.close()
