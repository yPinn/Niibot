"""Portable check-in exports and narrowly scoped owner data clearing."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass, replace
from datetime import date
from enum import StrEnum
from typing import Any

import asyncpg


class CheckinClearScope(StrEnum):
    """Closed set of destructive check-in data boundaries."""

    IMPORTED = "imported"
    ALL = "all"


@dataclass(frozen=True)
class CheckinExportRow:
    user_id: str
    username: str
    display_name: str | None
    total_days: int
    last_checkin_date: date
    current_streak: int
    daily_order: int | None


@dataclass(frozen=True)
class CheckinDataSummary:
    participant_count: int
    total_days: int
    imported_viewers: int
    imported_days: int
    ledger_checkins: int
    card_draws: int
    checkin_events: int
    scope: CheckinClearScope | None = None

    def with_scope(self, scope: CheckinClearScope) -> CheckinDataSummary:
        return replace(self, scope=scope)


def _spreadsheet_safe(value: str) -> str:
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return f"'{value}"
    return value


def encode_checkin_export_csv(rows: list[CheckinExportRow]) -> bytes:
    """Encode the importer-compatible summary contract as UTF-8 BOM CSV."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(
        [
            "Username",
            "Twitch User ID",
            "DisplayName",
            "Count",
            "LastDate",
            "Streak",
            "TodayOrder",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                _spreadsheet_safe(row.username),
                _spreadsheet_safe(row.user_id),
                _spreadsheet_safe(row.display_name or ""),
                row.total_days,
                row.last_checkin_date.isoformat(),
                row.current_streak,
                row.daily_order if row.daily_order is not None else "",
            ]
        )
    return b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")


