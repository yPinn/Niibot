"""PostgreSQL integration contract for the daily check-in leaderboard."""

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
