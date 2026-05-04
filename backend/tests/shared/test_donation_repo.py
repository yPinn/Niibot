"""Unit tests for shared.repositories.donation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.repositories.donation import DonationRepository


def _make_pool(*, execute: str = "UPDATE 1") -> tuple:
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=execute)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)

    return pool, conn


# ---------------------------------------------------------------------------
# mark_failed — only transitions pending → failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMarkFailed:
    async def test_sql_includes_pending_guard(self):
        """SQL must include AND status = 'pending' to prevent downgrading paid orders."""
        pool, conn = _make_pool()
        repo = DonationRepository(pool)

        await repo.mark_failed("trade-001")

        sql: str = conn.execute.call_args[0][0]
        assert "pending" in sql

    async def test_passes_trade_no_as_parameter(self):
        pool, conn = _make_pool()
        repo = DonationRepository(pool)

        await repo.mark_failed("trade-abc")

        assert "trade-abc" in conn.execute.call_args[0]

    async def test_sets_status_to_failed(self):
        pool, conn = _make_pool()
        repo = DonationRepository(pool)

        await repo.mark_failed("trade-001")

        sql: str = conn.execute.call_args[0][0]
        assert "failed" in sql

    async def test_no_op_when_already_paid(self):
        """UPDATE with AND status='pending' silently skips paid orders (UPDATE 0 is not an error)."""
        pool, conn = _make_pool(execute="UPDATE 0")
        repo = DonationRepository(pool)

        await repo.mark_failed("trade-paid")

        conn.execute.assert_called_once()
