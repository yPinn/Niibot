"""Tenant collection catalog and active-set selection tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.checkin_collection_service import CheckinCollectionService


def _pool() -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    transaction = MagicMock()
    transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    transaction.return_value.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = transaction
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _catalog_rows() -> list[dict[str, object]]:
    return [
        {
            "set_key": "aespa",
            "set_name": "aespa",
            "card_count": 2,
            "card_key": "karina-01",
            "card_number": 1,
            "card_name": "Karina",
            "portrait_url": "/images/collections/aespa/karina-01-r1.webp",
            "rarity_key": "common",
            "rarity_name": "普通",
        },
        {
            "set_key": "aespa",
            "set_name": "aespa",
            "card_count": 2,
            "card_key": "winter-01",
            "card_number": 2,
            "card_name": "Winter",
            "portrait_url": "/images/collections/aespa/winter-01-r1.webp",
            "rarity_key": "common",
            "rarity_name": "普通",
        },
        {
            "set_key": "uc",
            "set_name": "Eunha",
            "card_count": 1,
            "card_key": "eunha-01",
            "card_number": 1,
            "card_name": "Eunha",
            "portrait_url": "/images/collections/uc/eunha-01-r1.webp",
            "rarity_key": "common",
            "rarity_name": "普通",
        },
    ]


@pytest.mark.asyncio
async def test_get_snapshot_groups_the_fallback_catalog_and_scopes_selection() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = _catalog_rows()
    conn.fetchval.return_value = "uc"

    snapshot = await CheckinCollectionService(pool).get_snapshot("channel-1")

    assert snapshot.selected_set_key == "uc"
    assert snapshot.total_cards == 3
    assert [item.key for item in snapshot.sets] == ["aespa", "uc"]
    assert [card.key for card in snapshot.sets[0].cards] == ["karina-01", "winter-01"]
    assert conn.fetchval.await_args.args[1:] == ("channel-1",)
    assert "collection_system_settings" in conn.fetch.await_args.args[0]
    assert "first-path" not in conn.fetch.await_args.args[0]


@pytest.mark.asyncio
async def test_select_all_stores_null_so_the_official_fallback_remains_authoritative() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = _catalog_rows()
    conn.fetchval.return_value = None

    snapshot = await CheckinCollectionService(pool).select_set("channel-1", None)

    assert snapshot.selected_set_key is None
    sql = "\n".join(call.args[0] for call in conn.execute.await_args_list)
    assert "channel_collection_settings" in sql
    assert "active_pool_revision_id = EXCLUDED.active_pool_revision_id" in sql
    assert conn.execute.await_args.args[1:] == ("channel-1", None)


@pytest.mark.asyncio
async def test_select_set_resolves_only_a_published_official_set_pool() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = _catalog_rows()
    conn.fetchval.side_effect = [42, "aespa"]

    snapshot = await CheckinCollectionService(pool).select_set("channel-1", "aespa")

    assert snapshot.selected_set_key == "aespa"
    lookup = conn.fetchval.await_args_list[0]
    assert "published_at IS NOT NULL" in lookup.args[0]
    assert "official-set-" in lookup.args[0]
    assert "ORDER BY pool.revision_number DESC" in lookup.args[0]
    assert lookup.args[1:] == ("aespa",)
    assert conn.execute.await_args.args[1:] == ("channel-1", 42)


@pytest.mark.asyncio
async def test_select_set_rejects_unknown_key_without_writing() -> None:
    pool, conn = _pool()
    conn.fetchval.return_value = None

    with pytest.raises(ValueError, match="unknown collection set"):
        await CheckinCollectionService(pool).select_set("channel-1", "unknown")

    conn.execute.assert_not_awaited()
