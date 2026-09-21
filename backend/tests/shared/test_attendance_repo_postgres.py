"""PostgreSQL integration contract for the daily check-in leaderboard and rank lookup."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from shared.models.attendance import CheckinStatus
from shared.repositories.attendance import AttendanceRepository
from shared.repositories.collection import CollectionRepository

_DATABASE_URL = os.getenv("NIIBOT_TEST_DATABASE_URL")


async def _register_json_codecs(conn: asyncpg.Connection) -> None:
    for type_name in ("jsonb", "json"):
        await conn.set_type_codec(
            type_name,
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )


async def _create_pool(*, max_size: int) -> asyncpg.Pool:
    assert _DATABASE_URL is not None
    return await asyncpg.create_pool(
        _DATABASE_URL,
        min_size=1,
        max_size=max_size,
        init=_register_json_codecs,
    )


def _decode_jsonb(value: object) -> dict[str, object]:
    if isinstance(value, str):
        decoded = json.loads(value)
        assert isinstance(decoded, dict)
        return decoded
    assert isinstance(value, dict)
    return value


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_checkin_draw_and_overlay_event_commit_as_one_fact() -> None:
    pool = await _create_pool(max_size=2)
    channel_id = f"test-collection-checkin-{uuid4().hex}"
    occurred_at = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    repository = AttendanceRepository(
        pool,
        collection_repository=CollectionRepository(entropy_source=lambda _: bytes(16)),
    )
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
                channel_id,
            )

        first, second = await asyncio.gather(
            *(
                repository.record_checkin(
                    channel_id=channel_id,
                    user_id="viewer-1",
                    username="viewer",
                    display_name="Viewer One",
                    checkin_date=occurred_at.date(),
                    occurred_at=occurred_at,
                )
                for _ in range(2)
            )
        )
        recorded = first if first.status is CheckinStatus.RECORDED else second
        duplicate = second if recorded is first else first

        assert recorded.collection is not None
        assert recorded.collection.copy_count == 1
        assert recorded.collection.is_new is True
        assert duplicate.status is CheckinStatus.ALREADY_CHECKED_IN
        assert duplicate.collection is None
        assert duplicate.event_id is None

        async with pool.acquire() as conn:
            counts = await conn.fetchrow(
                """
                SELECT
                    (SELECT COUNT(*) FROM viewer_checkins WHERE channel_id = $1) AS checkins,
                    (SELECT COUNT(*) FROM viewer_card_draws WHERE channel_id = $1) AS draws,
                    (SELECT COUNT(*) FROM community_overlay_events WHERE channel_id = $1) AS events
                """,
                channel_id,
            )
            event = await conn.fetchrow(
                """
                SELECT schema_version, payload
                FROM community_overlay_events
                WHERE channel_id = $1
                """,
                channel_id,
            )
        assert counts is not None
        assert tuple(counts) == (1, 1, 1)
        assert event is not None
        assert event["schema_version"] == 1
        payload = _decode_jsonb(event["payload"])
        collection = payload["collection"]
        assert isinstance(collection, dict)
        assert collection["draw_id"] == recorded.collection.id
        assert collection["copy_count"] == 1
        assert collection["is_new"] is True
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM channels WHERE channel_id = $1", channel_id)
        await pool.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_concurrent_viewers_receive_distinct_stable_daily_order() -> None:
    pool = await _create_pool(max_size=3)
    channel_id = f"test-checkin-order-{uuid4().hex}"
    occurred_at = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    repository = AttendanceRepository(pool)
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
                channel_id,
            )

        first, second = await asyncio.gather(
            repository.record_checkin(
                channel_id=channel_id,
                user_id="viewer-1",
                username="viewer1",
                display_name="Viewer One",
                checkin_date=occurred_at.date(),
                occurred_at=occurred_at,
            ),
            repository.record_checkin(
                channel_id=channel_id,
                user_id="viewer-2",
                username="viewer2",
                display_name="Viewer Two",
                checkin_date=occurred_at.date(),
                occurred_at=occurred_at,
            ),
        )

        assert {first.today_order, second.today_order} == {1, 2}
        by_user = {first.user_id: first, second.user_id: second}

        duplicate = await repository.record_checkin(
            channel_id=channel_id,
            user_id="viewer-1",
            username="viewer1",
            display_name="Viewer One",
            checkin_date=occurred_at.date(),
            occurred_at=occurred_at,
        )

        assert duplicate.status is CheckinStatus.ALREADY_CHECKED_IN
        assert duplicate.today_order == by_user["viewer-1"].today_order
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM channels WHERE channel_id = $1", channel_id)
        await pool.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_collection_failure_rolls_back_the_enclosing_checkin_transaction() -> None:
    pool = await _create_pool(max_size=1)
    channel_id = f"test-collection-rollback-{uuid4().hex}"
    occurred_at = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    repository = AttendanceRepository(
        pool,
        collection_repository=CollectionRepository(entropy_source=lambda _: b"invalid"),
    )
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
                channel_id,
            )

        with pytest.raises(RuntimeError, match="entropy source"):
            await repository.record_checkin(
                channel_id=channel_id,
                user_id="viewer-1",
                username="viewer",
                display_name=None,
                checkin_date=occurred_at.date(),
                occurred_at=occurred_at,
            )

        async with pool.acquire() as conn:
            counts = await conn.fetchrow(
                """
                SELECT
                    (SELECT COUNT(*) FROM viewer_checkins WHERE channel_id = $1) AS checkins,
                    (SELECT COUNT(*) FROM viewer_card_draws WHERE channel_id = $1) AS draws,
                    (SELECT COUNT(*) FROM community_overlay_events WHERE channel_id = $1) AS events
                """,
                channel_id,
            )
        assert counts is not None
        assert tuple(counts) == (0, 0, 0)
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM channels WHERE channel_id = $1", channel_id)
        await pool.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_leaderboard_aggregates_and_ranks_inside_one_tenant() -> None:
    pool = await _create_pool(max_size=2)
    suffix = uuid4().hex
    channel_id = f"test-leaderboard-a-{suffix}"
    other_channel_id = f"test-leaderboard-b-{suffix}"
    latest_day = date(2026, 8, 31)

    try:
        async with pool.acquire() as conn:
            await conn.executemany(
                "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $2)",
                [(channel_id, channel_id), (other_channel_id, other_channel_id)],
            )

            rows: list[tuple[str, str, str, str | None, date]] = []
            for offset in range(3):
                checkin_day = latest_day - timedelta(days=2 - offset)
                rows.append(
                    (
                        channel_id,
                        "alice-id",
                        "alice",
                        "Alice New" if checkin_day == latest_day else "Alice Old",
                        checkin_day,
                    )
                )
                rows.append((channel_id, "bob-id", "bob", "Bob", checkin_day))

            rows.extend(
                (
                    channel_id,
                    f"viewer-{index:03d}",
                    f"viewer{index:03d}",
                    None,
                    latest_day - timedelta(days=1),
                )
                for index in range(102)
            )
            rows.extend(
                (
                    other_channel_id,
                    "other-viewer",
                    "other",
                    "Other Tenant Leader",
                    latest_day - timedelta(days=offset),
                )
                for offset in range(10)
            )
            rows.extend(
                (
                    other_channel_id,
                    "alice-id",
                    "alice",
                    "Alice In Other Channel",
                    latest_day - timedelta(days=offset),
                )
                for offset in range(10)
            )
            await conn.executemany(
                """
                INSERT INTO viewer_checkins
                    (channel_id, user_id, username, display_name, checkin_date)
                VALUES ($1, $2, $3, $4, $5)
                """,
                rows,
            )

        leaderboard = await AttendanceRepository(pool).list_leaderboard(channel_id)

        assert len(leaderboard) == 100
        assert [entry.rank for entry in leaderboard] == list(range(1, 101))
        assert [entry.user_id for entry in leaderboard[:2]] == ["alice-id", "bob-id"]
        assert leaderboard[0].display_name == "Alice New"
        assert [entry.total_days for entry in leaderboard[:2]] == [3, 3]
        assert all(entry.user_id != "other-viewer" for entry in leaderboard)
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM channels WHERE channel_id = ANY($1::text[])",
                [channel_id, other_channel_id],
            )
        await pool.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_get_checkin_rank_matches_leaderboard_ordering_past_the_limit() -> None:
    """A viewer's chat-facing !rank must never drift from the dashboard leaderboard."""
    pool = await _create_pool(max_size=2)
    suffix = uuid4().hex
    channel_id = f"test-rank-a-{suffix}"
    other_channel_id = f"test-rank-b-{suffix}"
    latest_day = date(2026, 8, 31)

    try:
        async with pool.acquire() as conn:
            await conn.executemany(
                "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $2)",
                [(channel_id, channel_id), (other_channel_id, other_channel_id)],
            )

            rows: list[tuple[str, str, str, str | None, date]] = []
            for offset in range(3):
                checkin_day = latest_day - timedelta(days=2 - offset)
                rows.append((channel_id, "alice-id", "alice", "Alice New", checkin_day))
                rows.append((channel_id, "bob-id", "bob", "Bob", checkin_day))
            # 102 single-day check-ins push bob-id/alice-id to the top and leave 102
            # viewers below them, so the highest-indexed ones fall past list_leaderboard's
            # LIMIT 100 — exactly the case get_checkin_rank exists to cover.
            rows.extend(
                (
                    channel_id,
                    f"viewer-{index:03d}",
                    f"viewer{index:03d}",
                    None,
                    latest_day - timedelta(days=1),
                )
                for index in range(102)
            )
            rows.append(
                (other_channel_id, "alice-id", "alice", "Alice In Other Channel", latest_day)
            )
            await conn.executemany(
                """
                INSERT INTO viewer_checkins
                    (channel_id, user_id, username, display_name, checkin_date)
                VALUES ($1, $2, $3, $4, $5)
                """,
                rows,
            )

        repo = AttendanceRepository(pool)
        leaderboard = await repo.list_leaderboard(channel_id)
        leaderboard_ranks = {entry.user_id: entry.rank for entry in leaderboard}

        alice_rank = await repo.get_checkin_rank(channel_id, "alice-id")
        assert alice_rank is not None
        assert alice_rank.rank == leaderboard_ranks["alice-id"] == 1
        assert alice_rank.total_days == 3
        assert alice_rank.total_participants == 104

        # viewer-101 sorts last among the 102 tied single-day check-ins, so it lands
        # past list_leaderboard's LIMIT 100 and is absent from `leaderboard`.
        beyond_limit_rank = await repo.get_checkin_rank(channel_id, "viewer-101")
        assert beyond_limit_rank is not None
        assert "viewer-101" not in leaderboard_ranks
        assert beyond_limit_rank.rank == 104
        assert beyond_limit_rank.total_participants == 104

        # Cross-tenant isolation: same user_id, unrelated channel, independent rank.
        other_rank = await repo.get_checkin_rank(other_channel_id, "alice-id")
        assert other_rank is not None
        assert other_rank.rank == 1
        assert other_rank.total_participants == 1

        assert await repo.get_checkin_rank(channel_id, "nobody") is None
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM channels WHERE channel_id = ANY($1::text[])",
                [channel_id, other_channel_id],
            )
        await pool.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_record_checkin_draws_once_and_embeds_the_immutable_event_snapshot() -> None:
    """Exercise the real pool loader, draw insert, aggregate, and event SQL together."""
    pool = await _create_pool(max_size=2)
    suffix = uuid4().hex
    channel_id = f"test-checkin-collection-{suffix}"
    occurred_at = datetime(2026, 9, 8, 8, 0, tzinfo=UTC)

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
                channel_id,
            )

        repository = AttendanceRepository(pool)
        first = await repository.record_checkin(
            channel_id=channel_id,
            user_id="viewer-1",
            username="viewer",
            display_name="Viewer",
            checkin_date=occurred_at.date(),
            occurred_at=occurred_at,
        )
        duplicate = await repository.record_checkin(
            channel_id=channel_id,
            user_id="viewer-1",
            username="viewer",
            display_name="Viewer",
            checkin_date=occurred_at.date(),
            occurred_at=occurred_at,
        )

        assert first.recorded is True
        assert first.collection is not None
        assert first.collection.selection.algorithm_version == "weighted-rarity-v1"
        assert len(first.collection.selection.entropy) == 16
        assert first.collection.copy_count == 1
        assert first.collection.progress.owned_copies == 1
        assert duplicate.recorded is False
        assert duplicate.collection is None
        assert duplicate.event_id is None

        async with pool.acquire() as conn:
            draw_count = await conn.fetchval(
                "SELECT COUNT(*) FROM viewer_card_draws WHERE channel_id = $1",
                channel_id,
            )
            events = await conn.fetch(
                """
                SELECT payload
                FROM community_overlay_events
                WHERE channel_id = $1 AND event_type = 'checkin.recorded'
                """,
                channel_id,
            )
        assert draw_count == 1
        assert len(events) == 1
        assert events[0]["payload"]["collection"] == first.collection.to_event_snapshot()
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM channels WHERE channel_id = $1", channel_id)
        await pool.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_carryover_bridges_lifetime_total_and_next_day_streak_without_fake_history() -> None:
    pool = await _create_pool(max_size=2)
    channel_id = f"test-checkin-carryover-{uuid4().hex}"
    actor_id = uuid4()
    source_day = date(2026, 9, 10)
    next_day_at = datetime(2026, 9, 11, 8, 0, tzinfo=UTC)
    repository = AttendanceRepository(pool)
    try:
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO users (id) VALUES ($1)", actor_id)
            await conn.execute(
                "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)", channel_id
            )
            batch_id = await conn.fetchval(
                """
                INSERT INTO checkin_import_batches
                    (channel_id, source, source_format, source_timezone, through_date,
                     content_sha256, idempotency_key, applied_by_user_id,
                     selected_rows, imported_rows)
                VALUES ($1, 'chiwabots', 'csv', 'Asia/Taipei', $2,
                        $3, $4, $5, 1, 1)
                RETURNING id
                """,
                channel_id,
                source_day,
                "a" * 64,
                "b" * 64,
                actor_id,
            )
            await conn.execute(
                """
                INSERT INTO viewer_checkin_carryovers
                    (channel_id, user_id, import_batch_id, source_username,
                     source_display_name, carried_total_days, last_source_date,
                     source_current_streak, source_daily_order)
                VALUES ($1, 'viewer-1', $2, 'viewer', 'Viewer', 15, $3, 3, 5)
                """,
                channel_id,
                batch_id,
                source_day,
            )
            await conn.execute(
                """
                INSERT INTO viewer_daily_checkin_streaks
                    (channel_id, user_id, current_streak, last_checkin_date)
                VALUES ($1, 'viewer-1', 3, $2)
                """,
                channel_id,
                source_day,
            )

        before = await repository.list_leaderboard(channel_id)
        duplicate = await repository.record_checkin(
            channel_id=channel_id,
            user_id="viewer-1",
            username="viewer",
            display_name="Viewer",
            checkin_date=source_day,
            occurred_at=datetime(2026, 9, 10, 8, 0, tzinfo=UTC),
        )
        recorded = await repository.record_checkin(
            channel_id=channel_id,
            user_id="viewer-1",
            username="viewer",
            display_name="Viewer",
            checkin_date=next_day_at.date(),
            occurred_at=next_day_at,
        )

        assert [(entry.user_id, entry.total_days) for entry in before] == [("viewer-1", 15)]
        assert duplicate.status is CheckinStatus.ALREADY_CHECKED_IN
        assert duplicate.checkin_id is None
        assert duplicate.current_streak == 3
        assert recorded.total_days == 16
        assert recorded.current_streak == 4
        assert recorded.collection is not None

        async with pool.acquire() as conn:
            counts = await conn.fetchrow(
                """
                SELECT
                    (SELECT COUNT(*) FROM viewer_checkins WHERE channel_id = $1) AS checkins,
                    (SELECT COUNT(*) FROM viewer_card_draws WHERE channel_id = $1) AS draws,
                    (SELECT COUNT(*) FROM community_overlay_events WHERE channel_id = $1) AS events
                """,
                channel_id,
            )
        assert counts is not None
        assert tuple(counts) == (1, 1, 1)
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM channels WHERE channel_id = $1", channel_id)
            await conn.execute("DELETE FROM users WHERE id = $1", actor_id)
        await pool.close()


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_export_then_bounded_resets_preserve_settings_and_real_data_until_full_clear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "api"))
    from services.checkin_data_service import CheckinClearScope, CheckinDataService

    pool = await _create_pool(max_size=2)
    channel_id = f"test-checkin-data-reset-{uuid4().hex}"
    actor_id = uuid4()
    source_day = date(2026, 9, 10)
    next_day_at = datetime(2026, 9, 11, 8, 0, tzinfo=UTC)
    repository = AttendanceRepository(pool)
    data = CheckinDataService(pool)
    try:
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO users (id) VALUES ($1)", actor_id)
            await conn.execute(
                "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)", channel_id
            )
            await conn.execute("INSERT INTO checkin_settings (channel_id) VALUES ($1)", channel_id)
            batch_id = await conn.fetchval(
                """
                INSERT INTO checkin_import_batches
                    (channel_id, source, source_format, source_timezone, through_date,
                     content_sha256, idempotency_key, applied_by_user_id,
                     selected_rows, imported_rows)
                VALUES ($1, 'chiwabots', 'csv', 'Asia/Taipei', $2,
                        $3, $4, $5, 1, 1)
                RETURNING id
                """,
                channel_id,
                source_day,
                "c" * 64,
                "d" * 64,
                actor_id,
            )
            await conn.execute(
                """
                INSERT INTO viewer_checkin_carryovers
                    (channel_id, user_id, import_batch_id, source_username,
                     source_display_name, carried_total_days, last_source_date,
                     source_current_streak, source_daily_order)
                VALUES ($1, 'viewer-1', $2, 'viewer', 'Viewer', 15, $3, 3, 5)
                """,
                channel_id,
                batch_id,
                source_day,
            )
            await conn.execute(
                """
                INSERT INTO viewer_daily_checkin_streaks
                    (channel_id, user_id, current_streak, last_checkin_date)
                VALUES ($1, 'viewer-1', 3, $2)
                """,
                channel_id,
                source_day,
            )

        await repository.record_checkin(
            channel_id=channel_id,
            user_id="viewer-1",
            username="viewer",
            display_name="Viewer",
            checkin_date=next_day_at.date(),
            occurred_at=next_day_at,
        )

        rows = await data.list_export_rows(channel_id)
        assert len(rows) == 1
        assert rows[0].total_days == 16
        assert rows[0].last_checkin_date == next_day_at.date()
        assert rows[0].current_streak == 4
        assert rows[0].daily_order == 1

        imported_result = await data.clear(
            channel_id=channel_id,
            actor_user_id=str(actor_id),
            scope=CheckinClearScope.IMPORTED,
        )
        assert imported_result.imported_days == 15

        async with pool.acquire() as conn:
            after_imported = await conn.fetchrow(
                """
                SELECT
                    (SELECT COUNT(*) FROM viewer_checkins WHERE channel_id = $1) AS checkins,
                    (SELECT COUNT(*) FROM viewer_card_draws WHERE channel_id = $1) AS draws,
                    (SELECT COUNT(*) FROM viewer_checkin_carryovers WHERE channel_id = $1) AS carryovers,
                    (SELECT COUNT(*) FROM checkin_import_batches WHERE channel_id = $1) AS batches,
                    (SELECT current_streak FROM viewer_daily_checkin_streaks
                      WHERE channel_id = $1 AND user_id = 'viewer-1') AS streak
                """,
                channel_id,
            )
        assert after_imported is not None
        assert tuple(after_imported) == (1, 1, 0, 0, 1)

        async with pool.acquire() as conn:
            with pytest.raises(asyncpg.RaiseError, match="viewer card draws are immutable"):
                await conn.execute(
                    "DELETE FROM viewer_card_draws WHERE channel_id = $1",
                    channel_id,
                )

        await data.clear(
            channel_id=channel_id,
            actor_user_id=str(actor_id),
            scope=CheckinClearScope.ALL,
        )
        async with pool.acquire() as conn:
            after_all = await conn.fetchrow(
                """
                SELECT
                    (SELECT COUNT(*) FROM viewer_checkins WHERE channel_id = $1) AS checkins,
                    (SELECT COUNT(*) FROM viewer_card_draws WHERE channel_id = $1) AS draws,
                    (SELECT COUNT(*) FROM community_overlay_events
                      WHERE channel_id = $1 AND event_type = 'checkin.recorded') AS events,
                    (SELECT COUNT(*) FROM viewer_daily_checkin_streaks
                      WHERE channel_id = $1) AS streaks,
                    (SELECT COUNT(*) FROM checkin_settings WHERE channel_id = $1) AS settings,
                    (SELECT COUNT(*) FROM tenant_audit_events
                      WHERE channel_id = $1 AND event_type = 'checkin.data_cleared') AS audits
                """,
                channel_id,
            )
        assert after_all is not None
        assert tuple(after_all) == (0, 0, 0, 0, 1, 2)
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM channels WHERE channel_id = $1", channel_id)
            await conn.execute("DELETE FROM users WHERE id = $1", actor_id)
        await pool.close()
