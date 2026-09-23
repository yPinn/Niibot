"""Tests for collection draws performed on a caller-owned transaction."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from shared.collection_draw import ALGORITHM_VERSION
from shared.repositories.collection import CollectionRepository

_NOW = datetime(2026, 9, 8, 8, 0, tzinfo=UTC)
_ENTROPY = bytes.fromhex("00000000000000000000000000000000")


def _pool_rows(pool_revision_id: int = 51) -> list[dict[str, object]]:
    base: dict[str, object] = {
        "pool_revision_id": pool_revision_id,
        "algorithm_version": ALGORITHM_VERSION,
        "set_id": 11,
        "set_key": "aespa",
        "set_display_name": "aespa",
        "total_cards": 9,
        "portrait_url": None,
        "square_url": None,
        "backdrop_url": None,
        "description": "",
    }
    return [
        {
            **base,
            "rarity_revision_id": 21,
            "rarity_key": "common",
            "rarity_display_name": "普通",
            "sort_rank": 10,
            "effect_intensity": 20,
            "weight": 70,
            "card_revision_id": 41,
            "card_id": 31,
            "card_key": "karina-01",
            "card_number": 1,
            "card_display_name": "星羅羅盤",
            "entry_order": 1,
        },
        {
            **base,
            "rarity_revision_id": 21,
            "rarity_key": "common",
            "rarity_display_name": "普通",
            "sort_rank": 10,
            "effect_intensity": 20,
            "weight": 70,
            "card_revision_id": 42,
            "card_id": 32,
            "card_key": "echo-stone",
            "card_number": 2,
            "card_display_name": "回聲礦石",
            "entry_order": 2,
        },
        {
            **base,
            "rarity_revision_id": 23,
            "rarity_key": "legendary",
            "rarity_display_name": "傳說",
            "sort_rank": 30,
            "effect_intensity": 100,
            "weight": 5,
            "card_revision_id": 43,
            "card_id": 33,
            "card_key": "winter-01",
            "card_number": 9,
            "card_display_name": "初途王冠",
            "entry_order": 9,
        },
    ]


def _draw_row(*, draw_id: int = 61, pool_revision_id: int = 51) -> dict[str, object]:
    return {
        "draw_id": draw_id,
        "pool_revision_id": pool_revision_id,
        "algorithm_version": ALGORITHM_VERSION,
        "entropy": _ENTROPY,
        "rarity_roll": 0,
        "rarity_weight_total": 75,
        "card_roll": 0,
        "card_bucket_size": 2,
        "card_revision_id": 41,
        "card_id": 31,
        "card_key": "karina-01",
        "card_number": 1,
        "card_display_name": "星羅羅盤",
        "description": "",
        "portrait_url": None,
        "square_url": None,
        "backdrop_url": None,
        "set_id": 11,
        "set_key": "aespa",
        "set_display_name": "aespa",
        "total_cards": 9,
        "rarity_revision_id": 21,
        "rarity_key": "common",
        "rarity_display_name": "普通",
        "sort_rank": 10,
        "effect_intensity": 20,
        "copy_count": 1,
        "owned_copies": 1,
        "unique_cards": 1,
    }


def _owned_rows() -> list[dict[str, object]]:
    return [
        {
            "card_revision_id": 41,
            "card_id": 31,
            "card_key": "karina-01",
            "card_number": 1,
            "card_display_name": "星羅羅盤",
            "description": "",
            "portrait_url": None,
            "square_url": None,
            "backdrop_url": None,
            "set_id": 11,
            "set_key": "aespa",
            "set_display_name": "aespa",
            "total_cards": 9,
            "rarity_revision_id": 21,
            "rarity_key": "common",
            "rarity_display_name": "普通",
            "sort_rank": 10,
            "effect_intensity": 20,
            "copy_count": 1,
        }
    ]


def _owned_history_rows() -> list[dict[str, object]]:
    rows = _owned_rows()
    rows[0]["copy_count"] = 2
    rows.append(
        {
            **rows[0],
            "card_revision_id": 42,
            "card_id": 32,
            "card_key": "echo-stone",
            "card_number": 2,
            "card_display_name": "回聲礦石",
            "portrait_url": "/images/collections/aespa/echo-stone-portrait.webp",
            "copy_count": 1,
        }
    )
    rows.append(
        {
            **rows[0],
            "card_revision_id": 43,
            "card_id": 33,
            "card_key": "winter-01",
            "card_number": 9,
            "card_display_name": "初途王冠",
            "rarity_revision_id": 23,
            "rarity_key": "legendary",
            "rarity_display_name": "傳說",
            "sort_rank": 30,
            "effect_intensity": 100,
            "portrait_url": "/images/collections/aespa/winter-01-portrait.webp",
            "copy_count": 1,
        }
    )
    return rows


@pytest.mark.asyncio
async def test_draw_uses_caller_connection_and_persists_entropy_and_audit_values() -> None:
    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        {"active_pool_revision_id": 51, "fallback_pool_revision_id": 52},
        {"id": 61},
        _draw_row(),
    ]
    conn.fetch.side_effect = [_pool_rows(), _owned_rows()]
    requested_sizes: list[int] = []

    def entropy_source(size: int) -> bytes:
        requested_sizes.append(size)
        return _ENTROPY

    repository = CollectionRepository(entropy_source=entropy_source)

    draw = await repository.draw_for_checkin(
        conn,
        channel_id="ch1",
        user_id="u1",
        checkin_id=7,
        drawn_at=_NOW,
    )

    assert requested_sizes == [16]
    assert draw.id == 61
    assert draw.selection.card.key == "karina-01"
    assert draw.selection.card.number == "001"
    assert draw.is_new is True
    assert draw.to_event_snapshot()["progress"] == {
        "owned_copies": 1,
        "unique_cards": 1,
        "total_cards": 9,
    }
    assert draw.to_event_snapshot()["owned_cards"] == [
        {
            "card": {
                "id": 31,
                "revision_id": 41,
                "key": "karina-01",
                "number": "001",
                "name": "星羅羅盤",
                "artwork": {
                    "portrait_url": None,
                    "square_url": None,
                    "backdrop_url": None,
                },
            },
            "rarity": {
                "key": "common",
                "label": "普通",
                "rank": 10,
                "effect_intensity": 20,
            },
            "copy_count": 1,
        }
    ]

    insert_call = conn.fetchrow.await_args_list[1]
    assert "INSERT INTO viewer_card_draws" in insert_call.args[0]
    assert "ON CONFLICT (checkin_id) DO NOTHING" in insert_call.args[0]
    assert insert_call.args[1:] == (
        "ch1",
        "u1",
        7,
        51,
        41,
        ALGORITHM_VERSION,
        _ENTROPY,
        0,
        75,
        0,
        2,
        _NOW,
    )


@pytest.mark.asyncio
async def test_unavailable_tenant_pool_falls_back_to_the_official_pool(caplog) -> None:
    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        {"active_pool_revision_id": 999, "fallback_pool_revision_id": 51},
        {"id": 61},
        _draw_row(),
    ]
    conn.fetch.side_effect = [[], _pool_rows(), _owned_rows()]
    repository = CollectionRepository(entropy_source=lambda _: _ENTROPY)

    draw = await repository.draw_for_checkin(
        conn,
        channel_id="ch1",
        user_id="u1",
        checkin_id=7,
        drawn_at=_NOW,
    )

    assert draw.selection.pool_revision_id == 51
    assert [call.args[1] for call in conn.fetch.await_args_list[:2]] == [999, 51]
    warning = next(
        record for record in caplog.records if record.message == "collection_active_pool_fallback"
    )
    assert warning.channel_id == "ch1"
    assert warning.pool_revision_id == 999
    assert warning.reason == "unavailable_or_unpublished"


@pytest.mark.asyncio
async def test_malformed_tenant_pool_falls_back_instead_of_failing_checkin() -> None:
    conn = AsyncMock()
    malformed = _pool_rows(999)
    malformed[0]["algorithm_version"] = "future-algorithm-v2"
    conn.fetchrow.side_effect = [
        {"active_pool_revision_id": 999, "fallback_pool_revision_id": 51},
        {"id": 61},
        _draw_row(),
    ]
    conn.fetch.side_effect = [malformed, _pool_rows(), _owned_rows()]
    repository = CollectionRepository(entropy_source=lambda _: _ENTROPY)

    draw = await repository.draw_for_checkin(
        conn,
        channel_id="ch1",
        user_id="u1",
        checkin_id=7,
        drawn_at=_NOW,
    )

    assert draw.selection.pool_revision_id == 51


@pytest.mark.asyncio
async def test_existing_checkin_draw_is_loaded_when_insert_conflicts() -> None:
    conn = AsyncMock()
    existing = _draw_row(draw_id=88)
    existing["copy_count"] = 2
    existing["owned_copies"] = 2
    conn.fetchrow.side_effect = [
        {"active_pool_revision_id": 51, "fallback_pool_revision_id": 51},
        None,
        existing,
    ]
    owned_rows = _owned_rows()
    owned_rows[0]["copy_count"] = 2
    conn.fetch.side_effect = [_pool_rows(), owned_rows]
    repository = CollectionRepository(entropy_source=lambda _: _ENTROPY)

    draw = await repository.draw_for_checkin(
        conn,
        channel_id="ch1",
        user_id="u1",
        checkin_id=7,
        drawn_at=_NOW,
    )

    assert draw.id == 88
    assert draw.is_new is False
    assert draw.copy_count == 2


@pytest.mark.asyncio
async def test_draw_snapshot_contains_complete_current_set_inventory_in_catalog_order() -> None:
    conn = AsyncMock()
    row = _draw_row()
    row["copy_count"] = 2
    row["owned_copies"] = 4
    row["unique_cards"] = 3
    conn.fetchrow.side_effect = [
        {"active_pool_revision_id": 51, "fallback_pool_revision_id": 51},
        {"id": 61},
        row,
    ]
    conn.fetch.side_effect = [_pool_rows(), _owned_history_rows()]
    repository = CollectionRepository(entropy_source=lambda _: _ENTROPY)

    draw = await repository.draw_for_checkin(
        conn,
        channel_id="ch1",
        user_id="u1",
        checkin_id=7,
        drawn_at=_NOW,
    )

    assert [item.card.number for item in draw.owned_cards] == ["001", "002", "009"]
    assert [item.copy_count for item in draw.owned_cards] == [2, 1, 1]
    inventory_call = conn.fetch.await_args_list[-1]
    assert inventory_call.args[1:] == ("ch1", "u1", 11)
    assert "DISTINCT ON (owned_card.id)" in inventory_call.args[0]
    assert "ORDER BY inventory.card_number" in inventory_call.args[0]


@pytest.mark.asyncio
async def test_selected_inventory_item_keeps_the_current_draw_revision_during_backfill() -> None:
    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        {"active_pool_revision_id": 51, "fallback_pool_revision_id": 51},
        {"id": 61},
        _draw_row(),
    ]
    inventory = _owned_rows()
    inventory[0]["card_revision_id"] = 99
    inventory[0]["card_display_name"] = "較新的同卡版本"
    inventory[0]["portrait_url"] = "/images/collections/aespa/karina-01-r2.webp"
    conn.fetch.side_effect = [_pool_rows(), inventory]
    repository = CollectionRepository(entropy_source=lambda _: _ENTROPY)

    draw = await repository.draw_for_checkin(
        conn,
        channel_id="ch1",
        user_id="u1",
        checkin_id=7,
        drawn_at=_NOW,
    )

    selected_item = draw.owned_cards[0]
    assert selected_item.card == draw.selection.card
    assert selected_item.card.revision_id == 41
    assert selected_item.card.name == "星羅羅盤"


@pytest.mark.asyncio
async def test_missing_official_fallback_fails_closed_before_writing_a_draw() -> None:
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    repository = CollectionRepository(entropy_source=lambda _: _ENTROPY)

    with pytest.raises(RuntimeError, match="official fallback"):
        await repository.draw_for_checkin(
            conn,
            channel_id="ch1",
            user_id="u1",
            checkin_id=7,
            drawn_at=_NOW,
        )

    conn.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_unusable_official_fallback_fails_before_writing_a_draw() -> None:
    conn = AsyncMock()
    conn.fetchrow.return_value = {
        "active_pool_revision_id": None,
        "fallback_pool_revision_id": 51,
    }
    conn.fetch.return_value = []
    repository = CollectionRepository(entropy_source=lambda _: _ENTROPY)

    with pytest.raises(RuntimeError, match="official fallback pool is unavailable"):
        await repository.draw_for_checkin(
            conn,
            channel_id="ch1",
            user_id="u1",
            checkin_id=7,
            drawn_at=_NOW,
        )

    assert all(
        "INSERT INTO viewer_card_draws" not in call.args[0]
        for call in conn.fetchrow.await_args_list
    )


@pytest.mark.asyncio
async def test_invalid_entropy_source_fails_before_reading_the_pool() -> None:
    conn = AsyncMock()
    conn.fetchrow.return_value = {
        "active_pool_revision_id": None,
        "fallback_pool_revision_id": 51,
    }
    repository = CollectionRepository(entropy_source=lambda _: b"short")

    with pytest.raises(RuntimeError, match="exactly 16 bytes"):
        await repository.draw_for_checkin(
            conn,
            channel_id="ch1",
            user_id="u1",
            checkin_id=7,
            drawn_at=_NOW,
        )

    conn.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_draw_after_insert_is_reported_as_transaction_failure() -> None:
    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        {"active_pool_revision_id": 51, "fallback_pool_revision_id": 51},
        {"id": 61},
        None,
    ]
    conn.fetch.return_value = _pool_rows()
    repository = CollectionRepository(entropy_source=lambda _: _ENTROPY)

    with pytest.raises(RuntimeError, match="persist or load"):
        await repository.draw_for_checkin(
            conn,
            channel_id="ch1",
            user_id="u1",
            checkin_id=7,
            drawn_at=_NOW,
        )
