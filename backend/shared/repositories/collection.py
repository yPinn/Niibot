"""Persistence for immutable collection pools and per-check-in card draws."""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

import asyncpg

from shared.collection_draw import select_card
from shared.models.collection import (
    CollectionCardRevision,
    CollectionDraw,
    CollectionProgress,
    CollectionSet,
    DrawPoolRarity,
    DrawPoolRevision,
    DrawSelection,
    OwnedCollectionCard,
    RarityRevision,
)

LOGGER = logging.getLogger(__name__)

_POOL_SELECT = """
    SELECT
        pool.id AS pool_revision_id,
        pool.algorithm_version,
        weight.rarity_revision_id,
        rarity.rarity_key,
        rarity.display_name AS rarity_display_name,
        rarity.sort_rank,
        rarity.effect_intensity,
        weight.weight,
        item.card_revision_id,
        item.card_id,
        item.card_key,
        item.card_number,
        item.card_display_name,
        item.description,
        item.portrait_url,
        item.square_url,
        item.backdrop_url,
        item.set_id,
        item.set_key,
        item.set_display_name,
        item.total_cards,
        item.entry_order
    FROM draw_pool_revisions AS pool
    JOIN draw_pool_rarity_weights AS weight
      ON weight.pool_revision_id = pool.id
    JOIN rarity_definition_revisions AS rarity
      ON rarity.id = weight.rarity_revision_id
    LEFT JOIN LATERAL (
        SELECT
            revision.id AS card_revision_id,
            card.id AS card_id,
            card.card_key,
            card.card_number,
            revision.display_name AS card_display_name,
            revision.description,
            revision.portrait_url,
            revision.square_url,
            revision.backdrop_url,
            collection_set.id AS set_id,
            collection_set.set_key,
            collection_set.display_name AS set_display_name,
            collection_set.total_cards,
            entry.entry_order
        FROM draw_pool_entries AS entry
        JOIN collection_card_revisions AS revision
          ON revision.id = entry.card_revision_id
         AND revision.card_id = entry.card_id
        JOIN collection_cards AS card
          ON card.id = revision.card_id
        JOIN collection_sets AS collection_set
          ON collection_set.id = card.set_id
         AND collection_set.published_at IS NOT NULL
        WHERE entry.pool_revision_id = pool.id
          AND card.rarity_revision_id = weight.rarity_revision_id
        ORDER BY entry.entry_order
    ) AS item ON TRUE
    WHERE pool.id = $1
      AND pool.published_at IS NOT NULL
    ORDER BY rarity.sort_rank, weight.rarity_revision_id, item.entry_order
"""

_DRAW_SELECT = """
    SELECT
        draw.id AS draw_id,
        draw.pool_revision_id,
        draw.algorithm_version,
        draw.entropy,
        draw.rarity_roll,
        draw.rarity_weight_total,
        draw.card_roll,
        draw.card_bucket_size,
        revision.id AS card_revision_id,
        card.id AS card_id,
        card.card_key,
        card.card_number,
        revision.display_name AS card_display_name,
        revision.description,
        revision.portrait_url,
        revision.square_url,
        revision.backdrop_url,
        collection_set.id AS set_id,
        collection_set.set_key,
        collection_set.display_name AS set_display_name,
        collection_set.total_cards,
        rarity.id AS rarity_revision_id,
        rarity.rarity_key,
        rarity.display_name AS rarity_display_name,
        rarity.sort_rank,
        rarity.effect_intensity,
        progress.copy_count,
        progress.owned_copies,
        progress.unique_cards
    FROM viewer_card_draws AS draw
    JOIN collection_card_revisions AS revision
      ON revision.id = draw.card_revision_id
    JOIN collection_cards AS card
      ON card.id = revision.card_id
    JOIN collection_sets AS collection_set
      ON collection_set.id = card.set_id
    JOIN rarity_definition_revisions AS rarity
      ON rarity.id = card.rarity_revision_id
    CROSS JOIN LATERAL (
        SELECT
            COUNT(*) FILTER (WHERE owned_card.id = card.id)::INT AS copy_count,
            COUNT(*)::INT AS owned_copies,
            COUNT(DISTINCT owned_card.id)::INT AS unique_cards
        FROM viewer_card_draws AS owned_draw
        JOIN collection_card_revisions AS owned_revision
          ON owned_revision.id = owned_draw.card_revision_id
        JOIN collection_cards AS owned_card
          ON owned_card.id = owned_revision.card_id
        WHERE owned_draw.channel_id = draw.channel_id
          AND owned_draw.user_id = draw.user_id
          AND owned_card.set_id = card.set_id
    ) AS progress
    WHERE draw.channel_id = $1
      AND draw.user_id = $2
      AND draw.checkin_id = $3
"""

