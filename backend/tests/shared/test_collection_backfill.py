"""Unit tests for deterministic historical check-in collection backfill."""

from __future__ import annotations

from datetime import date

import pytest

from shared.collection_backfill import (
    BACKFILL_POOL_KEY,
    BACKFILL_POOL_REVISION,
    BACKFILL_SEED_VERSION,
    MAX_BATCH_SIZE,
    derive_backfill_entropy,
    validate_batch_size,
)


def test_backfill_contract_is_pinned_to_the_first_official_pool_revision() -> None:
    assert BACKFILL_POOL_KEY == "official-all"
    assert BACKFILL_POOL_REVISION == 1
    assert BACKFILL_SEED_VERSION == "image-catalog-v1"


def test_entropy_is_stable_versioned_and_sensitive_to_every_identity_field() -> None:
    checkin_day = date(2026, 9, 8)
    expected = derive_backfill_entropy(
        channel_id="channel-a",
        user_id="viewer-a",
        checkin_date=checkin_day,
        checkin_id=42,
    )

    assert expected.hex() == "9e74746b4b7d71baca689f126457a5c7"
    assert expected == derive_backfill_entropy(
        channel_id="channel-a",
        user_id="viewer-a",
        checkin_date=checkin_day,
        checkin_id=42,
    )
    assert len(expected) == 16

    variants = {
        derive_backfill_entropy(
            channel_id="channel-b",
            user_id="viewer-a",
            checkin_date=checkin_day,
            checkin_id=42,
        ),
        derive_backfill_entropy(
            channel_id="channel-a",
            user_id="viewer-b",
            checkin_date=checkin_day,
            checkin_id=42,
        ),
        derive_backfill_entropy(
            channel_id="channel-a",
            user_id="viewer-a",
            checkin_date=date(2026, 9, 9),
            checkin_id=42,
        ),
        derive_backfill_entropy(
            channel_id="channel-a",
            user_id="viewer-a",
            checkin_date=checkin_day,
            checkin_id=43,
        ),
    }
    assert len(variants) == 4
    assert expected not in variants


@pytest.mark.parametrize("batch_size", [1, 100, MAX_BATCH_SIZE])
def test_batch_size_accepts_the_bounded_range(batch_size: int) -> None:
    assert validate_batch_size(batch_size) == batch_size


@pytest.mark.parametrize("batch_size", [0, -1, MAX_BATCH_SIZE + 1])
def test_batch_size_rejects_values_outside_the_bounded_range(batch_size: int) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        validate_batch_size(batch_size)
