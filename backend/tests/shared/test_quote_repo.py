"""Unit tests for shared.repositories.quote — QuoteRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.repositories.quote import QuoteRepository

pytestmark = pytest.mark.asyncio

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

_ROW = {
    "id": 1,
    "channel_id": "ch-1",
    "quote_number": 3,
    "quote_text": "這波不虧",
    "created_by": "streamer",
    "created_at": _NOW,
}


def _make_pool(*, fetchrow=None, execute="DELETE 1") -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    conn.fetchrow.return_value = fetchrow
    conn.execute.return_value = execute

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


class TestAdd:
    async def test_inserts_and_returns_quote(self):
        pool, conn = _make_pool(fetchrow=_ROW)
        repo = QuoteRepository(pool)

        result = await repo.add("ch-1", "這波不虧", "streamer")

        assert result.quote_number == 3
        assert result.quote_text == "這波不虧"
        sql, channel_id, text, creator = conn.fetchrow.await_args[0]
        assert "INSERT INTO quotes" in sql
        assert "COALESCE(MAX(quote_number), 0) + 1" in sql
        assert (channel_id, text, creator) == ("ch-1", "這波不虧", "streamer")


class TestGetRandom:
    async def test_returns_none_when_empty(self):
        pool, _conn = _make_pool(fetchrow=None)
        repo = QuoteRepository(pool)
        assert await repo.get_random("ch-1") is None

    async def test_returns_quote_when_found(self):
        pool, conn = _make_pool(fetchrow=_ROW)
        repo = QuoteRepository(pool)

        result = await repo.get_random("ch-1")

        assert result is not None
        assert result.quote_number == 3
        sql = conn.fetchrow.await_args[0][0]
        assert "ORDER BY random()" in sql


class TestGetByNumber:
    async def test_returns_none_when_not_found(self):
        pool, _conn = _make_pool(fetchrow=None)
        repo = QuoteRepository(pool)
        assert await repo.get_by_number("ch-1", 99) is None

    async def test_returns_matching_quote(self):
        pool, conn = _make_pool(fetchrow=_ROW)
        repo = QuoteRepository(pool)

        result = await repo.get_by_number("ch-1", 3)

        assert result is not None and result.id == 1
        _sql, channel_id, number = conn.fetchrow.await_args[0]
        assert (channel_id, number) == ("ch-1", 3)


class TestDelete:
    async def test_true_when_a_row_was_deleted(self):
        pool, _conn = _make_pool(execute="DELETE 1")
        repo = QuoteRepository(pool)
        assert await repo.delete("ch-1", 3) is True

    async def test_false_when_no_row_matched(self):
        pool, _conn = _make_pool(execute="DELETE 0")
        repo = QuoteRepository(pool)
        assert await repo.delete("ch-1", 999) is False
