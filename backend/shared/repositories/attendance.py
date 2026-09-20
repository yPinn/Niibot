"""Persistence for channel-scoped daily check-ins."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import asyncpg

from shared.community_events import CHECKIN_RECORDED, validate_community_event
from shared.models.attendance import (
    CheckinLeaderboardEntry,
    CheckinRank,
    CheckinResult,
    CheckinSettings,
    CheckinStatus,
)
from shared.models.collection import CollectionDraw
from shared.repositories.collection import CollectionRepository

_CHECKIN_COLUMNS = (
    "id, channel_id, user_id, username, display_name, checkin_date, session_id, created_at"
)
_SETTINGS_COLUMNS = (
    "channel_id, timezone, success_template, duplicate_template, "
    "reply_delay_seconds, created_at, updated_at"
)

# Shared by list_leaderboard and get_checkin_rank so a viewer's chat-facing rank can
# never drift from the dashboard leaderboard's ordering. $1 = channel_id.
_RANKED_CHECKINS_CTE = """
    WITH ledger_totals AS (
        SELECT
            user_id,
            (ARRAY_AGG(username ORDER BY checkin_date DESC, id DESC))[1] AS username,
            (ARRAY_AGG(display_name ORDER BY checkin_date DESC, id DESC))[1] AS display_name,
            COUNT(*) AS ledger_days,
            MAX(checkin_date) AS last_checkin_date
        FROM viewer_checkins
        WHERE channel_id = $1
        GROUP BY user_id
    ), carryover_totals AS (
        SELECT
            user_id,
            source_username AS username,
            source_display_name AS display_name,
            carried_total_days,
            last_source_date AS last_checkin_date
        FROM viewer_checkin_carryovers
        WHERE channel_id = $1
    ), viewer_totals AS (
        SELECT
            COALESCE(ledger.user_id, carryover.user_id) AS user_id,
            COALESCE(ledger.username, carryover.username) AS username,
            COALESCE(ledger.display_name, carryover.display_name) AS display_name,
            COALESCE(ledger.ledger_days, 0) + COALESCE(carryover.carried_total_days, 0)
                AS total_days,
            CASE
                WHEN ledger.last_checkin_date IS NULL THEN carryover.last_checkin_date
                WHEN carryover.last_checkin_date IS NULL THEN ledger.last_checkin_date
                ELSE GREATEST(ledger.last_checkin_date, carryover.last_checkin_date)
            END AS last_checkin_date
        FROM ledger_totals AS ledger
        FULL OUTER JOIN carryover_totals AS carryover USING (user_id)
    ), ranked AS (
        SELECT
            ROW_NUMBER() OVER (
                ORDER BY
                    total_days DESC,
                    last_checkin_date DESC,
                    LOWER(COALESCE(display_name, username)),
                    user_id
            ) AS rank,
            COUNT(*) OVER () AS total_participants,
            user_id,
            username,
            display_name,
            total_days,
            last_checkin_date
        FROM viewer_totals
    )
