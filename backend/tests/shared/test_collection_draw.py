"""Tests for the deterministic collection-card selector and event snapshot."""

from __future__ import annotations

import pytest

from shared.collection_draw import ALGORITHM_VERSION, select_card
from shared.models.collection import (
    CollectionCardRevision,
    CollectionDraw,
    CollectionProgress,
    CollectionSet,
    DrawPoolRarity,
    DrawPoolRevision,
    RarityRevision,
)


def _rarity(
    *,
    id: int,
    key: str,
    display_name: str,
    sort_rank: int,
    effect_intensity: int,
) -> RarityRevision:
    return RarityRevision(
        id=id,
        key=key,
        display_name=display_name,
        sort_rank=sort_rank,
        effect_intensity=effect_intensity,
    )


_SET = CollectionSet(id=11, key="starter", display_name="起始收藏", total_cards=3)
_COMMON = _rarity(
    id=21,
    key="common",
    display_name="普通",
    sort_rank=10,
    effect_intensity=10,
)
_LEGENDARY = _rarity(
    id=23,
    key="legendary",
    display_name="傳說",
    sort_rank=30,
    effect_intensity=90,
)


def _card(
    *,
    card_id: int,
    revision_id: int,
    key: str,
    number: str,
    name: str,
    rarity: RarityRevision,
) -> CollectionCardRevision:
    return CollectionCardRevision(
        card_id=card_id,
        revision_id=revision_id,
        key=key,
        number=number,
        name=name,
        description=None,
        collection_set=_SET,
        rarity=rarity,
        portrait_url=None,
        square_url=None,
        backdrop_url=None,
    )


_COMMON_A = _card(
    card_id=31,
    revision_id=41,
    key="first-step",
    number="001",
    name="第一步",
    rarity=_COMMON,
)
_COMMON_B = _card(
    card_id=32,
    revision_id=42,
    key="campfire",
    number="002",
    name="營火",
    rarity=_COMMON,
)
_LEGENDARY_A = _card(
    card_id=33,
    revision_id=43,
    key="world-tree",
    number="003",
    name="世界樹",
    rarity=_LEGENDARY,
)


def _pool() -> DrawPoolRevision:
    return DrawPoolRevision(
        id=51,
        algorithm_version=ALGORITHM_VERSION,
        rarities=(
            DrawPoolRarity(rarity=_COMMON, weight=70, cards=(_COMMON_A, _COMMON_B)),
            DrawPoolRarity(rarity=_LEGENDARY, weight=5, cards=(_LEGENDARY_A,)),
        ),
    )


def test_fixed_entropy_produces_a_stable_selection_and_audit_values() -> None:
    entropy = bytes.fromhex("8000000000000000ffffffffffffffff")

    first = select_card(_pool(), entropy)
    second = select_card(_pool(), entropy)

    assert first == second
    assert first.pool_revision_id == 51
    assert first.algorithm_version == ALGORITHM_VERSION
    assert first.entropy == entropy
    assert first.rarity_roll == 37
    assert first.rarity_weight_total == 75
    assert first.card_roll == 1
    assert first.card_bucket_size == 2
    assert first.card == _COMMON_B


def test_uint64_boundaries_reach_first_and_last_weighted_buckets() -> None:
    first = select_card(_pool(), bytes(16))
    last = select_card(_pool(), b"\xff" * 16)

    assert first.card == _COMMON_A
    assert (first.rarity_roll, first.card_roll) == (0, 0)
    assert last.card == _LEGENDARY_A
    assert (last.rarity_roll, last.card_roll) == (74, 0)


def test_rejects_entropy_that_cannot_supply_both_rolls() -> None:
    with pytest.raises(ValueError, match="entropy must be exactly 16 bytes"):
        select_card(_pool(), b"too-short")


def test_rejects_a_positive_weight_rarity_with_no_cards() -> None:
    malformed = DrawPoolRevision(
        id=52,
        algorithm_version=ALGORITHM_VERSION,
        rarities=(DrawPoolRarity(rarity=_COMMON, weight=70, cards=()),),
    )

    with pytest.raises(ValueError, match="has no cards"):
        select_card(malformed, bytes(16))


def test_rejects_an_unknown_algorithm_or_missing_weight_table() -> None:
    unsupported = DrawPoolRevision(
        id=52,
        algorithm_version="weighted-rarity-v2",
        rarities=_pool().rarities,
    )
    empty = DrawPoolRevision(id=53, algorithm_version=ALGORITHM_VERSION, rarities=())

    with pytest.raises(ValueError, match="Unsupported draw algorithm"):
        select_card(unsupported, bytes(16))
    with pytest.raises(ValueError, match="has no rarity weights"):
        select_card(empty, bytes(16))


def test_rejects_a_nonpositive_rarity_weight() -> None:
    malformed = DrawPoolRevision(
        id=52,
        algorithm_version=ALGORITHM_VERSION,
        rarities=(DrawPoolRarity(rarity=_COMMON, weight=0, cards=(_COMMON_A,)),),
    )

    with pytest.raises(ValueError, match="non-positive weight"):
        select_card(malformed, bytes(16))


def test_weighted_boundaries_allocate_exactly_the_declared_integer_ranges() -> None:
    counts = {"common": 0, "legendary": 0}
    uint64_range = 1 << 64

    for expected_roll in range(75):
        # Pick the midpoint of each of the 75 scaled uint64 intervals.
        rarity_source = ((expected_roll * 2 + 1) * uint64_range) // 150
        entropy = rarity_source.to_bytes(8, "big") + bytes(8)
        selection = select_card(_pool(), entropy)
        assert selection.rarity_roll == expected_roll
        counts[selection.card.rarity.key] += 1

    assert counts == {"common": 70, "legendary": 5}


def test_collection_draw_builds_the_complete_neutral_event_snapshot() -> None:
    selection = select_card(_pool(), bytes(16))
    draw = CollectionDraw(
        id=61,
        selection=selection,
        is_new=True,
        copy_count=1,
        progress=CollectionProgress(owned_copies=1, unique_cards=1, total_cards=3),
    )

    assert draw.to_event_snapshot() == {
        "draw_id": 61,
        "pool_revision_id": 51,
        "algorithm_version": "weighted-rarity-v1",
        "card": {
            "id": 31,
            "revision_id": 41,
            "key": "first-step",
            "number": "001",
            "name": "第一步",
            "artwork": {
                "portrait_url": None,
                "square_url": None,
                "backdrop_url": None,
            },
        },
        "set": {"id": 11, "key": "starter", "name": "起始收藏"},
        "rarity": {
            "key": "common",
            "label": "普通",
            "rank": 10,
            "effect_intensity": 10,
        },
        "is_new": True,
        "copy_count": 1,
        "progress": {"owned_copies": 1, "unique_cards": 1, "total_cards": 3},
    }
