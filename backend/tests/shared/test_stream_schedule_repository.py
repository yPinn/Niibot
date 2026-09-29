from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

from shared.repositories.stream_schedule import StreamScheduleRepository

_DAY = date(2026, 9, 21)


def _pool() -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=transaction)

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


async def test_restore_replacement_deletes_the_replacement_under_channel_lock() -> None:
    pool, conn = _pool()
    conn.fetchval.return_value = 9
    conn.execute.side_effect = ["SELECT 1", "DELETE 1"]

    restored = await StreamScheduleRepository(pool).restore_occurrence("chan1", 4, _DAY)

    assert restored is True
    assert "pg_advisory_xact_lock" in conn.execute.await_args_list[0].args[0]
    delete = conn.execute.await_args_list[1]
    assert "DELETE FROM stream_schedules" in delete.args[0]
    assert delete.args[1:] == ("chan1", 9)


async def test_restore_cancelled_occurrence_deletes_only_the_exception() -> None:
    pool, conn = _pool()
    conn.fetchval.return_value = None
    conn.execute.side_effect = ["SELECT 1", "DELETE 1"]

    restored = await StreamScheduleRepository(pool).restore_occurrence("chan1", 4, _DAY)

    assert restored is True
    delete = conn.execute.await_args_list[1]
    assert "DELETE FROM stream_schedule_occurrence_exceptions" in delete.args[0]
    assert delete.args[1:] == ("chan1", 4, _DAY)


async def test_delete_recurring_schedule_also_deletes_its_replacements() -> None:
    pool, conn = _pool()
    conn.fetchval.return_value = [9, 10]
    conn.execute.side_effect = ["SELECT 1", "DELETE 1", "DELETE 2"]

    deleted = await StreamScheduleRepository(pool).delete("chan1", 4)

    assert deleted is True
    replacement_delete = conn.execute.await_args_list[2]
    assert "id = ANY($2::int[])" in replacement_delete.args[0]
    assert replacement_delete.args[1:] == ("chan1", [9, 10])
