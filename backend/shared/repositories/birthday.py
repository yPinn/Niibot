"""Repository for birthdays, birthday_subscriptions, and birthday_settings tables."""

from __future__ import annotations

from datetime import date
from typing import Any, cast

import asyncpg

from shared.cache import _MISSING, AsyncTTLCache
from shared.models.birthday import Birthday, BirthdaySettings

# --- In-process caches ---
_birthday_cache = AsyncTTLCache(maxsize=64, ttl=60)
_settings_cache = AsyncTTLCache(maxsize=16, ttl=120)
_all_enabled_cache = AsyncTTLCache(maxsize=1, ttl=300)


class BirthdayRepository:
    """Pure SQL operations for birthday feature tables."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ==================== Birthday Operations ====================

    async def get_birthday(self, user_id: int) -> Birthday | None:
        """Get a user's birthday."""
        cache_key = f"bday:{user_id}"
        cached = _birthday_cache.get(cache_key)
        if cached is not _MISSING:
            return cached

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM birthdays WHERE user_id = $1",
                user_id,
            )
            if not row:
                return None
            result = cast(Birthday, Birthday(**dict(row)))
            _birthday_cache.set(cache_key, result)
            return result

    async def upsert_birthday(
        self,
        user_id: int,
        month: int,
        day: int,
        year: int | None = None,
    ) -> None:
        """Insert or update a user's birthday."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO birthdays (user_id, month, day, year)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id) DO UPDATE SET
                    month = EXCLUDED.month,
                    day   = EXCLUDED.day,
                    year  = EXCLUDED.year,
                    updated_at = NOW()
                """,
                user_id,
                month,
                day,
                year,
            )
        _birthday_cache.invalidate(f"bday:{user_id}")

    async def delete_birthday(self, user_id: int) -> bool:
        """Delete a user's birthday. Returns True if a row was deleted."""
        async with self.pool.acquire() as conn:
            result: str = await conn.execute(
                "DELETE FROM birthdays WHERE user_id = $1",
                user_id,
            )
        _birthday_cache.invalidate(f"bday:{user_id}")
        return result == "DELETE 1"

    # ==================== Subscription Operations ====================

    async def exists_subscription(self, guild_id: int, user_id: int) -> bool:
        """Check if a user is subscribed to a guild's birthday notifications."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM birthday_subscriptions WHERE guild_id = $1 AND user_id = $2",
                guild_id,
                user_id,
            )
            return row is not None

    async def create_subscription(self, guild_id: int, user_id: int) -> None:
        """Subscribe a user to a guild's birthday notifications."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO birthday_subscriptions (guild_id, user_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                """,
                guild_id,
                user_id,
            )

    async def delete_subscription(self, guild_id: int, user_id: int) -> bool:
        """Unsubscribe a user. Returns True if a row was deleted."""
        async with self.pool.acquire() as conn:
            result: str = await conn.execute(
                "DELETE FROM birthday_subscriptions WHERE guild_id = $1 AND user_id = $2",
                guild_id,
                user_id,
            )
            return result == "DELETE 1"

    async def delete_guild_subscriptions(self, guild_id: int) -> None:
        """Delete all subscriptions for a guild."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM birthday_subscriptions WHERE guild_id = $1",
                guild_id,
            )

    # ==================== Settings Operations ====================

    async def get_settings(self, guild_id: int) -> BirthdaySettings | None:
        """Get guild birthday settings."""
        cache_key = f"settings:{guild_id}"
        cached = _settings_cache.get(cache_key)
        if cached is not _MISSING:
            return cached

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM birthday_settings WHERE guild_id = $1",
                guild_id,
            )
            result = BirthdaySettings(**dict(row)) if row else None
            if result is not None:
                _settings_cache.set(cache_key, result)
            return result

    async def create_settings(
        self,
        guild_id: int,
        channel_id: int,
        role_id: int,
        message_template: str | None = None,
    ) -> None:
        """Create guild birthday settings."""
        async with self.pool.acquire() as conn:
            if message_template:
                await conn.execute(
                    """
                    INSERT INTO birthday_settings
                        (guild_id, channel_id, role_id, message_template)
                    VALUES ($1, $2, $3, $4)
                    """,
                    guild_id,
                    channel_id,
                    role_id,
                    message_template,
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO birthday_settings (guild_id, channel_id, role_id)
                    VALUES ($1, $2, $3)
                    """,
                    guild_id,
                    channel_id,
                    role_id,
                )
        _settings_cache.invalidate(f"settings:{guild_id}")
        _all_enabled_cache.clear()

    async def update_settings(
        self,
        guild_id: int,
        channel_id: int | None = None,
        role_id: int | None = None,
        message_template: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        """Update guild birthday settings (partial update)."""
        updates: list[str] = []
        values: list[Any] = []
        idx = 1

        if channel_id is not None:
            updates.append(f"channel_id = ${idx}")
            values.append(channel_id)
            idx += 1
        if role_id is not None:
            updates.append(f"role_id = ${idx}")
            values.append(role_id)
            idx += 1
        if message_template is not None:
            updates.append(f"message_template = ${idx}")
            values.append(message_template)
            idx += 1
        if enabled is not None:
            updates.append(f"enabled = ${idx}")
            values.append(enabled)
            idx += 1

        if not updates:
            return

        values.append(guild_id)
        query = (
            f"UPDATE birthday_settings "
            f"SET {', '.join(updates)}, updated_at = NOW() "
            f"WHERE guild_id = ${idx}"
        )
        async with self.pool.acquire() as conn:
            await conn.execute(query, *values)
        _settings_cache.invalidate(f"settings:{guild_id}")
        _all_enabled_cache.clear()

    async def update_last_notified(self, guild_id: int, notified_date: date) -> None:
        """Update the last notified date for a guild."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE birthday_settings
                SET last_notified_date = $1, updated_at = NOW()
                WHERE guild_id = $2
                """,
                notified_date,
                guild_id,
            )

    async def delete_settings(self, guild_id: int) -> None:
        """Delete guild birthday settings."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM birthday_settings WHERE guild_id = $1",
                guild_id,
            )
        _settings_cache.invalidate(f"settings:{guild_id}")
        _all_enabled_cache.clear()

    # ==================== Query Operations ====================

    async def list_todays_birthdays(
        self, guild_id: int, month: int, day: int
    ) -> list[tuple[int, int | None]]:
        """Get users with birthdays today in a guild.

        Returns list of ``(user_id, year)`` tuples.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT b.user_id, b.year
                FROM birthdays b
                JOIN birthday_subscriptions s ON b.user_id = s.user_id
                WHERE s.guild_id = $1 AND b.month = $2 AND b.day = $3
                ORDER BY b.user_id
                """,
                guild_id,
                month,
                day,
            )
            return [(row["user_id"], row["year"]) for row in rows]

    async def list_birthdays_in_month(
        self, guild_id: int, month: int
    ) -> list[tuple[int, int, int, int | None]]:
        """Get all birthdays in a month for a guild.

        Returns list of ``(user_id, month, day, year)`` tuples.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT b.user_id, b.month, b.day, b.year
                FROM birthdays b
                JOIN birthday_subscriptions s ON b.user_id = s.user_id
                WHERE s.guild_id = $1 AND b.month = $2
                ORDER BY b.day, b.user_id
                """,
                guild_id,
                month,
            )
            return [(row["user_id"], row["month"], row["day"], row["year"]) for row in rows]

    async def list_upcoming_birthdays(
        self, guild_id: int, current_month: int, current_day: int, limit: int = 5
    ) -> list[tuple[int, int, int, int | None]]:
        """Get upcoming birthdays for a guild.

        Returns list of ``(user_id, month, day, year)`` tuples.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT b.user_id, b.month, b.day, b.year
                FROM birthdays b
                JOIN birthday_subscriptions s ON b.user_id = s.user_id
                WHERE s.guild_id = $1
                  AND (
                    (b.month > $2) OR
                    (b.month = $2 AND b.day > $3) OR
                    (b.month < $2)
                  )
                ORDER BY
                  CASE WHEN b.month >= $2 THEN 0 ELSE 1 END,
                  b.month, b.day, b.user_id
                LIMIT $4
                """,
                guild_id,
                current_month,
                current_day,
                limit,
            )
            return [(row["user_id"], row["month"], row["day"], row["year"]) for row in rows]

    async def list_enabled_settings(self) -> list[BirthdaySettings]:
        """Get all enabled guild settings (for background notification task)."""
        cache_key = "all_enabled"
        cached = _all_enabled_cache.get(cache_key)
        if cached is not _MISSING:
            return cached

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM birthday_settings WHERE enabled = TRUE")
            result = [cast(BirthdaySettings, BirthdaySettings(**dict(row))) for row in rows]
            _all_enabled_cache.set(cache_key, result)
            return result
