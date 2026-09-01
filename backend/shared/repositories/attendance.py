"""Persistence for channel-scoped daily check-ins."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import asyncpg

from shared.community_events import CHECKIN_RECORDED, validate_community_event
from shared.models.attendance import (
    CheckinLeaderboardEntry,
    CheckinResult,
    CheckinSettings,
    CheckinStatus,
)

_CHECKIN_COLUMNS = (
    "id, channel_id, user_id, username, display_name, checkin_date, session_id, created_at"
)
_SETTINGS_COLUMNS = (
    "channel_id, timezone, success_template, duplicate_template, created_at, updated_at"
)


class AttendanceRepository:
    """Atomic check-in ledger and its successful overlay projection."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_or_create_settings(self, channel_id: str) -> CheckinSettings:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO checkin_settings (channel_id) VALUES ($1) "
                    "ON CONFLICT (channel_id) DO NOTHING",
                    channel_id,
                )
                row = await conn.fetchrow(
                    f"SELECT {_SETTINGS_COLUMNS} FROM checkin_settings WHERE channel_id = $1",
                    channel_id,
                )
        if row is None:
            raise RuntimeError(f"Failed to load check-in settings for channel {channel_id}")
        return CheckinSettings(**dict(row))

    async def update_settings(
        self,
        *,
        channel_id: str,
        timezone: str,
        success_template: str,
        duplicate_template: str,
    ) -> CheckinSettings:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO checkin_settings
                    (channel_id, timezone, success_template, duplicate_template)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (channel_id) DO UPDATE SET
                    timezone = EXCLUDED.timezone,
                    success_template = EXCLUDED.success_template,
                    duplicate_template = EXCLUDED.duplicate_template,
                    updated_at = NOW()
                RETURNING {_SETTINGS_COLUMNS}
                """,
                channel_id,
                timezone,
                success_template,
                duplicate_template,
            )
        if row is None:
            raise RuntimeError(f"Failed to update check-in settings for channel {channel_id}")
        return CheckinSettings(**dict(row))

    async def list_leaderboard(
        self, channel_id: str, *, limit: int = 100
    ) -> tuple[CheckinLeaderboardEntry, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH ranked_checkins AS (
                    SELECT
                        user_id,
                        username,
                        display_name,
                        checkin_date,
                        COUNT(*) OVER (PARTITION BY user_id) AS total_days,
                        ROW_NUMBER() OVER (
                            PARTITION BY user_id
                            ORDER BY checkin_date DESC, id DESC
                        ) AS recent_row
                    FROM viewer_checkins
                    WHERE channel_id = $1
                ), viewer_totals AS (
                    SELECT
                        user_id,
                        username,
                        display_name,
                        total_days,
                        checkin_date AS last_checkin_date
                    FROM ranked_checkins
                    WHERE recent_row = 1
                )
                SELECT
                    ROW_NUMBER() OVER (
                        ORDER BY
                            total_days DESC,
                            last_checkin_date DESC,
                            LOWER(COALESCE(display_name, username)),
                            user_id
                    ) AS rank,
                    user_id,
                    username,
                    display_name,
                    total_days,
                    last_checkin_date
                FROM viewer_totals
                ORDER BY rank
                LIMIT $2
                """,
                channel_id,
                limit,
            )
        return tuple(CheckinLeaderboardEntry(**dict(row)) for row in rows)

    async def record_checkin(
        self,
        *,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        checkin_date: date,
        occurred_at: datetime,
        session_id: int | None = None,
        event_expires_at: datetime | None = None,
    ) -> CheckinResult:
        """Insert once per local day and emit its overlay event in one transaction."""
        expires_at = event_expires_at or occurred_at + timedelta(minutes=10)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if session_id is not None:
                    valid_session = await conn.fetchval(
                        "SELECT EXISTS (SELECT 1 FROM stream_sessions "
                        "WHERE id = $1 AND channel_id = $2)",
                        session_id,
                        channel_id,
                    )
                    if not valid_session:
                        raise ValueError(
                            f"Session {session_id} does not belong to channel {channel_id}"
                        )
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO viewer_checkins
                        (channel_id, user_id, username, display_name, checkin_date,
                         session_id, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (channel_id, user_id, checkin_date) DO NOTHING
                    RETURNING {_CHECKIN_COLUMNS}
                    """,
                    channel_id,
                    user_id,
                    username,
                    display_name,
                    checkin_date,
                    session_id,
                    occurred_at,
                )
                recorded = row is not None
                if row is None:
                    row = await conn.fetchrow(
                        f"""
                        SELECT {_CHECKIN_COLUMNS}
                        FROM viewer_checkins
                        WHERE channel_id = $1
                          AND user_id = $2
                          AND checkin_date = $3
                        """,
                        channel_id,
                        user_id,
                        checkin_date,
                    )
                if row is None:
                    raise RuntimeError("Check-in conflict row could not be loaded")

                total_days = int(
                    await conn.fetchval(
                        "SELECT COUNT(*) FROM viewer_checkins "
                        "WHERE channel_id = $1 AND user_id = $2",
                        channel_id,
                        user_id,
                    )
                )

                event_id: int | None = None
                if recorded:
                    payload = {
                        "total_days": total_days,
                        "checkin_date": checkin_date.isoformat(),
                    }
                    validate_community_event(
                        CHECKIN_RECORDED.event_type,
                        CHECKIN_RECORDED.schema_version,
                        payload,
                    )
                    event_row = await conn.fetchrow(
                        """
                        INSERT INTO community_overlay_events
                            (channel_id, event_type, schema_version, source,
                             actor_user_id, actor_display_name, payload, occurred_at,
                             expires_at, idempotency_key)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        ON CONFLICT (channel_id, idempotency_key) DO UPDATE SET
                            idempotency_key = EXCLUDED.idempotency_key
                        RETURNING id
                        """,
                        channel_id,
                        CHECKIN_RECORDED.event_type,
                        CHECKIN_RECORDED.schema_version,
                        "twitch",
                        user_id,
                        display_name or username,
                        payload,
                        occurred_at,
                        expires_at,
                        f"checkin:{row['id']}",
                    )
                    if event_row is None:
                        raise RuntimeError("Failed to create check-in overlay event")
                    event_id = int(event_row["id"])

        return CheckinResult(
            status=(CheckinStatus.RECORDED if recorded else CheckinStatus.ALREADY_CHECKED_IN),
            channel_id=channel_id,
            user_id=user_id,
            username=username,
            display_name=display_name,
            checkin_date=checkin_date,
            total_days=total_days,
            checkin_id=int(row["id"]),
            event_id=event_id,
            occurred_at=occurred_at,
        )
