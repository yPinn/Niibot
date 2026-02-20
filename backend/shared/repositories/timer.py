"""Repository for timers table."""

from __future__ import annotations

import asyncpg

from shared.cache import AsyncTTLCache, cached
from shared.models.timer import TimerConfig

_timer_list_cache = AsyncTTLCache(maxsize=32, ttl=3600)

_COLUMNS = (
    "id, channel_id, timer_name, interval_seconds, min_lines, "
    "message_template, enabled, created_at, updated_at"
)


class TimerConfigRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @cached(
        cache=_timer_list_cache,
        key_func=lambda self, channel_id: f"timer_list:{channel_id}",
    )
    async def list_enabled(self, channel_id: str) -> list[TimerConfig]:
        """Return all enabled timers for a channel, ordered by id."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM timers "
                "WHERE channel_id = $1 AND enabled = TRUE ORDER BY id",
                channel_id,
            )
            return [TimerConfig(**dict(row)) for row in rows]

    async def list_all(self, channel_id: str) -> list[TimerConfig]:
        """Return all timers for a channel (enabled + disabled), ordered by id."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM timers WHERE channel_id = $1 ORDER BY id",
                channel_id,
            )
            return [TimerConfig(**dict(row)) for row in rows]

    async def upsert(
        self,
        channel_id: str,
        timer_name: str,
        *,
        interval_seconds: int | None = None,
        min_lines: int | None = None,
        message_template: str | None = None,
        enabled: bool | None = None,
    ) -> TimerConfig:
        """Insert or update a timer. Invalidates list cache."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO timers (channel_id, timer_name, interval_seconds, min_lines, message_template, enabled)
                VALUES ($1, $2, COALESCE($3, 300), COALESCE($4, 5), COALESCE($5, ''), COALESCE($6, TRUE))
                ON CONFLICT (channel_id, timer_name) DO UPDATE SET
                    interval_seconds = COALESCE($3, timers.interval_seconds),
                    min_lines        = COALESCE($4, timers.min_lines),
                    message_template = COALESCE($5, timers.message_template),
                    enabled          = COALESCE($6, timers.enabled)
                RETURNING {_COLUMNS}
                """,
                channel_id,
                timer_name,
                interval_seconds,
                min_lines,
                message_template,
                enabled,
            )
            result = TimerConfig(**dict(row))
            _timer_list_cache.invalidate(f"timer_list:{channel_id}")
            return result

    async def delete(self, channel_id: str, timer_name: str) -> bool:
        """Delete a timer. Returns True if deleted."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM timers WHERE channel_id = $1 AND timer_name = $2",
                channel_id,
                timer_name,
            )
            _timer_list_cache.invalidate(f"timer_list:{channel_id}")
            return result == "DELETE 1"

    def invalidate_cache(self, channel_id: str) -> None:
        """Invalidate list cache for a channel (called by pg_notify handler)."""
        _timer_list_cache.invalidate(f"timer_list:{channel_id}")
