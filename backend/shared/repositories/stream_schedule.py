"""Repository for stream_schedule_settings / stream_schedules / stream_schedule_segments."""

from __future__ import annotations

from datetime import date, time

import asyncpg

from shared.errors import ConflictError, InvalidInputError
from shared.models.stream_schedule import (
    OccurrenceExceptionKind,
    ScheduleKind,
    StreamSchedule,
    StreamScheduleOccurrenceException,
    StreamScheduleSegment,
    StreamScheduleSettings,
)
from shared.stream_schedule_validation import find_schedule_conflict

_SETTINGS_COLUMNS = "channel_id, timezone, enabled, created_at, updated_at"
_SCHEDULE_SELECT = (
    "SELECT s.id, s.channel_id, s.kind, s.weekday, s.specific_date, s.start_time, "
    "s.duration_minutes, COALESCE(opening.title_template, '') AS title_template, "
    "s.enabled, s.created_at, s.updated_at FROM stream_schedules s "
    "LEFT JOIN stream_schedule_segments opening "
    "ON opening.schedule_id = s.id AND opening.offset_minutes = 0"
)
_SEGMENT_COLUMNS = (
    "id, channel_id, schedule_id, offset_minutes, title_template, game_id, game_name, sort_order"
)
_EXCEPTION_COLUMNS = (
    "id, channel_id, recurring_schedule_id, occurrence_date, kind, "
    "replacement_schedule_id, created_at, updated_at"
)


def _row_to_schedule(row: asyncpg.Record) -> StreamSchedule:
    data = dict(row)
    data["kind"] = ScheduleKind(data["kind"])
    return StreamSchedule(**data)


def _row_to_segment(row: asyncpg.Record) -> StreamScheduleSegment:
    return StreamScheduleSegment(**dict(row))


def _row_to_exception(row: asyncpg.Record) -> StreamScheduleOccurrenceException:
    data = dict(row)
    data["kind"] = OccurrenceExceptionKind(data["kind"])
    return StreamScheduleOccurrenceException(**data)


class StreamScheduleConflictError(ConflictError):
    code = "STREAM_SCHEDULE.CONFLICT"
    user_message = "這個時段已有排程，請調整時間"


class StreamScheduleSegmentOutsideDurationError(InvalidInputError):
    code = "STREAM_SCHEDULE.SEGMENT_OUTSIDE_DURATION"
    user_message = "分段時間超出排程，請先調整分段"


class StreamScheduleRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @staticmethod
    async def _lock_channel(conn: asyncpg.Connection, channel_id: str) -> None:
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1))",
            f"stream_schedule:{channel_id}",
        )

    @staticmethod
    async def _validation_state(
        conn: asyncpg.Connection, channel_id: str
    ) -> tuple[list[StreamSchedule], set[tuple[int, date]]]:
        schedule_rows = await conn.fetch(
            f"{_SCHEDULE_SELECT} WHERE s.channel_id = $1 AND s.enabled = TRUE",
            channel_id,
        )
        exception_rows = await conn.fetch(
            """
            SELECT recurring_schedule_id, occurrence_date
            FROM stream_schedule_occurrence_exceptions
            WHERE channel_id = $1
            """,
            channel_id,
        )
        return (
            [_row_to_schedule(row) for row in schedule_rows],
            {(row["recurring_schedule_id"], row["occurrence_date"]) for row in exception_rows},
        )

    @staticmethod
    def _raise_if_conflict(
        candidate: StreamSchedule,
        existing: list[StreamSchedule],
        suppressed_occurrences: set[tuple[int, date]],
    ) -> None:
        if not candidate.enabled:
            return
        conflict = find_schedule_conflict(candidate, existing, suppressed_occurrences)
        if conflict is None:
            return
        conflict_date = (
            conflict.specific_date.isoformat()
            if conflict.specific_date is not None
            else f"weekday-{conflict.weekday}"
        )
        raise StreamScheduleConflictError(
            fields={
                "date": conflict_date,
                "start_time": conflict.start_time.strftime("%H:%M"),
            }
        )

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
                f"{_SCHEDULE_SELECT} WHERE s.channel_id = $1 "
                "ORDER BY s.kind, s.weekday, s.specific_date, s.start_time",
                channel_id,
            )
            return [_row_to_schedule(r) for r in rows]

    async def list_recurring_for_weekday(
        self, channel_id: str, weekday: int
    ) -> list[StreamSchedule]:
        """Enabled recurring schedules for one channel active on the given weekday."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"{_SCHEDULE_SELECT} WHERE s.channel_id = $1 AND s.kind = 'recurring' "
                "AND s.weekday = $2 AND s.enabled = TRUE ORDER BY s.start_time",
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
                f"{_SCHEDULE_SELECT} WHERE s.channel_id = $1 AND s.kind = 'one_off' "
                "AND s.specific_date = $2 AND s.enabled = TRUE ORDER BY s.start_time",
                channel_id,
                specific_date,
            )
            return [_row_to_schedule(r) for r in rows]

    async def get(self, channel_id: str, schedule_id: int) -> StreamSchedule | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"{_SCHEDULE_SELECT} WHERE s.channel_id = $1 AND s.id = $2",
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
        game_id: str | None = None,
        game_name: str | None = None,
    ) -> StreamSchedule:
        return await self._create(
            channel_id,
            kind=ScheduleKind.RECURRING,
            weekday=weekday,
            specific_date=None,
            start_time=start_time,
            duration_minutes=duration_minutes,
            title_template=title_template,
            game_id=game_id,
            game_name=game_name,
        )

    async def create_one_off(
        self,
        channel_id: str,
        *,
        specific_date: date,
        start_time: time,
        duration_minutes: int,
        title_template: str = "",
        game_id: str | None = None,
        game_name: str | None = None,
    ) -> StreamSchedule:
        return await self._create(
            channel_id,
            kind=ScheduleKind.ONE_OFF,
            weekday=None,
            specific_date=specific_date,
            start_time=start_time,
            duration_minutes=duration_minutes,
            title_template=title_template,
            game_id=game_id,
            game_name=game_name,
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
        game_id: str | None,
        game_name: str | None,
    ) -> StreamSchedule:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await self._lock_channel(conn, channel_id)
                existing, suppressed = await self._validation_state(conn, channel_id)
                candidate = StreamSchedule(
                    id=0,
                    channel_id=channel_id,
                    kind=kind,
                    weekday=weekday,
                    specific_date=specific_date,
                    start_time=start_time,
                    duration_minutes=duration_minutes,
                    title_template=title_template,
                )
                self._raise_if_conflict(candidate, existing, suppressed)
                schedule_id = await conn.fetchval(
                    """
                    INSERT INTO stream_schedules
                        (channel_id, kind, weekday, specific_date, start_time, duration_minutes)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING id
                    """,
                    channel_id,
                    kind.value,
                    weekday,
                    specific_date,
                    start_time,
                    duration_minutes,
                )
                await conn.execute(
                    """
                    INSERT INTO stream_schedule_segments
                        (channel_id, schedule_id, offset_minutes, title_template, game_id, game_name)
                    VALUES ($1, $2, 0, $3, $4, $5)
                    """,
                    channel_id,
                    schedule_id,
                    title_template,
                    game_id,
                    game_name,
                )
                row = await conn.fetchrow(
                    f"{_SCHEDULE_SELECT} WHERE s.channel_id = $1 AND s.id = $2",
                    channel_id,
                    schedule_id,
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
            async with conn.transaction():
                await self._lock_channel(conn, channel_id)
                current_row = await conn.fetchrow(
                    f"{_SCHEDULE_SELECT} WHERE s.channel_id = $1 AND s.id = $2",
                    channel_id,
                    schedule_id,
                )
                if current_row is None:
                    return None
                current = _row_to_schedule(current_row)
                next_duration = (
                    duration_minutes if duration_minutes is not None else current.duration_minutes
                )
                max_offset = await conn.fetchval(
                    """
                    SELECT MAX(offset_minutes)
                    FROM stream_schedule_segments
                    WHERE channel_id = $1 AND schedule_id = $2
                    """,
                    channel_id,
                    schedule_id,
                )
                if max_offset is not None and max_offset >= next_duration:
                    raise StreamScheduleSegmentOutsideDurationError(
                        fields={"duration_minutes": str(next_duration)}
                    )
                existing, suppressed = await self._validation_state(conn, channel_id)
                candidate = StreamSchedule(
                    id=current.id,
                    channel_id=current.channel_id,
                    kind=current.kind,
                    weekday=current.weekday,
                    specific_date=current.specific_date,
                    start_time=start_time or current.start_time,
                    duration_minutes=next_duration,
                    title_template=title_template
                    if title_template is not None
                    else current.title_template,
                    enabled=enabled if enabled is not None else current.enabled,
                    created_at=current.created_at,
                    updated_at=current.updated_at,
                )
                self._raise_if_conflict(candidate, existing, suppressed)
                updated_id = await conn.fetchval(
                    """
                    UPDATE stream_schedules SET
                        start_time       = COALESCE($3, start_time),
                        duration_minutes = COALESCE($4, duration_minutes),
                        enabled          = COALESCE($5, enabled)
                    WHERE channel_id = $1 AND id = $2
                    RETURNING id
                    """,
                    channel_id,
                    schedule_id,
                    start_time,
                    duration_minutes,
                    enabled,
                )
                if updated_id is None:
                    return None
                if title_template is not None:
                    await conn.execute(
                        """
                        INSERT INTO stream_schedule_segments
                            (channel_id, schedule_id, offset_minutes, title_template)
                        VALUES ($1, $2, 0, $3)
                        ON CONFLICT (schedule_id, offset_minutes) DO UPDATE SET
                            title_template = EXCLUDED.title_template
                        """,
                        channel_id,
                        schedule_id,
                        title_template,
                    )
                row = await conn.fetchrow(
                    f"{_SCHEDULE_SELECT} WHERE s.channel_id = $1 AND s.id = $2",
                    channel_id,
                    schedule_id,
                )
                return _row_to_schedule(row)

    async def delete(self, channel_id: str, schedule_id: int) -> bool:
        async with self.pool.acquire() as conn, conn.transaction():
            await self._lock_channel(conn, channel_id)
            replacement_ids = await conn.fetchval(
                """
                SELECT ARRAY_AGG(replacement_schedule_id)
                FROM stream_schedule_occurrence_exceptions
                WHERE channel_id = $1
                  AND recurring_schedule_id = $2
                  AND replacement_schedule_id IS NOT NULL
                """,
                channel_id,
                schedule_id,
            )
            result = await conn.execute(
                "DELETE FROM stream_schedules WHERE channel_id = $1 AND id = $2",
                channel_id,
                schedule_id,
            )
            if result != "DELETE 1":
                return False
            if replacement_ids:
                await conn.execute(
                    "DELETE FROM stream_schedules WHERE channel_id = $1 AND id = ANY($2::int[])",
                    channel_id,
                    replacement_ids,
                )
            return True

    # ------------------------------------------------------------------
    # Occurrence exceptions
    # ------------------------------------------------------------------

    async def list_occurrence_exceptions(
        self,
        channel_id: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[StreamScheduleOccurrenceException]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {_EXCEPTION_COLUMNS}
                FROM stream_schedule_occurrence_exceptions
                WHERE channel_id = $1
                  AND ($2::date IS NULL OR occurrence_date >= $2)
                  AND ($3::date IS NULL OR occurrence_date <= $3)
                ORDER BY occurrence_date, recurring_schedule_id
                """,
                channel_id,
                start_date,
                end_date,
            )
            return [_row_to_exception(row) for row in rows]

    async def cancel_occurrence(
        self, channel_id: str, recurring_schedule_id: int, occurrence_date: date
    ) -> StreamScheduleOccurrenceException | None:
        async with self.pool.acquire() as conn, conn.transaction():
            await self._lock_channel(conn, channel_id)
            await conn.execute(
                """
                UPDATE stream_schedules
                SET enabled = FALSE
                WHERE channel_id = $1
                  AND id = (
                      SELECT replacement_schedule_id
                      FROM stream_schedule_occurrence_exceptions
                      WHERE channel_id = $1
                        AND recurring_schedule_id = $2
                        AND occurrence_date = $3
                  )
                """,
                channel_id,
                recurring_schedule_id,
                occurrence_date,
            )
            row = await conn.fetchrow(
                f"""
                INSERT INTO stream_schedule_occurrence_exceptions
                    (channel_id, recurring_schedule_id, occurrence_date, kind)
                SELECT s.channel_id, s.id, $3, 'cancelled'
                FROM stream_schedules s
                WHERE s.channel_id = $1 AND s.id = $2 AND s.kind = 'recurring'
                  AND s.weekday = EXTRACT(ISODOW FROM $3::date)::INT - 1
                ON CONFLICT (recurring_schedule_id, occurrence_date) DO UPDATE SET
                    kind = 'cancelled',
                    replacement_schedule_id = NULL
                RETURNING {_EXCEPTION_COLUMNS}
                """,
                channel_id,
                recurring_schedule_id,
                occurrence_date,
            )
            return _row_to_exception(row) if row else None

    async def restore_occurrence(
        self, channel_id: str, recurring_schedule_id: int, occurrence_date: date
    ) -> bool:
        async with self.pool.acquire() as conn, conn.transaction():
            await self._lock_channel(conn, channel_id)
            replacement_id = await conn.fetchval(
                """
                SELECT replacement_schedule_id
                FROM stream_schedule_occurrence_exceptions
                WHERE channel_id = $1
                  AND recurring_schedule_id = $2
                  AND occurrence_date = $3
                FOR UPDATE
                """,
                channel_id,
                recurring_schedule_id,
                occurrence_date,
            )
            if replacement_id is not None:
                result = await conn.execute(
                    "DELETE FROM stream_schedules WHERE channel_id = $1 AND id = $2",
                    channel_id,
                    replacement_id,
                )
                return result == "DELETE 1"
            result = await conn.execute(
                """
                DELETE FROM stream_schedule_occurrence_exceptions
                WHERE channel_id = $1 AND recurring_schedule_id = $2 AND occurrence_date = $3
                """,
                channel_id,
                recurring_schedule_id,
                occurrence_date,
            )
            return result == "DELETE 1"

    async def create_replacement(
        self, channel_id: str, recurring_schedule_id: int, occurrence_date: date
    ) -> tuple[StreamScheduleOccurrenceException, StreamSchedule] | None:
        async with self.pool.acquire() as conn, conn.transaction():
            await self._lock_channel(conn, channel_id)
            parent = await conn.fetchrow(
                """
                SELECT id, weekday, start_time, duration_minutes
                FROM stream_schedules
                WHERE channel_id = $1 AND id = $2 AND kind = 'recurring'
                FOR UPDATE
                """,
                channel_id,
                recurring_schedule_id,
            )
            if parent is None or parent["weekday"] != occurrence_date.weekday():
                return None

            existing = await conn.fetchrow(
                f"""
                SELECT {_EXCEPTION_COLUMNS}
                FROM stream_schedule_occurrence_exceptions
                WHERE channel_id = $1 AND recurring_schedule_id = $2 AND occurrence_date = $3
                FOR UPDATE
                """,
                channel_id,
                recurring_schedule_id,
                occurrence_date,
            )
            if existing and existing["replacement_schedule_id"] is not None:
                replacement_id = existing["replacement_schedule_id"]
            else:
                schedules, suppressed = await self._validation_state(conn, channel_id)
                suppressed.add((recurring_schedule_id, occurrence_date))
                candidate = StreamSchedule(
                    id=0,
                    channel_id=channel_id,
                    kind=ScheduleKind.ONE_OFF,
                    weekday=None,
                    specific_date=occurrence_date,
                    start_time=parent["start_time"],
                    duration_minutes=parent["duration_minutes"],
                )
                self._raise_if_conflict(candidate, schedules, suppressed)
                replacement_id = await conn.fetchval(
                    """
                    INSERT INTO stream_schedules
                        (channel_id, kind, specific_date, start_time, duration_minutes)
                    VALUES ($1, 'one_off', $2, $3, $4)
                    RETURNING id
                    """,
                    channel_id,
                    occurrence_date,
                    parent["start_time"],
                    parent["duration_minutes"],
                )
                await conn.execute(
                    """
                    INSERT INTO stream_schedule_segments
                        (channel_id, schedule_id, offset_minutes, title_template,
                         game_id, game_name, sort_order)
                    SELECT channel_id, $2, offset_minutes, title_template,
                           game_id, game_name, sort_order
                    FROM stream_schedule_segments
                    WHERE channel_id = $1 AND schedule_id = $3
                    ORDER BY offset_minutes
                    """,
                    channel_id,
                    replacement_id,
                    recurring_schedule_id,
                )

            exception_row = await conn.fetchrow(
                f"""
                INSERT INTO stream_schedule_occurrence_exceptions
                    (channel_id, recurring_schedule_id, occurrence_date, kind,
                     replacement_schedule_id)
                VALUES ($1, $2, $3, 'replacement', $4)
                ON CONFLICT (recurring_schedule_id, occurrence_date) DO UPDATE SET
                    kind = 'replacement',
                    replacement_schedule_id = EXCLUDED.replacement_schedule_id
                RETURNING {_EXCEPTION_COLUMNS}
                """,
                channel_id,
                recurring_schedule_id,
                occurrence_date,
                replacement_id,
            )
            schedule_row = await conn.fetchrow(
                f"{_SCHEDULE_SELECT} WHERE s.channel_id = $1 AND s.id = $2",
                channel_id,
                replacement_id,
            )
            return _row_to_exception(exception_row), _row_to_schedule(schedule_row)

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
        async with self.pool.acquire() as conn, conn.transaction():
            await self._lock_channel(conn, channel_id)
            duration = await conn.fetchval(
                """
                SELECT duration_minutes FROM stream_schedules
                WHERE id = $1 AND channel_id = $2
                """,
                schedule_id,
                channel_id,
            )
            if duration is None:
                return None
            if offset_minutes >= duration:
                raise StreamScheduleSegmentOutsideDurationError(
                    fields={"offset_minutes": str(offset_minutes)}
                )
            row = await conn.fetchrow(
                f"""
                INSERT INTO stream_schedule_segments
                    (channel_id, schedule_id, offset_minutes, title_template, game_id, game_name, sort_order)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING {_SEGMENT_COLUMNS}
                """,
                channel_id,
                schedule_id,
                offset_minutes,
                title_template,
                game_id,
                game_name,
                sort_order,
            )
            return _row_to_segment(row)

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
        async with self.pool.acquire() as conn, conn.transaction():
            await self._lock_channel(conn, channel_id)
            current = await conn.fetchrow(
                """
                SELECT segment.offset_minutes, schedule.duration_minutes
                FROM stream_schedule_segments segment
                JOIN stream_schedules schedule ON schedule.id = segment.schedule_id
                WHERE segment.id = $1 AND segment.channel_id = $2
                """,
                segment_id,
                channel_id,
            )
            if current is None:
                return None
            next_offset = (
                offset_minutes if offset_minutes is not None else current["offset_minutes"]
            )
            if next_offset >= current["duration_minutes"]:
                raise StreamScheduleSegmentOutsideDurationError(
                    fields={"offset_minutes": str(next_offset)}
                )
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
