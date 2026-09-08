"""PostgreSQL contracts for published collection revisions and draw audit rows."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest

_DATABASE_URL = os.getenv("NIIBOT_TEST_DATABASE_URL")


async def _insert_draft_set(
    conn: asyncpg.Connection,
    *,
    total_cards: int = 1,
) -> tuple[int, int, int]:
    suffix = uuid4().hex
    rarity_id = await conn.fetchval(
        """
        SELECT id
        FROM rarity_definition_revisions
        WHERE rarity_key = 'common' AND revision_number = 1
        """
    )
    set_id = await conn.fetchval(
        """
        INSERT INTO collection_sets
            (set_key, revision_number, display_name, total_cards)
        VALUES ($1, 1, 'Migration contract set', $2)
        RETURNING id
        """,
        f"test-set-{suffix}",
        total_cards,
    )
    card_id = await conn.fetchval(
        """
        INSERT INTO collection_cards
            (set_id, card_key, card_number, rarity_revision_id)
        VALUES ($1, 'first-card', 1, $2)
        RETURNING id
        """,
        set_id,
        rarity_id,
    )
    revision_id = await conn.fetchval(
        """
        INSERT INTO collection_card_revisions
            (card_id, revision_number, display_name)
        VALUES ($1, 1, 'First card')
        RETURNING id
        """,
        card_id,
    )
    return set_id, card_id, revision_id


async def _insert_draft_pool(
    conn: asyncpg.Connection,
    *,
    card_revision_id: int | None = None,
) -> int:
    pool_id = await conn.fetchval(
        """
        INSERT INTO draw_pool_revisions
            (pool_key, revision_number, algorithm_version)
        VALUES ($1, 1, 'weighted-rarity-v1')
        RETURNING id
        """,
        f"test-pool-{uuid4().hex}",
    )
    if card_revision_id is not None:
        rarity_id = await conn.fetchval(
            """
            SELECT card.rarity_revision_id
            FROM collection_card_revisions AS revision
            JOIN collection_cards AS card ON card.id = revision.card_id
            WHERE revision.id = $1
            """,
            card_revision_id,
        )
        await conn.execute(
            """
            INSERT INTO draw_pool_rarity_weights
                (pool_revision_id, rarity_revision_id, weight)
            VALUES ($1, $2, 100)
            """,
            pool_id,
            rarity_id,
        )
        await conn.execute(
            """
            INSERT INTO draw_pool_entries
                (pool_revision_id, card_revision_id, entry_order)
            VALUES ($1, $2, 1)
            """,
            pool_id,
            card_revision_id,
        )
    return pool_id


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_publish_and_settings_reject_incomplete_or_unpublished_revisions() -> None:
    pool = await asyncpg.create_pool(_DATABASE_URL, min_size=1, max_size=1)
    try:
        async with pool.acquire() as conn:
            outer = conn.transaction()
            await outer.start()
            try:
                empty_set_id = await conn.fetchval(
                    """
                    INSERT INTO collection_sets
                        (set_key, revision_number, display_name, total_cards)
                    VALUES ($1, 1, 'Incomplete set', 1)
                    RETURNING id
                    """,
                    f"incomplete-set-{uuid4().hex}",
                )
                with pytest.raises(asyncpg.PostgresError):
                    async with conn.transaction():
                        await conn.execute(
                            "UPDATE collection_sets SET published_at = NOW() WHERE id = $1",
                            empty_set_id,
                        )

                empty_pool_id = await _insert_draft_pool(conn)
                with pytest.raises(asyncpg.PostgresError):
                    async with conn.transaction():
                        await conn.execute(
                            "UPDATE draw_pool_revisions SET published_at = NOW() WHERE id = $1",
                            empty_pool_id,
                        )

                channel_id = f"test-collection-setting-{uuid4().hex}"
                await conn.execute(
                    "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
                    channel_id,
                )
                with pytest.raises(asyncpg.PostgresError):
                    async with conn.transaction():
                        await conn.execute(
                            """
                            INSERT INTO channel_collection_settings
                                (channel_id, active_pool_revision_id)
                            VALUES ($1, $2)
                            """,
                            channel_id,
                            empty_pool_id,
                        )
            finally:
                await outer.rollback()
    finally:
        await pool.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_pool_publish_rejects_inconsistent_membership() -> None:
    pool = await asyncpg.create_pool(_DATABASE_URL, min_size=1, max_size=1)
    try:
        async with pool.acquire() as conn:
            outer = conn.transaction()
            await outer.start()
            try:
                published_revision_id = await conn.fetchval(
                    """
                    SELECT entry.card_revision_id
                    FROM collection_system_settings AS settings
                    JOIN draw_pool_entries AS entry
                      ON entry.pool_revision_id = settings.fallback_pool_revision_id
                    ORDER BY entry.entry_order
                    LIMIT 1
                    """
                )
                assert published_revision_id is not None

                no_weight_pool = await conn.fetchval(
                    """
                    INSERT INTO draw_pool_revisions
                        (pool_key, revision_number, algorithm_version)
                    VALUES ($1, 1, 'weighted-rarity-v1')
                    RETURNING id
                    """,
                    f"no-weight-{uuid4().hex}",
                )
                await conn.execute(
                    """
                    INSERT INTO draw_pool_entries
                        (pool_revision_id, card_revision_id, entry_order)
                    VALUES ($1, $2, 1)
                    """,
                    no_weight_pool,
                    published_revision_id,
                )
                with pytest.raises(asyncpg.PostgresError):
                    async with conn.transaction():
                        await conn.execute(
                            "UPDATE draw_pool_revisions SET published_at = NOW() WHERE id = $1",
                            no_weight_pool,
                        )

                _, _, draft_revision_id = await _insert_draft_set(conn)
                unpublished_set_pool = await _insert_draft_pool(
                    conn,
                    card_revision_id=draft_revision_id,
                )
                with pytest.raises(asyncpg.PostgresError):
                    async with conn.transaction():
                        await conn.execute(
                            "UPDATE draw_pool_revisions SET published_at = NOW() WHERE id = $1",
                            unpublished_set_pool,
                        )

                extra_weight_pool = await _insert_draft_pool(
                    conn,
                    card_revision_id=published_revision_id,
                )
                rare_rarity_id = await conn.fetchval(
                    """
                    SELECT id
                    FROM rarity_definition_revisions
                    WHERE rarity_key = 'rare' AND revision_number = 1
                    """
                )
                await conn.execute(
                    """
                    INSERT INTO draw_pool_rarity_weights
                        (pool_revision_id, rarity_revision_id, weight)
                    VALUES ($1, $2, 1)
                    """,
                    extra_weight_pool,
                    rare_rarity_id,
                )
                with pytest.raises(asyncpg.PostgresError):
                    async with conn.transaction():
                        await conn.execute(
                            "UPDATE draw_pool_revisions SET published_at = NOW() WHERE id = $1",
                            extra_weight_pool,
                        )
            finally:
                await outer.rollback()
    finally:
        await pool.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_set_publish_and_card_insert_are_serialized() -> None:
    """A child insert must wait for an in-flight publish decision."""
    pool = await asyncpg.create_pool(_DATABASE_URL, min_size=2, max_size=2)
    conn1 = await pool.acquire()
    conn2 = await pool.acquire()
    set_id, _, _ = await _insert_draft_set(conn1)
    publish = conn1.transaction()
    await publish.start()
    publish_active = True
    insert_task: asyncio.Task[str] | None = None
    try:
        await conn1.execute(
            "UPDATE collection_sets SET published_at = NOW() WHERE id = $1",
            set_id,
        )

        async def insert_while_publish_is_open() -> str:
            return await conn2.execute(
                """
                INSERT INTO collection_cards
                    (set_id, card_key, card_number, rarity_revision_id)
                SELECT $1, 'late-card', 2, id
                FROM rarity_definition_revisions
                WHERE rarity_key = 'common' AND revision_number = 1
                """,
                set_id,
            )

        insert_task = asyncio.create_task(insert_while_publish_is_open())
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(insert_task), timeout=0.2)

        await publish.commit()
        publish_active = False
        with pytest.raises(asyncpg.PostgresError):
            await insert_task
    finally:
        if publish_active:
            await publish.rollback()
        if insert_task is not None and not insert_task.done():
            insert_task.cancel()
            await asyncio.gather(insert_task, return_exceptions=True)
        await pool.release(conn2)
        await pool.release(conn1)
        await pool.close()


@pytest.mark.parametrize("member_kind", ["weight", "entry"])
@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_pool_publish_and_member_insert_are_serialized(member_kind: str) -> None:
    pool = await asyncpg.create_pool(_DATABASE_URL, min_size=2, max_size=2)
    conn1 = await pool.acquire()
    conn2 = await pool.acquire()
    starter = await conn1.fetchrow(
        """
        SELECT
            common_entry.card_revision_id AS common_revision_id,
            rare_entry.card_revision_id AS rare_revision_id,
            common_card.rarity_revision_id AS common_rarity_id,
            rare_card.rarity_revision_id AS rare_rarity_id
        FROM collection_system_settings AS settings
        JOIN draw_pool_entries AS common_entry
          ON common_entry.pool_revision_id = settings.fallback_pool_revision_id
        JOIN collection_card_revisions AS common_revision
          ON common_revision.id = common_entry.card_revision_id
        JOIN collection_cards AS common_card
          ON common_card.id = common_revision.card_id
        JOIN rarity_definition_revisions AS common_rarity
          ON common_rarity.id = common_card.rarity_revision_id
         AND common_rarity.rarity_key = 'common'
        JOIN draw_pool_entries AS rare_entry
          ON rare_entry.pool_revision_id = settings.fallback_pool_revision_id
        JOIN collection_card_revisions AS rare_revision
          ON rare_revision.id = rare_entry.card_revision_id
        JOIN collection_cards AS rare_card
          ON rare_card.id = rare_revision.card_id
        JOIN rarity_definition_revisions AS rare_rarity
          ON rare_rarity.id = rare_card.rarity_revision_id
         AND rare_rarity.rarity_key = 'rare'
        LIMIT 1
        """
    )
    assert starter is not None
    pool_id = await _insert_draft_pool(
        conn1,
        card_revision_id=starter["common_revision_id"],
    )
    publish = conn1.transaction()
    await publish.start()
    publish_active = True
    insert_task: asyncio.Task[str] | None = None
    try:
        await conn1.execute(
            "UPDATE draw_pool_revisions SET published_at = NOW() WHERE id = $1",
            pool_id,
        )

        async def insert_while_publish_is_open() -> str:
            if member_kind == "weight":
                return await conn2.execute(
                    """
                    INSERT INTO draw_pool_rarity_weights
                        (pool_revision_id, rarity_revision_id, weight)
                    VALUES ($1, $2, 1)
                    """,
                    pool_id,
                    starter["rare_rarity_id"],
                )
            return await conn2.execute(
                """
                INSERT INTO draw_pool_entries
                    (pool_revision_id, card_revision_id, entry_order)
                VALUES ($1, $2, 2)
                """,
                pool_id,
                starter["rare_revision_id"],
            )

        insert_task = asyncio.create_task(insert_while_publish_is_open())
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(insert_task), timeout=0.2)

        await publish.commit()
        publish_active = False
        with pytest.raises(asyncpg.PostgresError):
            await insert_task
    finally:
        if publish_active:
            await publish.rollback()
        if insert_task is not None and not insert_task.done():
            insert_task.cancel()
            await asyncio.gather(insert_task, return_exceptions=True)
        await pool.release(conn2)
        await pool.release(conn1)
        await pool.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_draw_audit_bounds_identity_and_channel_teardown_contract() -> None:
    pool = await asyncpg.create_pool(_DATABASE_URL, min_size=1, max_size=1)
    channel_id = f"test-draw-ledger-{uuid4().hex}"
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
                channel_id,
            )
            checkin_id = await conn.fetchval(
                """
                INSERT INTO viewer_checkins
                    (channel_id, user_id, username, checkin_date)
                VALUES ($1, 'viewer-1', 'viewer', CURRENT_DATE)
                RETURNING id
                """,
                channel_id,
            )
            pool_row = await conn.fetchrow(
                """
                SELECT pool.id AS pool_id, entry.card_revision_id
                FROM collection_system_settings AS settings
                JOIN draw_pool_revisions AS pool
                  ON pool.id = settings.fallback_pool_revision_id
                JOIN draw_pool_entries AS entry ON entry.pool_revision_id = pool.id
                ORDER BY entry.entry_order
                LIMIT 1
                """
            )
            assert pool_row is not None

            draw_args = (
                channel_id,
                checkin_id,
                pool_row["pool_id"],
                pool_row["card_revision_id"],
            )
            insert_sql = """
                INSERT INTO viewer_card_draws (
                    channel_id, user_id, checkin_id, pool_revision_id,
                    card_revision_id, algorithm_version, entropy,
                    rarity_roll, rarity_weight_total, card_roll, card_bucket_size
                )
                VALUES ($1, 'viewer-1', $2, $3, $4, $5,
                        decode('00112233445566778899aabbccddeeff', 'hex'),
                        $6, 100, $7, 5)
            """

            for algorithm, rarity_roll, card_roll in (
                ("different-algorithm", 0, 0),
                ("weighted-rarity-v1", 100, 0),
                ("weighted-rarity-v1", 0, 5),
            ):
                with pytest.raises(asyncpg.PostgresError):
                    async with conn.transaction():
                        await conn.execute(
                            insert_sql,
                            *draw_args,
                            algorithm,
                            rarity_roll,
                            card_roll,
                        )

            await conn.execute(
                insert_sql,
                *draw_args,
                "weighted-rarity-v1",
                0,
                0,
            )
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                async with conn.transaction():
                    await conn.execute(
                        "DELETE FROM viewer_checkins WHERE id = $1",
                        checkin_id,
                    )

            await conn.execute("DELETE FROM channels WHERE channel_id = $1", channel_id)
            assert (
                await conn.fetchval(
                    "SELECT COUNT(*) FROM viewer_card_draws WHERE channel_id = $1",
                    channel_id,
                )
                == 0
            )
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM channels WHERE channel_id = $1", channel_id)
        await pool.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_draw_rejects_an_unpublished_pool() -> None:
    pool = await asyncpg.create_pool(_DATABASE_URL, min_size=1, max_size=1)
    try:
        async with pool.acquire() as conn:
            outer = conn.transaction()
            await outer.start()
            try:
                channel_id = f"test-unpublished-draw-{uuid4().hex}"
                await conn.execute(
                    "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
                    channel_id,
                )
                checkin_id = await conn.fetchval(
                    """
                    INSERT INTO viewer_checkins
                        (channel_id, user_id, username, checkin_date)
                    VALUES ($1, 'viewer-1', 'viewer', CURRENT_DATE)
                    RETURNING id
                    """,
                    channel_id,
                )
                card_revision_id = await conn.fetchval(
                    """
                    SELECT entry.card_revision_id
                    FROM collection_system_settings AS settings
                    JOIN draw_pool_entries AS entry
                      ON entry.pool_revision_id = settings.fallback_pool_revision_id
                    ORDER BY entry.entry_order
                    LIMIT 1
                    """
                )
                draft_pool_id = await _insert_draft_pool(
                    conn,
                    card_revision_id=card_revision_id,
                )
                with pytest.raises(asyncpg.PostgresError):
                    async with conn.transaction():
                        await conn.execute(
                            """
                            INSERT INTO viewer_card_draws (
                                channel_id, user_id, checkin_id, pool_revision_id,
                                card_revision_id, algorithm_version, entropy,
                                rarity_roll, rarity_weight_total, card_roll, card_bucket_size
                            )
                            VALUES ($1, 'viewer-1', $2, $3, $4, 'weighted-rarity-v1',
                                    decode('00112233445566778899aabbccddeeff', 'hex'),
                                    0, 100, 0, 1)
                            """,
                            channel_id,
                            checkin_id,
                            draft_pool_id,
                            card_revision_id,
                        )
            finally:
                await outer.rollback()
    finally:
        await pool.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_pool_rejects_two_revisions_of_the_same_logical_card() -> None:
    pool = await asyncpg.create_pool(_DATABASE_URL, min_size=1, max_size=1)
    try:
        async with pool.acquire() as conn:
            outer = conn.transaction()
            await outer.start()
            try:
                card = await conn.fetchrow(
                    """
                    SELECT card.id, card.rarity_revision_id, revision.id AS revision_id
                    FROM collection_system_settings AS settings
                    JOIN draw_pool_entries AS entry
                      ON entry.pool_revision_id = settings.fallback_pool_revision_id
                    JOIN collection_card_revisions AS revision
                      ON revision.id = entry.card_revision_id
                    JOIN collection_cards AS card ON card.id = revision.card_id
                    ORDER BY entry.entry_order
                    LIMIT 1
                    """
                )
                assert card is not None
                second_revision_id = await conn.fetchval(
                    """
                    INSERT INTO collection_card_revisions
                        (card_id, revision_number, display_name)
                    VALUES ($1, 2, 'Second visual revision')
                    RETURNING id
                    """,
                    card["id"],
                )
                pool_id = await conn.fetchval(
                    """
                    INSERT INTO draw_pool_revisions
                        (pool_key, revision_number, algorithm_version)
                    VALUES ($1, 1, 'weighted-rarity-v1')
                    RETURNING id
                    """,
                    f"duplicate-logical-card-{uuid4().hex}",
                )
                await conn.execute(
                    """
                    INSERT INTO draw_pool_rarity_weights
                        (pool_revision_id, rarity_revision_id, weight)
                    VALUES ($1, $2, 100)
                    """,
                    pool_id,
                    card["rarity_revision_id"],
                )
                with pytest.raises(asyncpg.UniqueViolationError):
                    await conn.execute(
                        """
                        INSERT INTO draw_pool_entries
                            (pool_revision_id, card_revision_id, entry_order)
                        VALUES ($1, $2, 1), ($1, $3, 2)
                        """,
                        pool_id,
                        card["revision_id"],
                        second_revision_id,
                    )
            finally:
                await outer.rollback()
    finally:
        await pool.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_official_seed_is_a_complete_unique_fallback_pool() -> None:
    conn = await asyncpg.connect(_DATABASE_URL)
    try:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS entry_count,
                COUNT(DISTINCT card.id) AS card_count,
                COUNT(DISTINCT revision.id) AS revision_count,
                COUNT(*) FILTER (WHERE rarity.rarity_key = 'common') AS common_count,
                COUNT(*) FILTER (WHERE rarity.rarity_key = 'rare') AS rare_count,
                COUNT(*) FILTER (WHERE rarity.rarity_key = 'legendary') AS legendary_count,
                MIN(pool.published_at) IS NOT NULL AS is_published
            FROM collection_system_settings AS settings
            JOIN draw_pool_revisions AS pool
              ON pool.id = settings.fallback_pool_revision_id
            JOIN draw_pool_entries AS entry ON entry.pool_revision_id = pool.id
            JOIN collection_card_revisions AS revision
              ON revision.id = entry.card_revision_id
            JOIN collection_cards AS card ON card.id = revision.card_id
            JOIN rarity_definition_revisions AS rarity
              ON rarity.id = card.rarity_revision_id
            """
        )
        assert row is not None
        assert dict(row) == {
            "entry_count": 9,
            "card_count": 9,
            "revision_count": 9,
            "common_count": 5,
            "rare_count": 3,
            "legendary_count": 1,
            "is_published": True,
        }
        weights = await conn.fetch(
            """
            SELECT rarity.rarity_key, weight.weight
            FROM collection_system_settings AS settings
            JOIN draw_pool_rarity_weights AS weight
              ON weight.pool_revision_id = settings.fallback_pool_revision_id
            JOIN rarity_definition_revisions AS rarity
              ON rarity.id = weight.rarity_revision_id
            ORDER BY rarity.sort_rank
            """
        )
        assert [(row["rarity_key"], row["weight"]) for row in weights] == [
            ("common", 70),
            ("rare", 25),
            ("legendary", 5),
        ]
        assert await conn.fetchval("SELECT COUNT(*) FROM collection_system_settings") == 1
    finally:
        await conn.close()