"""


class AttendanceRepository:
    """Atomic check-in ledger and its successful overlay projection."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        collection_repository: CollectionRepository | None = None,
    ) -> None:
        self.pool = pool
        self.collection_repository = collection_repository or CollectionRepository()

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
        reply_delay_seconds: int,
    ) -> CheckinSettings:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO checkin_settings
                    (channel_id, timezone, success_template, duplicate_template,
                     reply_delay_seconds)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (channel_id) DO UPDATE SET
                    timezone = EXCLUDED.timezone,
                    success_template = EXCLUDED.success_template,
                    duplicate_template = EXCLUDED.duplicate_template,
                    reply_delay_seconds = EXCLUDED.reply_delay_seconds,
                    updated_at = NOW()
                RETURNING {_SETTINGS_COLUMNS}
                """,
                channel_id,
                timezone,
                success_template,
                duplicate_template,
                reply_delay_seconds,
            )
        if row is None:
            raise RuntimeError(f"Failed to update check-in settings for channel {channel_id}")
        return CheckinSettings(**dict(row))

    async def list_leaderboard(
        self, channel_id: str, *, limit: int = 100
    ) -> tuple[CheckinLeaderboardEntry, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                _RANKED_CHECKINS_CTE
                + """
                SELECT rank, user_id, username, display_name, total_days, last_checkin_date
                FROM ranked
                ORDER BY rank
                LIMIT $2
                """,
                channel_id,
                limit,
            )
        return tuple(CheckinLeaderboardEntry(**dict(row)) for row in rows)

    async def get_checkin_rank(self, channel_id: str, user_id: str) -> CheckinRank | None:
        """A single viewer's rank against the same ordering as list_leaderboard."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                _RANKED_CHECKINS_CTE
                + """
                SELECT rank, total_days, last_checkin_date, total_participants
                FROM ranked
                WHERE user_id = $2
                """,
                channel_id,
                user_id,
            )
        return CheckinRank(**dict(row)) if row is not None else None

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
                # Normal check-ins share this lock; an import takes the exclusive
                # form so its conflict check and cut-over cannot race a live viewer.
                await conn.execute(
                    "SELECT pg_advisory_xact_lock_shared(hashtextextended($1, 0))",
                    f"checkin-import:{channel_id}",
                )
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

                carryover = await conn.fetchrow(
                    """
                    SELECT carryover.carried_total_days,
                           carryover.last_source_date,
                           streak.current_streak
                    FROM viewer_checkin_carryovers AS carryover
                    LEFT JOIN viewer_daily_checkin_streaks AS streak
                      ON streak.channel_id = carryover.channel_id
                     AND streak.user_id = carryover.user_id
                    WHERE carryover.channel_id = $1 AND carryover.user_id = $2
                    """,
                    channel_id,
                    user_id,
                )
                carried_total_days = int(carryover["carried_total_days"]) if carryover else 0
                if carryover is not None and checkin_date <= carryover["last_source_date"]:
                    ledger_days = int(
                        await conn.fetchval(
                            "SELECT COUNT(*) FROM viewer_checkins "
                            "WHERE channel_id = $1 AND user_id = $2",
                            channel_id,
                            user_id,
                        )
                    )
                    return CheckinResult(
                        status=CheckinStatus.ALREADY_CHECKED_IN,
                        channel_id=channel_id,
                        user_id=user_id,
                        username=username,
                        display_name=display_name,
                        checkin_date=checkin_date,
                        total_days=carried_total_days + ledger_days,
                        checkin_id=None,
                        event_id=None,
                        occurred_at=occurred_at,
                        current_streak=int(carryover["current_streak"] or 0),
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

                ledger_days = int(
                    await conn.fetchval(
                        "SELECT COUNT(*) FROM viewer_checkins "
                        "WHERE channel_id = $1 AND user_id = $2",
                        channel_id,
                        user_id,
                    )
                )
                total_days = carried_total_days + ledger_days

                if recorded:
                    current_streak = int(
                        await conn.fetchval(
                            """
                            INSERT INTO viewer_daily_checkin_streaks
                                (channel_id, user_id, current_streak, last_checkin_date)
                            VALUES ($1, $2, 1, $3)
                            ON CONFLICT (channel_id, user_id) DO UPDATE SET
                                current_streak = CASE
                                    WHEN viewer_daily_checkin_streaks.last_checkin_date
                                         = EXCLUDED.last_checkin_date - 1
                                    THEN viewer_daily_checkin_streaks.current_streak + 1
                                    WHEN viewer_daily_checkin_streaks.last_checkin_date
                                         = EXCLUDED.last_checkin_date
                                    THEN viewer_daily_checkin_streaks.current_streak
                                    ELSE 1
                                END,
                                last_checkin_date = GREATEST(
                                    viewer_daily_checkin_streaks.last_checkin_date,
                                    EXCLUDED.last_checkin_date
                                ),
                                updated_at = NOW()
                            RETURNING current_streak
                            """,
                            channel_id,
                            user_id,
                            checkin_date,
                        )
                    )
                else:
                    current_streak = int(
                        await conn.fetchval(
                            """
                            SELECT COALESCE(current_streak, 0)
                            FROM viewer_daily_checkin_streaks
                            WHERE channel_id = $1 AND user_id = $2
                            """,
                            channel_id,
                            user_id,
                        )
                        or 0
                    )

                event_id: int | None = None
                collection: CollectionDraw | None = None
                if recorded:
                    collection = await self.collection_repository.draw_for_checkin(
                        conn,
                        channel_id=channel_id,
                        user_id=user_id,
                        checkin_id=int(row["id"]),
                        drawn_at=occurred_at,
                    )
                    payload = {
                        "total_days": total_days,
                        "checkin_date": checkin_date.isoformat(),
                        "collection": collection.to_event_snapshot(),
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
            current_streak=current_streak,
            collection=collection,
        )
