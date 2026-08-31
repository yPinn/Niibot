"""Shared Tarot topic normalization and deterministic daily draws."""

from __future__ import annotations

import random
from collections.abc import Iterable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Final

TAROT_CATEGORY_LABELS: Final[dict[str, str]] = {
    "general": "綜合",
    "love": "感情",
    "career": "事業",
    "finance": "財運",
}

_CATEGORY_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "general": ("g", "general", "綜合", "整體", "預設"),
    "love": ("l", "love", "感情", "愛情"),
    "career": ("c", "career", "事業", "工作", "學業"),
    "finance": ("f", "finance", "財運", "財務", "金錢"),
}

_CATEGORY_BY_ALIAS: Final = {
    alias.casefold(): category
    for category, aliases in _CATEGORY_ALIASES.items()
    for alias in aliases
}


def normalize_tarot_category(value: str | None) -> str | None:
    """Return a canonical topic, using general only when the topic is omitted."""
    normalized = (value or "").strip().casefold()
    if not normalized:
        return "general"
    return _CATEGORY_BY_ALIAS.get(normalized)


def get_daily_tarot_draw(
    card_ids: Iterable[str],
    *,
    user_id: str | int,
    category: str,
    now: datetime | None = None,
) -> tuple[str, bool]:
    """Return one stable card and orientation for a user's UTC-day topic slot."""
    if category not in TAROT_CATEGORY_LABELS:
        raise ValueError(f"Unsupported Tarot category: {category}")

    cards = tuple(sorted(card_ids))
    if not cards:
        raise ValueError("Tarot deck must contain at least one card")

    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    slot = f"tarot-v2|{user_id}|{current.astimezone(UTC).date().isoformat()}|{category}"
    seed = int.from_bytes(sha256(slot.encode("utf-8")).digest()[:16], "big")
    rng = random.Random(seed)
    return rng.choice(cards), rng.choice((True, False))
