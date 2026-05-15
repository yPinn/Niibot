"""Unit tests for shared.repositories.crosshair — CrosshairRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from shared.repositories.crosshair import CrosshairRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
_XH_ID = str(uuid4())
CHANNEL_ID = "ch-123"

_XH_ROW = {
    "id": _XH_ID,
    "channel_id": CHANNEL_ID,
    "game": "valorant",
    "name": "Default",
    "code": "0;P;c;1;h;0",
    "description": None,
    "display_order": 0,
    "copy_count": 5,
    "created_at": _NOW,
    "updated_at": _NOW,
}

_XH_PUBLIC_ROW = {**_XH_ROW, "channel_name": "streamer"}


def _make_pool(*, fetch=None, fetchrow=None, execute="DELETE 0") -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    conn.fetch.return_value = (
        [MagicMock(**{"keys.return_value": list(_XH_ROW), **{k: v for k, v in _XH_ROW.items()}})]
        if fetch is None
        else fetch
    )
    conn.fetchrow.return_value = fetchrow
    conn.execute.return_value = execute

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _dict_row(d: dict) -> MagicMock:
    """Return a MagicMock that behaves like an asyncpg Record for dict()."""
    row = MagicMock()
    row.keys.return_value = list(d.keys())
    row.__iter__ = MagicMock(return_value=iter(d.values()))
    row.items = MagicMock(return_value=list(d.items()))
    # Support dict(row) via mapping protocol
    row.__class__ = type("Row", (MagicMock,), {"keys": lambda s: list(d.keys())})
    return row


# ---------------------------------------------------------------------------
# list_by_channel
# ---------------------------------------------------------------------------


class TestListByChannel:
    @pytest.mark.asyncio
    async def test_returns_rows_without_game_filter(self):
        pool, conn = _make_pool()
        conn.fetch.return_value = [_XH_ROW]
        repo = CrosshairRepository(pool)
        rows = await repo.list_by_channel(CHANNEL_ID)
        assert len(rows) == 1
        assert rows[0]["name"] == "Default"
        # Should query without game filter (1 param)
        call_args = conn.fetch.await_args
        assert "$2" not in call_args.args[0]

    @pytest.mark.asyncio
    async def test_returns_rows_with_game_filter(self):
        pool, conn = _make_pool()
        conn.fetch.return_value = [_XH_ROW]
        repo = CrosshairRepository(pool)
        rows = await repo.list_by_channel(CHANNEL_ID, game="valorant")
        assert rows[0]["game"] == "valorant"
        # Should include $2 for game param
        call_args = conn.fetch.await_args
        assert "$2" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_invalid_game_ignored(self):
        pool, conn = _make_pool()
        conn.fetch.return_value = []
        repo = CrosshairRepository(pool)
        await repo.list_by_channel(CHANNEL_ID, game="cs2")
        # cs2 not in VALID_GAMES → treated as no filter
        call_args = conn.fetch.await_args
        assert "$2" not in call_args.args[0]

    @pytest.mark.asyncio
    async def test_empty_list(self):
        pool, conn = _make_pool()
        conn.fetch.return_value = []
        repo = CrosshairRepository(pool)
        rows = await repo.list_by_channel(CHANNEL_ID)
        assert rows == []


# ---------------------------------------------------------------------------
# list_all_public
# ---------------------------------------------------------------------------


class TestListAllPublic:
    @pytest.mark.asyncio
    async def test_returns_public_rows(self):
        pool, conn = _make_pool()
        conn.fetch.return_value = [_XH_PUBLIC_ROW]
        repo = CrosshairRepository(pool)
        rows = await repo.list_all_public()
        assert rows[0]["channel_name"] == "streamer"

    @pytest.mark.asyncio
    async def test_applies_game_filter(self):
        pool, conn = _make_pool()
        conn.fetch.return_value = [_XH_PUBLIC_ROW]
        repo = CrosshairRepository(pool)
        await repo.list_all_public(game="valorant")
        call_args = conn.fetch.await_args
        assert "$2" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_passes_limit(self):
        pool, conn = _make_pool()
        conn.fetch.return_value = []
        repo = CrosshairRepository(pool)
        await repo.list_all_public(limit=10)
        call_args = conn.fetch.await_args
        assert 10 in call_args.args


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestCreate:
    @pytest.mark.asyncio
    async def test_returns_created_row(self):
        pool, conn = _make_pool()
        conn.fetchrow.return_value = _XH_ROW
        repo = CrosshairRepository(pool)
        row = await repo.create(CHANNEL_ID, game="valorant", name="Default", code="0;P;c;1")
        assert row["name"] == "Default"
        assert row["game"] == "valorant"

    @pytest.mark.asyncio
    async def test_passes_all_fields(self):
        pool, conn = _make_pool()
        conn.fetchrow.return_value = _XH_ROW
        repo = CrosshairRepository(pool)
        await repo.create(
            CHANNEL_ID,
            game="valorant",
            name="x",
            code="y",
            description="desc",
            display_order=2,
        )
        args = conn.fetchrow.await_args.args
        assert "valorant" in args
        assert "desc" in args
        assert 2 in args


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


class TestUpdate:
    @pytest.mark.asyncio
    async def test_updates_and_returns_row(self):
        updated = {**_XH_ROW, "name": "Updated"}
        pool, conn = _make_pool()
        conn.fetchrow.return_value = updated
        repo = CrosshairRepository(pool)
        row = await repo.update(_XH_ID, CHANNEL_ID, fields={"name": "Updated"})
        assert row["name"] == "Updated"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        repo = CrosshairRepository(pool)
        row = await repo.update(_XH_ID, CHANNEL_ID, fields={"name": "X"})
        assert row is None

    @pytest.mark.asyncio
    async def test_empty_fields_fetches_existing(self):
        pool, conn = _make_pool()
        conn.fetchrow.return_value = _XH_ROW
        repo = CrosshairRepository(pool)
        await repo.update(_XH_ID, CHANNEL_ID, fields={})
        # No SET clause — should SELECT instead
        call_args = conn.fetchrow.await_args.args[0]
        assert "SELECT" in call_args

    @pytest.mark.asyncio
    async def test_unknown_fields_are_filtered(self):
        pool, conn = _make_pool()
        conn.fetchrow.return_value = _XH_ROW
        repo = CrosshairRepository(pool)
        # "channel_id" is not in _ALLOWED_COLUMNS — should be stripped
        await repo.update(_XH_ID, CHANNEL_ID, fields={"channel_id": "evil", "name": "ok"})
        call_args = conn.fetchrow.await_args.args[0]
        assert "channel_id" not in call_args.split("SET")[1].split("WHERE")[0]


# ---------------------------------------------------------------------------
# increment_copy
# ---------------------------------------------------------------------------


class TestIncrementCopy:
    @pytest.mark.asyncio
    async def test_executes_update(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = CrosshairRepository(pool)
        await repo.increment_copy(_XH_ID)
        conn.execute.assert_awaited_once()
        assert "copy_count" in conn.execute.await_args.args[0]


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDelete:
    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self):
        pool, _ = _make_pool(execute="DELETE 1")
        repo = CrosshairRepository(pool)
        result = await repo.delete(_XH_ID, CHANNEL_ID)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self):
        pool, _ = _make_pool(execute="DELETE 0")
        repo = CrosshairRepository(pool)
        result = await repo.delete(_XH_ID, CHANNEL_ID)
        assert result is False
