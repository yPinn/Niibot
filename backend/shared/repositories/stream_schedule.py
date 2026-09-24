"""Repository for stream_schedule_settings / stream_schedules / stream_schedule_segments."""

from __future__ import annotations

from datetime import date, time

import asyncpg

from shared.models.stream_schedule import (
    ScheduleKind,
    StreamSchedule,
    StreamScheduleSegment,
    StreamScheduleSettings,
)

_SETTINGS_COLUMNS = "channel_id, timezone, enabled, created_at, updated_at"
_SCHEDULE_COLUMNS = (
    "id, channel_id, kind, weekday, specific_date, start_time, duration_minutes, "
    "title_template, enabled, created_at, updated_at"
)
_SEGMENT_COLUMNS = (
    "id, channel_id, schedule_id, offset_minutes, title_template, game_id, game_name, sort_order"
)


def _row_to_schedule(row: asyncpg.Record) -> StreamSchedule:
    data = dict(row)
    data["kind"] = ScheduleKind(data["kind"])
    return StreamSchedule(**data)


def _row_to_segment(row: asyncpg.Record) -> StreamScheduleSegment:
    return StreamScheduleSegment(**dict(row))


class StreamScheduleRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ------------------------------------------------------------------
    # Settings (one row per channel)
    # ------------------------------------------------------------------

    async def get_or_create_settings(self, channel_id: str) -> StreamScheduleSettings:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO stream_schedule_settings (channel_id)
                VALUES ($1)
                ON CONFLICT (channel_id) DO UPDATE SET channel_id = stream_schedule_settings.channel_id
                RETURNING {_SETTINGS_COLUMNS}
                """,
                channel_id,
            )
            return StreamScheduleSettings(**dict(row))

    async def update_settings(
        self,
        channel_id: str,
        *,
        timezone: str | None = None,
        enabled: bool | None = None,
    ) -> StreamScheduleSettings:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO stream_schedule_settings (channel_id, timezone, enabled)
                VALUES ($1, COALESCE($2, 'Asia/Taipei'), COALESCE($3, TRUE))
                ON CONFLICT (channel_id) DO UPDATE SET
                    timezone = COALESCE($2, stream_schedule_settings.timezone),
                    enabled  = COALESCE($3, stream_schedule_settings.enabled)
                RETURNING {_SETTINGS_COLUMNS}
                """,
                channel_id,
                timezone,
                enabled,
            )
            return StreamScheduleSettings(**dict(row))

    # ------------------------------------------------------------------
    # Schedules (plan level)
    # ------------------------------------------------------------------

    async def list_all(self, channel_id: str) -> list[StreamSchedule]:
        """All schedules for a channel (enabled + disabled), for the dashboard list."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_SCHEDULE_COLUMNS} FROM stream_schedules "
                "WHERE channel_id = $1 ORDER BY kind, weekday, specific_date, start_time",
                channel_id,
            )
            return [_row_to_schedule(r) for r in rows]

    async def list_recurring_for_weekday(
        self, channel_id: str, weekday: int
    ) -> list[StreamSchedule]:
        """Enabled recurring schedules for one channel active on the given weekday."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_SCHEDULE_COLUMNS} FROM stream_schedules "
                "WHERE channel_id = $1 AND kind = 'recurring' AND weekday = $2 AND enabled = TRUE "
                "ORDER BY start_time",
                channel_id,
                weekday,
            )
            return [_row_to_schedule(r) for r in rows]

    async def list_one_off_for_date(
        self, channel_id: str, specific_date: date
    ) -> list[StreamSchedule]:
        """Enabled one-off schedules for one channel on the given date."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_SCHEDULE_COLUMNS} FROM stream_schedules "
                "WHERE channel_id = $1 AND kind = 'one_off' AND specific_date = $2 AND enabled = TRUE "
                "ORDER BY start_time",
                channel_id,
                specific_date,
            )
            return [_row_to_schedule(r) for r in rows]

    async def get(self, channel_id: str, schedule_id: int) -> StreamSchedule | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_SCHEDULE_COLUMNS} FROM stream_schedules "
                "WHERE channel_id = $1 AND id = $2",
                channel_id,
                schedule_id,
            )
            return _row_to_schedule(row) if row else None

    async def create_recurring(
        self,
        channel_id: str,
        *,
        weekday: int,
        start_time: time,
        duration_minutes: int,
        title_template: str = "",
    ) -> StreamSchedule:
        return await self._create(
            channel_id,
            kind=ScheduleKind.RECURRING,
            weekday=weekday,
            specific_date=None,
            start_time=start_time,
            duration_minutes=duration_minutes,
            title_template=title_template,
        )

    async def create_one_off(
        self,
        channel_id: str,
        *,
        specific_date: date,
        start_time: time,
        duration_minutes: int,
        title_template: str = "",
    ) -> StreamSchedule:
        return await self._create(
            channel_id,
            kind=ScheduleKind.ONE_OFF,
            weekday=None,
            specific_date=specific_date,
            start_time=start_time,
            duration_minutes=duration_minutes,
            title_template=title_template,
        )

    async def _create(
        self,
        channel_id: str,
        *,
        kind: ScheduleKind,
        weekday: int | None,
        specific_date: date | None,
        start_time: time,
        duration_minutes: int,
        title_template: str,
    ) -> StreamSchedule:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO stream_schedules
                    (channel_id, kind, weekday, specific_date, start_time, duration_minutes, title_template)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING {_SCHEDULE_COLUMNS}
                """,
                channel_id,
                kind.value,
                weekday,
                specific_date,
                start_time,
                duration_minutes,
                title_template,
            )
            return _row_to_schedule(row)

    async def update(
        self,
        channel_id: str,
        schedule_id: int,
        *,
        start_time: time | None = None,
        duration_minutes: int | None = None,
        title_template: str | None = None,
        enabled: bool | None = None,
    ) -> StreamSchedule | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE stream_schedules SET
                    start_time       = COALESCE($3, start_time),
                    duration_minutes = COALESCE($4, duration_minutes),
                    title_template   = COALESCE($5, title_template),
                    enabled          = COALESCE($6, enabled)
                WHERE channel_id = $1 AND id = $2
                RETURNING {_SCHEDULE_COLUMNS}
                """,
                channel_id,
                schedule_id,
                start_time,
                duration_minutes,
                title_template,
                enabled,
            )
            return _row_to_schedule(row) if row else None

    async def delete(self, channel_id: str, schedule_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM stream_schedules WHERE channel_id = $1 AND id = $2",
                channel_id,
                schedule_id,
            )
            return result == "DELETE 1"

    # ------------------------------------------------------------------
    # Segments (sub-blocks of a schedule)
    # ------------------------------------------------------------------

    async def list_segments(self, channel_id: str, schedule_id: int) -> list[StreamScheduleSegment]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_SEGMENT_COLUMNS} FROM stream_schedule_segments "
                "WHERE channel_id = $1 AND schedule_id = $2 ORDER BY offset_minutes",
                channel_id,
                schedule_id,
            )
            return [_row_to_segment(r) for r in rows]

    async def list_segments_for_schedules(
        self, schedule_ids: list[int]
    ) -> dict[int, list[StreamScheduleSegment]]:
        """Batch fetch, grouped by schedule_id — avoids N+1 when resolving a day's candidates."""
        if not schedule_ids:
            return {}
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_SEGMENT_COLUMNS} FROM stream_schedule_segments "
                "WHERE schedule_id = ANY($1::int[]) ORDER BY schedule_id, offset_minutes",
                schedule_ids,
            )
        grouped: dict[int, list[StreamScheduleSegment]] = {sid: [] for sid in schedule_ids}
        for row in rows:
            segment = _row_to_segment(row)
            grouped[segment.schedule_id].append(segment)
        return grouped

    async def add_segment(
        self,
        channel_id: str,
        schedule_id: int,
        *,
        offset_minutes: int,
        title_template: str,
        game_id: str | None = None,
        game_name: str | None = None,
        sort_order: int = 0,
    ) -> StreamScheduleSegment | None:
        """Returns None if schedule_id doesn't belong to channel_id (caller treats as 404).

        channel_id on the new row is derived from the parent schedule (never taken
        as a bare literal insert value) — the WHERE clause is what actually enforces
        that schedule_id belongs to the caller's channel.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO stream_schedule_segments
                    (channel_id, schedule_id, offset_minutes, title_template, game_id, game_name, sort_order)
                SELECT s.channel_id, s.id, $2, $3, $4, $5, $6
                FROM stream_schedules s
                WHERE s.id = $1 AND s.channel_id = $7
                RETURNING {_SEGMENT_COLUMNS}
                """,
                schedule_id,
                offset_minutes,
                title_template,
                game_id,
                game_name,
                sort_order,
                channel_id,
            )
            return _row_to_segment(row) if row else None

    async def update_segment(
        self,
        channel_id: str,
        segment_id: int,
        *,
        offset_minutes: int | None = None,
        title_template: str | None = None,
        game_id: str | None = None,
        game_name: str | None = None,
        sort_order: int | None = None,
        clear_game: bool = False,
    ) -> StreamScheduleSegment | None:
        """game_id/game_name of None means "leave unchanged" (COALESCE) unless
        clear_game=True, which forces both to NULL — same two-state problem
        `clear_alias` solves for timers.upsert(); a bare None can't express both
        "don't touch" and "set to NULL" at once.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE stream_schedule_segments SET
                    offset_minutes = COALESCE($3, offset_minutes),
                    title_template = COALESCE($4, title_template),
                    game_id        = CASE WHEN $8 THEN NULL ELSE COALESCE($5, game_id) END,
                    game_name      = CASE WHEN $8 THEN NULL ELSE COALESCE($6, game_name) END,
                    sort_order     = COALESCE($7, sort_order)
                WHERE id = $1 AND channel_id = $2
                RETURNING {_SEGMENT_COLUMNS}
                """,
                segment_id,
                channel_id,
                offset_minutes,
                title_template,
                game_id,
                game_name,
                sort_order,
                clear_game,
            )
            return _row_to_segment(row) if row else None

    async def delete_segment(self, channel_id: str, segment_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM stream_schedule_segments WHERE id = $1 AND channel_id = $2",
                segment_id,
                channel_id,
            )
            return result == "DELETE 1"