_OWNED_CARDS_SELECT = """
    SELECT
        inventory.card_revision_id,
        inventory.card_id,
        inventory.card_key,
        inventory.card_number,
        inventory.card_display_name,
        inventory.description,
        inventory.portrait_url,
        inventory.square_url,
        inventory.backdrop_url,
        inventory.set_id,
        inventory.set_key,
        inventory.set_display_name,
        inventory.total_cards,
        inventory.rarity_revision_id,
        inventory.rarity_key,
        inventory.rarity_display_name,
        inventory.sort_rank,
        inventory.effect_intensity,
        inventory.copy_count
    FROM (
        SELECT DISTINCT ON (owned_card.id)
            owned_revision.id AS card_revision_id,
            owned_card.id AS card_id,
            owned_card.card_key,
            owned_card.card_number,
            owned_revision.display_name AS card_display_name,
            owned_revision.description,
            owned_revision.portrait_url,
            owned_revision.square_url,
            owned_revision.backdrop_url,
            collection_set.id AS set_id,
            collection_set.set_key,
            collection_set.display_name AS set_display_name,
            collection_set.total_cards,
            rarity.id AS rarity_revision_id,
            rarity.rarity_key,
            rarity.display_name AS rarity_display_name,
            rarity.sort_rank,
            rarity.effect_intensity,
            COUNT(*) OVER (PARTITION BY owned_card.id)::INT AS copy_count
        FROM viewer_card_draws AS owned_draw
        JOIN collection_card_revisions AS owned_revision
          ON owned_revision.id = owned_draw.card_revision_id
        JOIN collection_cards AS owned_card
          ON owned_card.id = owned_revision.card_id
        JOIN collection_sets AS collection_set
          ON collection_set.id = owned_card.set_id
        JOIN rarity_definition_revisions AS rarity
          ON rarity.id = owned_card.rarity_revision_id
        WHERE owned_draw.channel_id = $1
          AND owned_draw.user_id = $2
          AND owned_card.set_id = $3
        ORDER BY owned_card.id, owned_draw.drawn_at DESC, owned_draw.id DESC
    ) AS inventory
    ORDER BY inventory.card_number, inventory.card_id
"""


