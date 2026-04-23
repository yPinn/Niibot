"""Unit tests for shared.migrations.runner — MigrationRunner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from shared.migrations.runner import MigrationRunner


def _make_pool(*, fetch=None):
    conn = AsyncMock()
    conn.execute.return_value = None
    conn.fetch.return_value = fetch or []

    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=None)
    mock_tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=mock_tx)

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


class TestEnsureTable:
    async def test_executes_create_table(self):
        pool, conn = _make_pool()
        await MigrationRunner(pool).ensure_table()
        conn.execute.assert_called_once()
        sql = conn.execute.call_args[0][0]
        assert "CREATE TABLE IF NOT EXISTS" in sql
        assert "schema_migrations" in sql


class TestGetApplied:
    async def test_empty_table_returns_empty_set(self):
        pool, _ = _make_pool(fetch=[])
        result = await MigrationRunner(pool).get_applied()
        assert result == set()

    async def test_returns_applied_versions(self):
        rows = [{"version": "000_initial"}, {"version": "001_add_index"}]
        pool, _ = _make_pool(fetch=rows)
        result = await MigrationRunner(pool).get_applied()
        assert result == {"000_initial", "001_add_index"}


class TestRunPending:
    async def test_empty_dir_returns_empty_list(self, tmp_path: Path):
        pool, _ = _make_pool(fetch=[])
        result = await MigrationRunner(pool).run_pending(migrations_dir=tmp_path)
        assert result == []

    async def test_applies_pending_migration(self, tmp_path: Path):
        (tmp_path / "001_create_users.sql").write_text("CREATE TABLE users (id INT);")
        pool, _ = _make_pool(fetch=[])
        result = await MigrationRunner(pool).run_pending(migrations_dir=tmp_path)
        assert result == ["001_create_users"]

    async def test_skips_already_applied(self, tmp_path: Path):
        (tmp_path / "001_create_users.sql").write_text("CREATE TABLE users (id INT);")
        rows = [{"version": "001_create_users"}]
        pool, _ = _make_pool(fetch=rows)
        result = await MigrationRunner(pool).run_pending(migrations_dir=tmp_path)
        assert result == []

    async def test_applies_only_unapplied_in_order(self, tmp_path: Path):
        (tmp_path / "001_first.sql").write_text("SELECT 1;")
        (tmp_path / "002_second.sql").write_text("SELECT 2;")
        (tmp_path / "003_third.sql").write_text("SELECT 3;")
        rows = [{"version": "001_first"}]
        pool, _ = _make_pool(fetch=rows)
        result = await MigrationRunner(pool).run_pending(migrations_dir=tmp_path)
        assert result == ["002_second", "003_third"]

    async def test_all_applied_returns_empty_list(self, tmp_path: Path):
        (tmp_path / "001_init.sql").write_text("SELECT 1;")
        rows = [{"version": "001_init"}]
        pool, _ = _make_pool(fetch=rows)
        result = await MigrationRunner(pool).run_pending(migrations_dir=tmp_path)
        assert result == []


class TestApplyOne:
    async def test_executes_migration_sql(self):
        pool, conn = _make_pool()
        await MigrationRunner(pool)._apply_one(
            "001_test", "001_test.sql", "CREATE TABLE x (id INT);"
        )
        first_sql = conn.execute.call_args_list[0][0][0]
        assert "CREATE TABLE x" in first_sql

    async def test_records_version_in_tracking_table(self):
        pool, conn = _make_pool()
        await MigrationRunner(pool)._apply_one(
            "042_add_col", "042_add_col.sql", "ALTER TABLE x ADD col TEXT;"
        )
        insert_args = conn.execute.call_args_list[1][0]
        assert "INSERT INTO schema_migrations" in insert_args[0]
        assert insert_args[1] == "042_add_col"
        assert insert_args[2] == "042_add_col.sql"

    async def test_uses_transaction(self):
        pool, conn = _make_pool()
        await MigrationRunner(pool)._apply_one("001_t", "001_t.sql", "SELECT 1;")
        conn.transaction.assert_called_once()
