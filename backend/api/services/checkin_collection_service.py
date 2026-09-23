"""Read the official check-in card catalog and choose one immutable set pool."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncpg


@dataclass(frozen=True, slots=True)
class CheckinCollectionCard:
    key: str
    number: int
    name: str
    portrait_url: str
    rarity_key: str
    rarity_name: str


@dataclass(frozen=True, slots=True)
class CheckinCollectionSet:
    key: str
    name: str
    card_count: int
    cards: tuple[CheckinCollectionCard, ...]


@dataclass(frozen=True, slots=True)
class CheckinCollectionSnapshot:
    selected_set_key: str | None
    total_cards: int
    sets: tuple[CheckinCollectionSet, ...]


_CATALOG_SQL = """
SELECT
    collection_set.set_key,
    collection_set.display_name AS set_name,
    collection_set.total_cards AS card_count,
    card.card_key,
    card.card_number,
    revision.display_name AS card_name,
    revision.portrait_url,
    rarity.rarity_key,
    rarity.display_name AS rarity_name
FROM collection_system_settings AS settings
JOIN draw_pool_entries AS entry
  ON entry.pool_revision_id = settings.fallback_pool_revision_id
JOIN collection_card_revisions AS revision
  ON revision.id = entry.card_revision_id
 AND revision.card_id = entry.card_id
JOIN collection_cards AS card ON card.id = revision.card_id
JOIN collection_sets AS collection_set ON collection_set.id = card.set_id
JOIN rarity_definition_revisions AS rarity ON rarity.id = card.rarity_revision_id
WHERE settings.singleton = 1
  AND collection_set.published_at IS NOT NULL
  AND revision.portrait_url IS NOT NULL
ORDER BY collection_set.set_key, card.card_number
"""

_SELECTED_SET_SQL = """
SELECT MIN(collection_set.set_key)
FROM channel_collection_settings AS channel_settings
JOIN draw_pool_revisions AS pool
  ON pool.id = channel_settings.active_pool_revision_id
JOIN draw_pool_entries AS entry ON entry.pool_revision_id = pool.id
JOIN collection_cards AS card ON card.id = entry.card_id
JOIN collection_sets AS collection_set ON collection_set.id = card.set_id
WHERE channel_settings.channel_id = $1
  AND pool.published_at IS NOT NULL
  AND pool.pool_key = 'official-set-' || collection_set.set_key
GROUP BY pool.id
HAVING COUNT(DISTINCT collection_set.set_key) = 1
"""


class CheckinCollectionService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_snapshot(self, channel_id: str) -> CheckinCollectionSnapshot:
        async with self._pool.acquire() as conn:
            return await self._snapshot(conn, channel_id)

    async def select_set(
        self,
        channel_id: str,
        set_key: str | None,
    ) -> CheckinCollectionSnapshot:
        async with self._pool.acquire() as conn, conn.transaction():
            pool_revision_id: int | None = None
            if set_key is not None:
                pool_revision_id = await conn.fetchval(
                    """
                    SELECT pool.id
                    FROM draw_pool_revisions AS pool
                    JOIN draw_pool_entries AS entry ON entry.pool_revision_id = pool.id
                    JOIN collection_cards AS card ON card.id = entry.card_id
                    JOIN collection_sets AS collection_set ON collection_set.id = card.set_id
                    WHERE pool.pool_key = 'official-set-' || $1
                      AND pool.published_at IS NOT NULL
                      AND collection_set.set_key = $1
                    GROUP BY pool.id, pool.revision_number
                    HAVING COUNT(DISTINCT collection_set.set_key) = 1
                    ORDER BY pool.revision_number DESC
                    LIMIT 1
                    """,
                    set_key,
                )
                if pool_revision_id is None:
                    raise ValueError("unknown collection set")

            await conn.execute(
                """
                INSERT INTO channel_collection_settings
                    (channel_id, active_pool_revision_id)
                VALUES ($1, $2)
                ON CONFLICT (channel_id) DO UPDATE
                SET active_pool_revision_id = EXCLUDED.active_pool_revision_id
                """,
                channel_id,
                pool_revision_id,
            )
            return await self._snapshot(conn, channel_id)

    async def _snapshot(
        self,
        conn: asyncpg.Connection,
        channel_id: str,
    ) -> CheckinCollectionSnapshot:
        rows = await conn.fetch(_CATALOG_SQL)
        selected_set_key = await conn.fetchval(_SELECTED_SET_SQL, channel_id)
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            set_key = str(row["set_key"])
            group = grouped.setdefault(
                set_key,
                {
                    "name": str(row["set_name"]),
                    "card_count": int(row["card_count"]),
                    "cards": [],
                },
            )
            group["cards"].append(
                CheckinCollectionCard(
                    key=str(row["card_key"]),
                    number=int(row["card_number"]),
                    name=str(row["card_name"]),
                    portrait_url=str(row["portrait_url"]),
                    rarity_key=str(row["rarity_key"]),
                    rarity_name=str(row["rarity_name"]),
                )
            )

        sets = tuple(
            CheckinCollectionSet(
                key=key,
                name=str(value["name"]),
                card_count=int(value["card_count"]),
                cards=tuple(value["cards"]),
            )
            for key, value in grouped.items()
        )
        return CheckinCollectionSnapshot(
            selected_set_key=str(selected_set_key) if selected_set_key is not None else None,
            total_cards=sum(len(item.cards) for item in sets),
            sets=sets,
        )