class CollectionRepository:
    """Draw against a caller-owned connection so attendance stays atomic."""

    def __init__(self, *, entropy_source: Callable[[int], bytes] = secrets.token_bytes) -> None:
        self._entropy_source = entropy_source

    async def load_published_pool(
        self,
        conn: asyncpg.Connection,
        *,
        pool_key: str,
        revision_number: int,
    ) -> DrawPoolRevision:
        """Load one exact immutable pool revision without consulting mutable settings."""
        pool_id = await conn.fetchval(
            """
            SELECT id
            FROM draw_pool_revisions
            WHERE pool_key = $1
              AND revision_number = $2
              AND published_at IS NOT NULL
            """,
            pool_key,
            revision_number,
        )
        if pool_id is None:
            raise RuntimeError(
                f"Published collection pool {pool_key!r} revision {revision_number} is unavailable"
            )
        pool = _pool_from_rows(await conn.fetch(_POOL_SELECT, int(pool_id)))
        if pool is None:
            raise RuntimeError(
                f"Published collection pool {pool_key!r} revision {revision_number} is unusable"
            )
        return pool

    async def insert_draw_selection(
        self,
        conn: asyncpg.Connection,
        *,
        channel_id: str,
        user_id: str,
        checkin_id: int,
        drawn_at: datetime,
        selection: DrawSelection,
    ) -> bool:
        """Insert an audited selection, returning False when that check-in already has a draw.

        The caller owns the transaction and must serialize writes with the same
        per-viewer advisory lock used by :meth:`draw_for_checkin`.
        """
        row = await conn.fetchrow(
            """
            INSERT INTO viewer_card_draws
                (channel_id, user_id, checkin_id, pool_revision_id, card_revision_id,
                 algorithm_version, entropy, rarity_roll, rarity_weight_total,
                 card_roll, card_bucket_size, drawn_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (checkin_id) DO NOTHING
            RETURNING id
            """,
            channel_id,
            user_id,
            checkin_id,
            selection.pool_revision_id,
            selection.card.revision_id,
            selection.algorithm_version,
            selection.entropy,
            selection.rarity_roll,
            selection.rarity_weight_total,
            selection.card_roll,
            selection.card_bucket_size,
            drawn_at,
        )
        return row is not None

    async def draw_for_checkin(
        self,
        conn: asyncpg.Connection,
        *,
        channel_id: str,
        user_id: str,
        checkin_id: int,
        drawn_at: datetime,
    ) -> CollectionDraw:
        """Persist or load the one immutable draw belonging to a check-in."""
        # Copy counts and NEW state must be serialized per viewer, including
        # future historical backfills that may process several days concurrently.
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1 || ':' || $2, 0))",
            channel_id,
            user_id,
        )
        settings = await conn.fetchrow(
            """
            SELECT channel_settings.active_pool_revision_id,
                   system_settings.fallback_pool_revision_id
            FROM collection_system_settings AS system_settings
            LEFT JOIN channel_collection_settings AS channel_settings
              ON channel_settings.channel_id = $1
            WHERE system_settings.singleton = 1
            """,
            channel_id,
        )
        if settings is None:
            raise RuntimeError("Collection official fallback pool is not configured")

        active_pool_id = settings["active_pool_revision_id"]
        fallback_pool_id = settings["fallback_pool_revision_id"]
        candidate_ids: list[int] = []
        for candidate in (active_pool_id, fallback_pool_id):
            if candidate is not None and int(candidate) not in candidate_ids:
                candidate_ids.append(int(candidate))

        entropy = self._entropy_source(16)
        if len(entropy) != 16:
            raise RuntimeError("Collection entropy source must return exactly 16 bytes")

        selection: DrawSelection | None = None
        active_pool = int(active_pool_id) if active_pool_id is not None else None
        fallback_pool = int(fallback_pool_id) if fallback_pool_id is not None else None
        for pool_id in candidate_ids:
            rows = await conn.fetch(_POOL_SELECT, pool_id)
            pool = _pool_from_rows(rows)
            if pool is None:
                if pool_id == active_pool and active_pool != fallback_pool:
                    _log_active_pool_fallback(channel_id, pool_id, "unavailable_or_unpublished")
                continue
            try:
                selection = select_card(pool, entropy)
            except ValueError as exc:
                if pool_id == active_pool and active_pool != fallback_pool:
                    _log_active_pool_fallback(channel_id, pool_id, str(exc))
                continue
            break
        if selection is None:
            raise RuntimeError("Collection official fallback pool is unavailable")

        await conn.fetchrow(
            """
            INSERT INTO viewer_card_draws
                (channel_id, user_id, checkin_id, pool_revision_id, card_revision_id,
                 algorithm_version, entropy, rarity_roll, rarity_weight_total,
                 card_roll, card_bucket_size, drawn_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (checkin_id) DO NOTHING
            RETURNING id
            """,
            channel_id,
            user_id,
            checkin_id,
            selection.pool_revision_id,
            selection.card.revision_id,
            selection.algorithm_version,
            selection.entropy,
            selection.rarity_roll,
            selection.rarity_weight_total,
            selection.card_roll,
            selection.card_bucket_size,
            drawn_at,
        )
        row = await conn.fetchrow(_DRAW_SELECT, channel_id, user_id, checkin_id)
        if row is None:
            raise RuntimeError("Failed to persist or load collection draw")
        owned_rows = await conn.fetch(
            _OWNED_CARDS_SELECT,
            channel_id,
            user_id,
            int(row["set_id"]),
        )
        return _draw_from_row(row, owned_rows)


def _pool_from_rows(rows: Sequence[Mapping[str, Any]]) -> DrawPoolRevision | None:
    if not rows:
        return None

    first = rows[0]
    rarity_records: dict[int, RarityRevision] = {}
    rarity_weights: dict[int, int] = {}
    cards_by_rarity: dict[int, list[CollectionCardRevision]] = {}
    seen_revisions: set[int] = set()

    for row in rows:
        rarity_id = int(row["rarity_revision_id"])
        if rarity_id not in rarity_records:
            rarity_records[rarity_id] = RarityRevision(
                id=rarity_id,
                key=str(row["rarity_key"]),
                display_name=str(row["rarity_display_name"]),
                sort_rank=int(row["sort_rank"]),
                effect_intensity=int(row["effect_intensity"]),
            )
            rarity_weights[rarity_id] = int(row["weight"])
            cards_by_rarity[rarity_id] = []

        revision_id_value = row["card_revision_id"]
        if revision_id_value is None:
            continue
        revision_id = int(revision_id_value)
        if revision_id in seen_revisions:
            continue
        seen_revisions.add(revision_id)
        collection_set = CollectionSet(
            id=int(row["set_id"]),
            key=str(row["set_key"]),
            display_name=str(row["set_display_name"]),
            total_cards=int(row["total_cards"]),
        )
        cards_by_rarity[rarity_id].append(
            CollectionCardRevision(
                card_id=int(row["card_id"]),
                revision_id=revision_id,
                key=str(row["card_key"]),
                number=f"{int(row['card_number']):03d}",
                name=str(row["card_display_name"]),
                description=str(row["description"]) or None,
                collection_set=collection_set,
                rarity=rarity_records[rarity_id],
                portrait_url=_optional_text(row["portrait_url"]),
                square_url=_optional_text(row["square_url"]),
                backdrop_url=_optional_text(row["backdrop_url"]),
            )
        )

    return DrawPoolRevision(
        id=int(first["pool_revision_id"]),
        algorithm_version=str(first["algorithm_version"]),
        rarities=tuple(
            DrawPoolRarity(
                rarity=rarity,
                weight=rarity_weights[rarity.id],
                cards=tuple(cards_by_rarity[rarity.id]),
            )
            for rarity in rarity_records.values()
        ),
    )


