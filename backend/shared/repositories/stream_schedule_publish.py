"""Persistence for reliable Twitch Schedule publication."""

from __future__ import annotations

from datetime import date

import asyncpg

from shared.models.stream_schedule import (
    ScheduleKind,
    StreamSchedulePublishJob,
    StreamSchedulePublishOverview,
    TwitchScheduleOccurrenceState,
    TwitchSchedulePublishState,
)

_STATE_COLUMNS = (
    "id, channel_id, schedule_id, twitch_segment_id, schedule_kind, identity_key, "
    "payload_fingerprint, status, error_code, attempt_count, last_attempted_at, synced_at"
)
_OCCURRENCE_COLUMNS = (
    "id, channel_id, recurring_schedule_id, occurrence_date, twitch_segment_id, "
    "desired_state, status, error_code, last_attempted_at, synced_at"
)


def _state(row: asyncpg.Record | dict) -> TwitchSchedulePublishState:
    values = dict(row)
    values["schedule_kind"] = ScheduleKind(values["schedule_kind"])
    return TwitchSchedulePublishState(**values)


def _occurrence(row: asyncpg.Record | dict) -> TwitchScheduleOccurrenceState:
    return TwitchScheduleOccurrenceState(**dict(row))


class StreamSchedulePublishRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def enqueue(self, channel_id: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_schedule_publish_queue (channel_id)
                VALUES ($1)
                ON CONFLICT (channel_id) DO UPDATE SET
                    generation = stream_schedule_publish_queue.generation + 1,
                    requested_at = NOW(), available_at = NOW(), attempt_count = 0,
                    last_error_code = NULL
                """,
                channel_id,
            )

    async def enqueue_deferred(self, channel_id: str, *, delay_seconds: int) -> None:
        """Recheck future occurrence work without postponing newer immediate work."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_schedule_publish_queue (channel_id, available_at)
                VALUES ($1, NOW() + make_interval(secs => $2))
                ON CONFLICT (channel_id) DO UPDATE SET
                    generation = stream_schedule_publish_queue.generation + 1,
                    requested_at = NOW(),
                    available_at = LEAST(
                        stream_schedule_publish_queue.available_at, EXCLUDED.available_at
                    ),
                    attempt_count = 0,
                    last_error_code = NULL
                """,
                channel_id,
                delay_seconds,
            )

    async def claim_due_job(self) -> StreamSchedulePublishJob | None:
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                WITH candidate AS (
                    SELECT channel_id
                    FROM stream_schedule_publish_queue
                    WHERE available_at <= NOW()
                      AND (locked_at IS NULL OR locked_at < NOW() - INTERVAL '5 minutes')
                    ORDER BY available_at, requested_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE stream_schedule_publish_queue queue
                SET locked_at = NOW()
                FROM candidate
                WHERE queue.channel_id = candidate.channel_id
                RETURNING queue.channel_id, queue.generation, queue.attempt_count
                """
            )
            return StreamSchedulePublishJob(**dict(row)) if row else None

    async def complete_job(self, channel_id: str, *, generation: int) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "DELETE FROM stream_schedule_publish_queue "
                "WHERE channel_id = $1 AND generation = $2",
                channel_id,
                generation,
            )
            await conn.execute(
                "UPDATE stream_schedule_publish_queue SET locked_at = NULL "
                "WHERE channel_id = $1 AND generation <> $2",
                channel_id,
                generation,
            )

    async def fail_job(
        self,
        channel_id: str,
        *,
        generation: int,
        attempt_count: int,
        error_code: str,
        retryable: bool,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE stream_schedule_publish_queue
                SET locked_at = NULL,
                    attempt_count = $4 + 1,
                    last_error_code = $3,
                    available_at = NOW() + make_interval(
                        secs => (CASE WHEN $5
                            THEN LEAST(3600, 15 * POWER(2, LEAST($4, 7)))
                            ELSE 21600
                        END)::DOUBLE PRECISION
                    )
                WHERE channel_id = $1 AND generation = $2
                """,
                channel_id,
                generation,
                error_code,
                attempt_count,
                retryable,
            )

    async def list_states(self, channel_id: str) -> list[TwitchSchedulePublishState]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_STATE_COLUMNS} FROM stream_schedule_twitch_states "
                "WHERE channel_id = $1 ORDER BY id",
                channel_id,
            )
            return [_state(row) for row in rows]

    async def mark_state_synced(
        self,
        channel_id: str,
        *,
        schedule_id: int,
        schedule_kind: ScheduleKind,
        twitch_segment_id: str,
        identity_key: str,
        payload_fingerprint: str,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_schedule_twitch_states
                    (channel_id, schedule_id, twitch_segment_id, schedule_kind,
                     identity_key, payload_fingerprint, status, last_attempted_at, synced_at)
                VALUES ($1, $2, $3, $4, $5, $6, 'synced', NOW(), NOW())
                ON CONFLICT (channel_id, schedule_id) DO UPDATE SET
                    twitch_segment_id = EXCLUDED.twitch_segment_id,
                    schedule_kind = EXCLUDED.schedule_kind,
                    identity_key = EXCLUDED.identity_key,
                    payload_fingerprint = EXCLUDED.payload_fingerprint,
                    status = 'synced', error_code = NULL, attempt_count = 0,
                    last_attempted_at = NOW(), synced_at = NOW(), updated_at = NOW()
                """,
                channel_id,
                schedule_id,
                twitch_segment_id,
                schedule_kind.value,
                identity_key,
                payload_fingerprint,
            )

    async def mark_state_error(
        self,
        channel_id: str,
        *,
        schedule_id: int,
        schedule_kind: ScheduleKind,
        error_code: str,
        blocked: bool,
    ) -> None:
        status = "blocked" if blocked else "error"
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_schedule_twitch_states
                    (channel_id, schedule_id, schedule_kind, status, error_code,
                     attempt_count, last_attempted_at)
                VALUES ($1, $2, $3, $4, $5, 1, NOW())
                ON CONFLICT (channel_id, schedule_id) DO UPDATE SET
                    schedule_kind = EXCLUDED.schedule_kind,
                    status = EXCLUDED.status,
                    error_code = EXCLUDED.error_code,
                    attempt_count = stream_schedule_twitch_states.attempt_count + 1,
                    last_attempted_at = NOW(), updated_at = NOW()
                """,
                channel_id,
                schedule_id,
                schedule_kind.value,
                status,
                error_code,
            )

    async def delete_state(self, channel_id: str, state_id: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM stream_schedule_twitch_states WHERE channel_id = $1 AND id = $2",
                channel_id,
                state_id,
            )

    async def mark_existing_state_error(
        self,
        channel_id: str,
        state_id: int,
        *,
        error_code: str,
        blocked: bool,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE stream_schedule_twitch_states SET
                    status = $3,
                    error_code = $4,
                    attempt_count = attempt_count + 1,
                    last_attempted_at = NOW(),
                    updated_at = NOW()
                WHERE channel_id = $1 AND id = $2
                """,
                channel_id,
                state_id,
                "blocked" if blocked else "error",
                error_code,
            )

    async def list_occurrence_states(self, channel_id: str) -> list[TwitchScheduleOccurrenceState]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_OCCURRENCE_COLUMNS} FROM stream_schedule_twitch_occurrences "
                "WHERE channel_id = $1 ORDER BY occurrence_date, recurring_schedule_id",
                channel_id,
            )
            return [_occurrence(row) for row in rows]

    async def upsert_occurrence_desired(
        self,
        channel_id: str,
        *,
        recurring_schedule_id: int,
        occurrence_date: date,
        desired_state: str,
    ) -> TwitchScheduleOccurrenceState:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO stream_schedule_twitch_occurrences
                    (channel_id, recurring_schedule_id, occurrence_date, desired_state, status)
                VALUES ($1, $2, $3, $4, 'pending')
                ON CONFLICT (channel_id, recurring_schedule_id, occurrence_date) DO UPDATE SET
                    desired_state = EXCLUDED.desired_state,
                    status = CASE
                        WHEN stream_schedule_twitch_occurrences.desired_state = EXCLUDED.desired_state
                            THEN stream_schedule_twitch_occurrences.status
                        ELSE 'pending'
                    END,
                    error_code = NULL,
                    updated_at = NOW()
                RETURNING {_OCCURRENCE_COLUMNS}
                """,
                channel_id,
                recurring_schedule_id,
                occurrence_date,
                desired_state,
            )
            return _occurrence(row)

    async def mark_occurrence_status(
        self,
        channel_id: str,
        occurrence_id: int,
        *,
        status: str,
        twitch_segment_id: str | None = None,
        error_code: str | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE stream_schedule_twitch_occurrences SET
                    twitch_segment_id = COALESCE($3, twitch_segment_id),
                    status = $4,
                    error_code = $5,
                    last_attempted_at = NOW(),
                    synced_at = CASE WHEN $4 = 'synced' THEN NOW() ELSE synced_at END,
                    updated_at = NOW()
                WHERE channel_id = $1 AND id = $2
                """,
                channel_id,
                occurrence_id,
                twitch_segment_id,
                status,
                error_code,
            )

    async def delete_occurrence_state(self, channel_id: str, occurrence_id: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM stream_schedule_twitch_occurrences WHERE channel_id = $1 AND id = $2",
                channel_id,
                occurrence_id,
            )

    async def get_overview(self, channel_id: str) -> StreamSchedulePublishOverview:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                WITH combined_states AS (
                    SELECT status, error_code, updated_at, synced_at
                    FROM stream_schedule_twitch_states
                    WHERE channel_id = $1
                    UNION ALL
                    SELECT status, error_code, updated_at, synced_at
                    FROM stream_schedule_twitch_occurrences
                    WHERE channel_id = $1
                )
                SELECT
                    COUNT(*) FILTER (
                        WHERE state.status IN ('pending', 'deferred')
                    )::INT AS pending_count,
                    COUNT(*) FILTER (WHERE state.status = 'synced')::INT AS synced_count,
                    COUNT(*) FILTER (WHERE state.status = 'blocked')::INT AS blocked_count,
                    COUNT(*) FILTER (WHERE state.status = 'error')::INT AS error_count,
                    (ARRAY_AGG(state.error_code ORDER BY state.updated_at DESC)
                        FILTER (WHERE state.error_code IS NOT NULL))[1] AS last_error_code,
                    MAX(state.synced_at) AS last_synced_at,
                    EXISTS(
                        SELECT 1 FROM stream_schedule_publish_queue queue
                        WHERE queue.channel_id = $1
                    ) AS queued,
                    (
                        SELECT queue.last_error_code
                        FROM stream_schedule_publish_queue queue
                        WHERE queue.channel_id = $1
                    ) AS queue_error_code
                FROM combined_states state
                """,
                channel_id,
            )
        values = dict(row) if row else {}
        pending = int(values.get("pending_count") or 0)
        synced = int(values.get("synced_count") or 0)
        blocked = int(values.get("blocked_count") or 0)
        errors = int(values.get("error_count") or 0)
        queued = bool(values.get("queued"))
        queue_error = values.get("queue_error_code")
        if queue_error is not None:
            errors = max(errors, 1)
        if errors:
            status = "error"
        elif blocked:
            status = "blocked"
        elif pending or queued:
            status = "pending"
        elif synced:
            status = "synced"
        else:
            status = "idle"
        return StreamSchedulePublishOverview(
            status=status,
            pending_count=pending,
            synced_count=synced,
            blocked_count=blocked,
            error_count=errors,
            last_error_code=queue_error or values.get("last_error_code"),
            last_synced_at=values.get("last_synced_at"),
        )