class CheckinDataService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def list_export_rows(self, channel_id: str) -> list[CheckinExportRow]:
        async with self.pool.acquire() as conn:
            records = await conn.fetch(
                """
                WITH ledger_ranked AS (
                    SELECT
                        checkin.user_id,
                        checkin.username,
                        checkin.display_name,
                        checkin.checkin_date,
                        COUNT(*) OVER (
                            PARTITION BY checkin.channel_id, checkin.user_id
                        ) AS ledger_days,
                        COUNT(*) OVER (
                            PARTITION BY checkin.channel_id, checkin.checkin_date
                            ORDER BY checkin.id
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                        ) AS daily_order,
                        ROW_NUMBER() OVER (
                            PARTITION BY checkin.channel_id, checkin.user_id
                            ORDER BY checkin.checkin_date DESC, checkin.id DESC
                        ) AS latest_rank
                    FROM viewer_checkins AS checkin
                    WHERE checkin.channel_id = $1
                ),
                ledger AS (
                    SELECT * FROM ledger_ranked WHERE latest_rank = 1
                )
                SELECT
                    COALESCE(ledger.user_id, carryover.user_id) AS user_id,
                    COALESCE(ledger.username, carryover.source_username) AS username,
                    COALESCE(ledger.display_name, carryover.source_display_name) AS display_name,
                    COALESCE(ledger.ledger_days, 0)
                        + COALESCE(carryover.carried_total_days, 0) AS total_days,
                    CASE
                        WHEN ledger.checkin_date IS NULL THEN carryover.last_source_date
                        WHEN carryover.last_source_date IS NULL THEN ledger.checkin_date
                        ELSE GREATEST(ledger.checkin_date, carryover.last_source_date)
                    END AS last_checkin_date,
                    COALESCE(
                        streak.current_streak,
                        carryover.source_current_streak,
                        0
                    ) AS current_streak,
                    CASE
                        WHEN ledger.checkin_date IS NULL THEN carryover.source_daily_order
                        WHEN carryover.last_source_date IS NULL THEN ledger.daily_order
                        WHEN ledger.checkin_date >= carryover.last_source_date
                            THEN ledger.daily_order
                        ELSE carryover.source_daily_order
                    END AS daily_order
                FROM ledger
                FULL OUTER JOIN viewer_checkin_carryovers AS carryover
                  ON carryover.channel_id = $1
                 AND carryover.user_id = ledger.user_id
                LEFT JOIN viewer_daily_checkin_streaks AS streak
                  ON streak.channel_id = $1
                 AND streak.user_id = COALESCE(ledger.user_id, carryover.user_id)
                ORDER BY total_days DESC, last_checkin_date DESC, user_id ASC
                """,
                channel_id,
            )
        return [
            CheckinExportRow(
                user_id=str(record["user_id"]),
                username=str(record["username"]),
                display_name=record["display_name"],
                total_days=int(record["total_days"]),
                last_checkin_date=record["last_checkin_date"],
                current_streak=int(record["current_streak"]),
                daily_order=(
                    int(record["daily_order"]) if record["daily_order"] is not None else None
                ),
            )
            for record in records
        ]

    async def export_csv(self, channel_id: str) -> bytes:
        return encode_checkin_export_csv(await self.list_export_rows(channel_id))

    async def _get_summary(
        self,
        conn: asyncpg.Connection,
        channel_id: str,
    ) -> CheckinDataSummary:
        row = await conn.fetchrow(
            """
            WITH
            participants AS (
                SELECT user_id FROM viewer_checkins WHERE channel_id = $1
                UNION
                SELECT user_id FROM viewer_checkin_carryovers WHERE channel_id = $1
            ),
            ledger AS (
                SELECT COUNT(*)::BIGINT AS checkins
                FROM viewer_checkins
                WHERE channel_id = $1
            ),
            carryover AS (
                SELECT
                    COUNT(*)::BIGINT AS viewers,
                    COALESCE(SUM(carried_total_days), 0)::BIGINT AS days
                FROM viewer_checkin_carryovers
                WHERE channel_id = $1
            )
            SELECT
                (SELECT COUNT(*) FROM participants)::BIGINT AS participant_count,
                ledger.checkins + carryover.days AS total_days,
                carryover.viewers AS imported_viewers,
                carryover.days AS imported_days,
                ledger.checkins AS ledger_checkins,
                (
                    SELECT COUNT(*) FROM viewer_card_draws WHERE channel_id = $1
                )::BIGINT AS card_draws,
                (
                    SELECT COUNT(*)
                    FROM community_overlay_events
                    WHERE channel_id = $1 AND event_type = 'checkin.recorded'
                )::BIGINT AS checkin_events
            FROM ledger CROSS JOIN carryover
            """,
            channel_id,
        )
        assert row is not None
        return CheckinDataSummary(
            participant_count=int(row["participant_count"]),
            total_days=int(row["total_days"]),
            imported_viewers=int(row["imported_viewers"]),
            imported_days=int(row["imported_days"]),
            ledger_checkins=int(row["ledger_checkins"]),
            card_draws=int(row["card_draws"]),
            checkin_events=int(row["checkin_events"]),
        )

    async def get_summary(self, channel_id: str) -> CheckinDataSummary:
        async with self.pool.acquire() as conn:
            return await self._get_summary(conn, channel_id)

    async def clear(
        self,
        *,
        channel_id: str,
        actor_user_id: str,
        scope: CheckinClearScope,
    ) -> CheckinDataSummary:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"checkin-import:{channel_id}",
                )
                summary = await self._get_summary(conn, channel_id)
                if scope is CheckinClearScope.ALL:
                    await self._clear_all(conn, channel_id)
                else:
                    await self._clear_imported(conn, channel_id)
                await self._write_audit(
                    conn,
                    channel_id=channel_id,
                    actor_user_id=actor_user_id,
                    scope=scope,
                    summary=summary,
                )
        return summary.with_scope(scope)

    async def _clear_imported(self, conn: asyncpg.Connection, channel_id: str) -> None:
        await conn.execute(
            "DELETE FROM viewer_daily_checkin_streaks WHERE channel_id = $1",
            channel_id,
        )
        await conn.execute(
            "DELETE FROM viewer_checkin_carryovers WHERE channel_id = $1",
            channel_id,
        )
        await conn.execute(
            "DELETE FROM checkin_import_batches WHERE channel_id = $1",
            channel_id,
        )
        await self._rebuild_ledger_streaks(conn, channel_id)

    async def _clear_all(self, conn: asyncpg.Connection, channel_id: str) -> None:
        await conn.execute(
            """
            DELETE FROM community_overlay_events
            WHERE channel_id = $1 AND event_type = 'checkin.recorded'
            """,
            channel_id,
        )
        # viewer_card_draws uses a deferred FK and an immutable-data guard.
        # Migration 131 permits deleting the draw only after this parent row is
        # absent in the same transaction, keeping unrelated deletes blocked.
        await conn.execute(
            "DELETE FROM viewer_checkins WHERE channel_id = $1",
            channel_id,
        )
        await conn.execute(
            "DELETE FROM viewer_card_draws WHERE channel_id = $1",
            channel_id,
        )
        await conn.execute(
            "DELETE FROM viewer_daily_checkin_streaks WHERE channel_id = $1",
            channel_id,
        )
        await conn.execute(
            "DELETE FROM viewer_checkin_carryovers WHERE channel_id = $1",
            channel_id,
        )
        await conn.execute(
            "DELETE FROM checkin_import_batches WHERE channel_id = $1",
            channel_id,
        )

    async def _rebuild_ledger_streaks(
        self,
        conn: asyncpg.Connection,
        channel_id: str,
    ) -> None:
        await conn.execute(
            """
            WITH latest_island AS (
                SELECT DISTINCT ON (channel_id, user_id)
                    channel_id,
                    user_id,
                    COUNT(*) OVER (
                        PARTITION BY channel_id, user_id, island_key
                    ) AS current_streak,
                    MAX(checkin_date) OVER (
                        PARTITION BY channel_id, user_id, island_key
                    ) AS last_checkin_date
                FROM (
                    SELECT
                        channel_id,
                        user_id,
                        checkin_date,
                        checkin_date - ROW_NUMBER() OVER (
                            PARTITION BY channel_id, user_id ORDER BY checkin_date
                        )::INT AS island_key
                    FROM (
                        SELECT DISTINCT channel_id, user_id, checkin_date
                        FROM viewer_checkins
                        WHERE channel_id = $1
                    ) AS unique_dates
                ) AS islands
                ORDER BY channel_id, user_id, last_checkin_date DESC
            )
            INSERT INTO viewer_daily_checkin_streaks
                (channel_id, user_id, current_streak, last_checkin_date)
            SELECT channel_id, user_id, current_streak, last_checkin_date
            FROM latest_island
            """,
            channel_id,
        )

    async def _write_audit(
        self,
        conn: asyncpg.Connection,
        *,
        channel_id: str,
        actor_user_id: str,
        scope: CheckinClearScope,
        summary: CheckinDataSummary,
    ) -> None:
        metadata: dict[str, Any] = asdict(summary)
        metadata["scope"] = scope.value
        await conn.execute(
            """
            INSERT INTO tenant_audit_events
                (channel_id, actor_user_id, event_type, target_type, target_id, metadata)
            VALUES (
                $1,
                $2::uuid,
                'checkin.data_cleared',
                'checkin_data',
                $1,
                $3::jsonb
            )
            """,
            channel_id,
            actor_user_id,
            json.dumps(metadata),
        )
