"""Resumable historical check-in to collection-draw backfill.

The historical assignment contract is intentionally frozen to the first
image-backed official pool. Mutable channel and system pool pointers are not
consulted, so a rerun produces the same selection for a given check-in.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

import asyncpg

from shared.collection_draw import select_card
from shared.repositories.collection import CollectionRepository

BACKFILL_POOL_KEY: Final = "official-all"
BACKFILL_POOL_REVISION: Final = 1
BACKFILL_SEED_VERSION: Final = "image-catalog-v1"
DEFAULT_BATCH_SIZE: Final = 100
MAX_BATCH_SIZE: Final = 1000

_SEED: Final = f"niibot/checkin-collection/{BACKFILL_SEED_VERSION}".encode()
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BackfillReport:
    """Stable counters returned to the operational CLI."""

    scanned: int
    inserted: int
    skipped: int
    remaining: int
    failures: int


@dataclass(frozen=True, slots=True)
class _HistoricalCheckin:
    id: int
    channel_id: str
    user_id: str
    checkin_date: date
    created_at: datetime


def validate_batch_size(batch_size: int) -> int:
    """Validate the maximum number of one viewer's check-ins per transaction."""
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
    return batch_size


def derive_backfill_entropy(
    *,
    channel_id: str,
    user_id: str,
    checkin_date: date,
    checkin_id: int,
) -> bytes:
    """Derive the frozen 128-bit historical draw input without mutable state.

    Length-prefixed fields make the encoding unambiguous if identifier formats
    expand later. The seed embeds a version so any future algorithm is a new,
    explicit migration contract instead of a silent reshuffle.
    """
    fields = (
        _SEED,
        channel_id.encode("utf-8"),
        user_id.encode("utf-8"),
        checkin_date.isoformat().encode("ascii"),
        str(checkin_id).encode("ascii"),
    )
    digest = hashlib.sha256()
    for field in fields:
        digest.update(len(field).to_bytes(4, byteorder="big", signed=False))
        digest.update(field)
    return digest.digest()[:16]


async def backfill_checkin_collections(
    conn: asyncpg.Connection,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
) -> BackfillReport:
    """Fill only missing historical draws in deterministic ledger order.

    Work is committed in bounded, single-viewer transactions. A failed viewer
    batch is rolled back and left missing for a later rerun while the current run
    continues with the next viewer.
    """
    validate_batch_size(batch_size)
    repository = CollectionRepository()
    pool = await repository.load_published_pool(
        conn,
        pool_key=BACKFILL_POOL_KEY,
        revision_number=BACKFILL_POOL_REVISION,
    )

    candidate_count = await _count_missing(conn)
    if dry_run:
        return BackfillReport(
            scanned=candidate_count,
            inserted=0,
            skipped=candidate_count,
            remaining=candidate_count,
            failures=0,
        )

    scanned = 0
    inserted = 0
    skipped = 0
    failures = 0
    after_channel_id: str | None = None
    after_user_id: str | None = None

    while viewer := await _next_viewer(conn, after_channel_id, after_user_id):
        channel_id, user_id = viewer

        while True:
            rows: list[_HistoricalCheckin] = []
            batch_inserted = 0
            batch_skipped = 0
            try:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended($1 || ':' || $2, 0))",
                        channel_id,
                        user_id,
                    )
                    records = await conn.fetch(
                        """
                        SELECT
                            checkin.id,
                            checkin.channel_id,
                            checkin.user_id,
                            checkin.checkin_date,
                            checkin.created_at
                        FROM viewer_checkins AS checkin
                        WHERE checkin.channel_id = $1
                          AND checkin.user_id = $2
                          AND NOT EXISTS (
                              SELECT 1
                              FROM viewer_card_draws AS draw
                              WHERE draw.checkin_id = checkin.id
                          )
                        ORDER BY checkin.checkin_date, checkin.id
                        LIMIT $3
                        """,
                        channel_id,
                        user_id,
                        batch_size,
                    )
                    rows = [_historical_checkin(record) for record in records]
                    scanned += len(rows)
                    for row in rows:
                        entropy = derive_backfill_entropy(
                            channel_id=row.channel_id,
                            user_id=row.user_id,
                            checkin_date=row.checkin_date,
                            checkin_id=row.id,
                        )
                        selection = select_card(pool, entropy)
                        was_inserted = await repository.insert_draw_selection(
                            conn,
                            channel_id=row.channel_id,
                            user_id=row.user_id,
                            checkin_id=row.id,
                            drawn_at=row.created_at,
                            selection=selection,
                        )
                        if was_inserted:
                            batch_inserted += 1
                        else:
                            batch_skipped += 1
            except Exception:
                failures += 1
                _LOGGER.exception(
                    "collection_backfill_viewer_batch_failed",
                    extra={
                        "channel_id": channel_id,
                        "user_id": user_id,
                        "checkin_count": len(rows),
                    },
                )
                break

            inserted += batch_inserted
            skipped += batch_skipped
            if not rows:
                break

        after_channel_id = channel_id
        after_user_id = user_id

    return BackfillReport(
        scanned=scanned,
        inserted=inserted,
        skipped=skipped,
        remaining=await _count_missing(conn),
        failures=failures,
    )


async def _count_missing(conn: asyncpg.Connection) -> int:
    return int(
        await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM viewer_checkins AS checkin
            WHERE NOT EXISTS (
                SELECT 1
                FROM viewer_card_draws AS draw
                WHERE draw.checkin_id = checkin.id
            )
            """
        )
        or 0
    )


async def _next_viewer(
    conn: asyncpg.Connection,
    after_channel_id: str | None,
    after_user_id: str | None,
) -> tuple[str, str] | None:
    row = await conn.fetchrow(
        """
        SELECT checkin.channel_id, checkin.user_id
        FROM viewer_checkins AS checkin
        WHERE NOT EXISTS (
            SELECT 1
            FROM viewer_card_draws AS draw
            WHERE draw.checkin_id = checkin.id
        )
          AND (
              $1::TEXT IS NULL
              OR checkin.channel_id > $1
              OR (checkin.channel_id = $1 AND checkin.user_id > $2)
          )
        GROUP BY checkin.channel_id, checkin.user_id
        ORDER BY checkin.channel_id, checkin.user_id
        LIMIT 1
        """,
        after_channel_id,
        after_user_id,
    )
    if row is None:
        return None
    return str(row["channel_id"]), str(row["user_id"])


def _historical_checkin(record: asyncpg.Record) -> _HistoricalCheckin:
    return _HistoricalCheckin(
        id=int(record["id"]),
        channel_id=str(record["channel_id"]),
        user_id=str(record["user_id"]),
        checkin_date=record["checkin_date"],
        created_at=record["created_at"],
    )