def _card_from_row(row: Mapping[str, Any]) -> CollectionCardRevision:
    rarity = RarityRevision(
        id=int(row["rarity_revision_id"]),
        key=str(row["rarity_key"]),
        display_name=str(row["rarity_display_name"]),
        sort_rank=int(row["sort_rank"]),
        effect_intensity=int(row["effect_intensity"]),
    )
    collection_set = CollectionSet(
        id=int(row["set_id"]),
        key=str(row["set_key"]),
        display_name=str(row["set_display_name"]),
        total_cards=int(row["total_cards"]),
    )
    return CollectionCardRevision(
        card_id=int(row["card_id"]),
        revision_id=int(row["card_revision_id"]),
        key=str(row["card_key"]),
        number=f"{int(row['card_number']):03d}",
        name=str(row["card_display_name"]),
        description=str(row["description"]) or None,
        collection_set=collection_set,
        rarity=rarity,
        portrait_url=_optional_text(row["portrait_url"]),
        square_url=_optional_text(row["square_url"]),
        backdrop_url=_optional_text(row["backdrop_url"]),
    )


def _draw_from_row(
    row: Mapping[str, Any],
    owned_rows: Sequence[Mapping[str, Any]],
) -> CollectionDraw:
    card = _card_from_row(row)
    selection = DrawSelection(
        pool_revision_id=int(row["pool_revision_id"]),
        algorithm_version=str(row["algorithm_version"]),
        card=card,
        entropy=bytes(row["entropy"]),
        rarity_roll=int(row["rarity_roll"]),
        rarity_weight_total=int(row["rarity_weight_total"]),
        card_roll=int(row["card_roll"]),
        card_bucket_size=int(row["card_bucket_size"]),
    )
    copy_count = int(row["copy_count"])
    owned_cards = tuple(
        _owned_card_from_row(owned_row, selected_card=card) for owned_row in owned_rows
    )
    owned_copies = int(row["owned_copies"])
    unique_cards = int(row["unique_cards"])
    selected_inventory_item = next(
        (item for item in owned_cards if item.card.card_id == card.card_id),
        None,
    )
    if (
        len(owned_cards) != unique_cards
        or sum(item.copy_count for item in owned_cards) != owned_copies
        or selected_inventory_item is None
        or selected_inventory_item.copy_count != copy_count
    ):
        raise RuntimeError("Collection inventory does not match draw progress")
    return CollectionDraw(
        id=int(row["draw_id"]),
        selection=selection,
        is_new=copy_count == 1,
        copy_count=copy_count,
        progress=CollectionProgress(
            owned_copies=owned_copies,
            unique_cards=unique_cards,
            total_cards=card.collection_set.total_cards,
        ),
        owned_cards=owned_cards,
    )


def _owned_card_from_row(
    row: Mapping[str, Any],
    *,
    selected_card: CollectionCardRevision,
) -> OwnedCollectionCard:
    inventory_card = _card_from_row(row)
    return OwnedCollectionCard(
        card=(selected_card if inventory_card.card_id == selected_card.card_id else inventory_card),
        copy_count=int(row["copy_count"]),
    )


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None else None


def _log_active_pool_fallback(channel_id: str, pool_revision_id: int, reason: str) -> None:
    LOGGER.warning(
        "collection_active_pool_fallback",
        extra={
            "channel_id": channel_id,
            "pool_revision_id": pool_revision_id,
            "reason": reason,
        },
    )
