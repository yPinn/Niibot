"""PostgreSQL integration contract for the daily check-in leaderboard and rank lookup."""

from __future__ import annotations

import os
from datetime import date, timedelta
from uuid import uuid4

import asyncpg
import pytest

from shared.repositories.attendance import AttendanceRepository

_DATABASE_URL = os.getenv("NIIBOT_TEST_DATABASE_URL")


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_leaderboard_aggregates_and_ranks_inside_one_tenant() -> None:
    pool = await asyncpg.create_pool(_DATABASE_URL, min_size=1, max_size=2)
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
    pool = await asyncpg.create_pool(_DATABASE_URL, min_size=1, max_size=2)
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
