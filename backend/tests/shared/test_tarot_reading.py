"""Deterministic Tarot topic slots and input normalization."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from shared.tarot_reading import get_daily_tarot_draw, normalize_tarot_category


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, "general"),
        ("", "general"),
        ("綜合", "general"),
        ("愛情", "love"),
        ("感情", "love"),
        ("工作", "career"),
        ("學業", "career"),
        ("金錢", "finance"),
        ("財運", "finance"),
        (" CAREER ", "career"),
    ],
)
def test_normalizes_supported_topic_aliases(raw: str | None, expected: str) -> None:
    assert normalize_tarot_category(raw) == expected


def test_unknown_topic_is_not_silently_treated_as_general() -> None:
    assert normalize_tarot_category("健康") is None


def test_daily_draw_is_stable_per_topic_slot_but_topics_are_independent() -> None:
    card_ids = [str(index) for index in range(78)]
    now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

    first = get_daily_tarot_draw(card_ids, user_id="u1", category="love", now=now)
    repeated = get_daily_tarot_draw(card_ids, user_id="u1", category="love", now=now)
    topic_draws = {
        get_daily_tarot_draw(card_ids, user_id="u1", category=category, now=now)
        for category in ("general", "love", "career", "finance")
    }

    assert repeated == first
    assert len(topic_draws) > 1


def test_daily_draw_rejects_unknown_category() -> None:
    with pytest.raises(ValueError, match="Unsupported Tarot category"):
        get_daily_tarot_draw(["0"], user_id="u1", category="health")
