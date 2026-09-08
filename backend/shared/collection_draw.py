"""Pure, auditable selection for the first collection draw algorithm."""

from __future__ import annotations

from typing import Final

from shared.models.collection import DrawPoolRevision, DrawSelection

ALGORITHM_VERSION: Final = "weighted-rarity-v1"
_UINT64_RANGE: Final = 1 << 64


def _scale_uint64(value: int, upper_bound: int) -> int:
    """Map a uint64 into ``range(upper_bound)`` without floating-point drift."""
    return value * upper_bound // _UINT64_RANGE


def select_card(pool: DrawPoolRevision, entropy: bytes) -> DrawSelection:
    """Select rarity then card deterministically from exactly 128 bits of entropy."""
    if len(entropy) != 16:
        raise ValueError("entropy must be exactly 16 bytes")
    if pool.algorithm_version != ALGORITHM_VERSION:
        raise ValueError(f"Unsupported draw algorithm: {pool.algorithm_version}")
    if not pool.rarities:
        raise ValueError(f"Draw pool {pool.id} has no rarity weights")

    for bucket in pool.rarities:
        if bucket.weight <= 0:
            raise ValueError(f"Rarity {bucket.rarity.key} has a non-positive weight")
        if not bucket.cards:
            raise ValueError(f"Rarity {bucket.rarity.key} has no cards")

    rarity_weight_total = sum(bucket.weight for bucket in pool.rarities)
    rarity_source = int.from_bytes(entropy[:8], byteorder="big", signed=False)
    rarity_roll = _scale_uint64(rarity_source, rarity_weight_total)

    selected_bucket = pool.rarities[-1]
    cursor = 0
    for bucket in pool.rarities:
        cursor += bucket.weight
        if rarity_roll < cursor:
            selected_bucket = bucket
            break

    card_bucket_size = len(selected_bucket.cards)
    card_source = int.from_bytes(entropy[8:], byteorder="big", signed=False)
    card_roll = _scale_uint64(card_source, card_bucket_size)

    return DrawSelection(
        pool_revision_id=pool.id,
        algorithm_version=pool.algorithm_version,
        card=selected_bucket.cards[card_roll],
        entropy=entropy,
        rarity_roll=rarity_roll,
        rarity_weight_total=rarity_weight_total,
        card_roll=card_roll,
        card_bucket_size=card_bucket_size,
    )
