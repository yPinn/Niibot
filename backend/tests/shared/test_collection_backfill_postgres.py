"""PostgreSQL integration contract for historical collection draws."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import asyncpg
import pytest

from shared.collection_backfill import (
    BACKFILL_POOL_KEY,
    BACKFILL_POOL_REVISION,
    backfill_checkin_collections,
    derive_backfill_entropy,
)
from shared.repositories.collection import CollectionRepository

_DATABASE_URL = os.getenv("NIIBOT_TEST_DATABASE_URL", "")


async def _create_alternate_published_pool(conn: asyncpg.Connection, suffix: str) -> int:
    official_pool_id = await conn.fetchval(
        """
        SELECT id
        FROM draw_pool_revisions
        WHERE pool_key = $1
          AND revision_number = $2
          AND published_at IS NOT NULL
        """,
        BACKFILL_POOL_KEY,
        BACKFILL_POOL_REVISION,
    )
    assert official_pool_id is not None
    alternate_pool_id = await conn.fetchval(
        """
        INSERT INTO draw_pool_revisions
            (pool_key, revision_number, algorithm_version)
        VALUES ($1, 1, 'weighted-rarity-v1')
        RETURNING id
        """,
        f"backfill-alternate-{suffix}",
    )
    await conn.execute(
        """
        INSERT INTO draw_pool_rarity_weights
            (pool_revision_id, rarity_revision_id, weight)
        SELECT $1, rarity_revision_id, weight
        FROM draw_pool_rarity_weights
        WHERE pool_revision_id = $2
        """,
        alternate_pool_id,
        official_pool_id,
    )
    await conn.execute(
        """
        INSERT INTO draw_pool_entries
            (pool_revision_id, card_revision_id, entry_order)
        SELECT $1, card_revision_id, entry_order
        FROM draw_pool_entries
        WHERE pool_revision_id = $2
        """,
        alternate_pool_id,
        official_pool_id,
    )
    await conn.execute(
        "UPDATE draw_pool_revisions SET published_at = NOW() WHERE id = $1",
        alternate_pool_id,
    )
    return int(alternate_pool_id)


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_backfill_is_deterministic_resumable_and_ignores_mutable_pool_pointers() -> None:
    conn = await asyncpg.connect(_DATABASE_URL, statement_cache_size=0)
    outer = conn.transaction()
    await outer.start()
    suffix = uuid4().hex
    channel_a = f"backfill-a-{suffix}"
    channel_b = f"backfill-b-{suffix}"
    try:
        await conn.executemany(
            "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
            [(channel_b,), (channel_a,)],
        )
        official_pool_id = await conn.fetchval(
            """
            SELECT id
            FROM draw_pool_revisions
            WHERE pool_key = $1
              AND revision_number = $2
              AND published_at IS NOT NULL
            """,
            BACKFILL_POOL_KEY,
            BACKFILL_POOL_REVISION,
        )
        alternate_pool_id = await _create_alternate_published_pool(conn, suffix)
        await conn.execute(
            """
            UPDATE collection_system_settings
            SET fallback_pool_revision_id = $1
            WHERE singleton = 1
            """,
            alternate_pool_id,
        )
        await conn.executemany(
            """
            INSERT INTO channel_collection_settings
                (channel_id, active_pool_revision_id)
            VALUES ($1, $2)
            """,
            [(channel_a, alternate_pool_id), (channel_b, alternate_pool_id)],
        )

        base = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
        # Deliberately shuffled insertion order: processing must be ordered by
        # channel, viewer, check-in date, then id rather than by sequence id.
        inputs = [
            (channel_b, "viewer-z", "z", date(2026, 8, 1), base),
            (channel_a, "viewer-b", "b", date(2026, 8, 2), base + timedelta(days=1)),
            (channel_a, "viewer-a", "a", date(2026, 8, 2), base + timedelta(days=1)),
            (channel_a, "viewer-a", "a", date(2026, 8, 1), base),
            (channel_b, "viewer-a", "a", date(2026, 8, 1), base),
        ]
        await conn.executemany(
            """
            INSERT INTO viewer_checkins
                (channel_id, user_id, username, checkin_date, created_at)
            VALUES ($1, $2, $3, $4, $5)
            """,
            inputs,
        )
        expected = await conn.fetch(
            """
            SELECT id, channel_id, user_id, checkin_date, created_at
            FROM viewer_checkins
            WHERE channel_id = ANY($1::text[])
            ORDER BY channel_id, user_id, checkin_date, id
            """,
            [channel_a, channel_b],
        )

        preview = await backfill_checkin_collections(conn, batch_size=1, dry_run=True)
        assert preview.scanned == len(expected)
        assert preview.inserted == 0
        assert preview.skipped == len(expected)
        assert preview.remaining == len(expected)
        assert preview.failures == 0
        assert (
            await conn.fetchval(
                "SELECT COUNT(*) FROM viewer_card_draws WHERE channel_id = ANY($1::text[])",
                [channel_a, channel_b],
            )
            == 0
        )

        first = await backfill_checkin_collections(conn, batch_size=1)
        assert first.scanned == len(expected)
        assert first.inserted == len(expected)
        assert first.skipped == 0
        assert first.remaining == 0
        assert first.failures == 0

        draws = await conn.fetch(
            """
            SELECT
                draw.id AS draw_id,
                draw.checkin_id,
                draw.channel_id,
                draw.user_id,
                draw.pool_revision_id,
                draw.entropy,
                draw.drawn_at,
                checkin.checkin_date,
                checkin.created_at
            FROM viewer_card_draws AS draw
            JOIN viewer_checkins AS checkin ON checkin.id = draw.checkin_id
            WHERE draw.channel_id = ANY($1::text[])
            ORDER BY draw.id
            """,
            [channel_a, channel_b],
        )
        assert [
            (row["channel_id"], row["user_id"], row["checkin_date"], row["checkin_id"])
            for row in draws
        ] == [
            (row["channel_id"], row["user_id"], row["checkin_date"], row["id"]) for row in expected
        ]
        assert all(row["pool_revision_id"] == official_pool_id for row in draws)
        assert all(row["drawn_at"] == row["created_at"] for row in draws)
        assert all(
            bytes(row["entropy"])
            == derive_backfill_entropy(
                channel_id=row["channel_id"],
                user_id=row["user_id"],
                checkin_date=row["checkin_date"],
                checkin_id=row["checkin_id"],
            )
            for row in draws
        )

        inventory = await conn.fetch(
            """
            SELECT channel_id, user_id, COUNT(*)::INT AS copies
            FROM viewer_card_draws
            WHERE channel_id = ANY($1::text[])
            GROUP BY channel_id, user_id
            ORDER BY channel_id, user_id
            """,
            [channel_a, channel_b],
        )
        checkin_counts = await conn.fetch(
            """
            SELECT channel_id, user_id, COUNT(*)::INT AS copies
            FROM viewer_checkins
            WHERE channel_id = ANY($1::text[])
            GROUP BY channel_id, user_id
            ORDER BY channel_id, user_id
            """,
            [channel_a, channel_b],
        )
        assert [tuple(row) for row in inventory] == [tuple(row) for row in checkin_counts]
        assert (
            await conn.fetchval(
                "SELECT COUNT(*) FROM community_overlay_events WHERE channel_id = ANY($1::text[])",
                [channel_a, channel_b],
            )
            == 0
        )

        rerun = await backfill_checkin_collections(conn, batch_size=2)
        assert rerun.scanned == 0
        assert rerun.inserted == 0
        assert rerun.skipped == 0
        assert rerun.remaining == 0
        assert rerun.failures == 0
    finally:
        await outer.rollback()
        await conn.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_failed_viewer_batch_rolls_back_then_a_rerun_resumes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = await asyncpg.connect(_DATABASE_URL, statement_cache_size=0)
    outer = conn.transaction()
    await outer.start()
    suffix = uuid4().hex
    channel_id = f"backfill-resume-{suffix}"
    failed_user_id = f"viewer-bad-{suffix}"
    successful_user_id = f"viewer-good-{suffix}"
    try:
        await conn.execute(
            "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
            channel_id,
        )
        await conn.executemany(
            """
            INSERT INTO viewer_checkins
                (channel_id, user_id, username, checkin_date, created_at)
            VALUES ($1, $2, $2, $3, $4)
            """,
            [
                (channel_id, failed_user_id, date(2026, 8, 1), datetime(2026, 8, 1, tzinfo=UTC)),
                (channel_id, failed_user_id, date(2026, 8, 2), datetime(2026, 8, 2, tzinfo=UTC)),
                (
                    channel_id,
                    successful_user_id,
                    date(2026, 8, 1),
                    datetime(2026, 8, 1, tzinfo=UTC),
                ),
            ],
        )

        original_insert = CollectionRepository.insert_draw_selection
        failed_user_calls = 0

        async def fail_on_second_row(
            self: CollectionRepository,
            connection: asyncpg.Connection,
            **kwargs: object,
        ) -> bool:
            nonlocal failed_user_calls
            if kwargs["user_id"] == failed_user_id:
                failed_user_calls += 1
                if failed_user_calls == 2:
                    raise RuntimeError("injected viewer-batch failure")
            return await original_insert(self, connection, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(CollectionRepository, "insert_draw_selection", fail_on_second_row)
        partial = await backfill_checkin_collections(conn, batch_size=10)

        assert partial.scanned == 3
        assert partial.inserted == 1
        assert partial.skipped == 0
        assert partial.remaining == 2
        assert partial.failures == 1
        assert (
            await conn.fetchval(
                "SELECT COUNT(*) FROM viewer_card_draws WHERE channel_id = $1 AND user_id = $2",
                channel_id,
                failed_user_id,
            )
            == 0
        )
        assert (
            await conn.fetchval(
                "SELECT COUNT(*) FROM viewer_card_draws WHERE channel_id = $1 AND user_id = $2",
                channel_id,
                successful_user_id,
            )
            == 1
        )

        monkeypatch.setattr(CollectionRepository, "insert_draw_selection", original_insert)
        resumed = await backfill_checkin_collections(conn, batch_size=1)
        assert resumed.scanned == 2
        assert resumed.inserted == 2
        assert resumed.skipped == 0
        assert resumed.remaining == 0
        assert resumed.failures == 0
        assert (
            await conn.fetchval(
                "SELECT COUNT(*) FROM community_overlay_events WHERE channel_id = $1",
                channel_id,
            )
            == 0
        )
    finally:
        await outer.rollback()
        await conn.close()
