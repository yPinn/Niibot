"""Birthday database repository."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

import asyncpg


@dataclass
class Birthday:
    """Birthday data model."""

    user_id: int
    month: int
    day: int
    year: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class BirthdaySettings:
    """Guild birthday settings model."""

    guild_id: int
    channel_id: int
    role_id: int
    message_template: str = "今天是 {users} 的生日，請各位送上祝福！"
    last_notified_date: Optional[date] = None
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BirthdayRepository:
    """Repository for birthday-related database operations."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    # ==================== Birthday Operations ====================

    async def get_birthday(self, user_id: int) -> Optional[Birthday]:
        """Get a user's birthday."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM birthdays WHERE user_id = $1",
                user_id,
            )
            if row:
                return Birthday(**dict(row))
            return None

    async def set_birthday(
        self,
        user_id: int,
        month: int,
        day: int,
        year: Optional[int] = None,
    ) -> None:
        """Set or update a user's birthday."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO birthdays (user_id, month, day, year)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id) DO UPDATE SET
                    month = EXCLUDED.month,
                    day = EXCLUDED.day,
                    year = EXCLUDED.year,
                    updated_at = NOW()
                """,
                user_id,
                month,
                day,
                year,
            )

    async def delete_birthday(self, user_id: int) -> bool:
        """Delete a user's birthday. Returns True if deleted."""
        async with self.pool.acquire() as conn:
            result: str = await conn.execute(
                "DELETE FROM birthdays WHERE user_id = $1",
                user_id,
            )
            return result == "DELETE 1"

    # ==================== Subscription Operations ====================

    async def is_subscribed(self, guild_id: int, user_id: int) -> bool:
        """Check if a user is subscribed to a guild's birthday notifications."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1 FROM birthday_subscriptions
                WHERE guild_id = $1 AND user_id = $2
                """,
                guild_id,
                user_id,
            )
            return row is not None

    async def subscribe(self, guild_id: int, user_id: int) -> None:
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

    async def unsubscribe(self, guild_id: int, user_id: int) -> bool:
        """Unsubscribe a user from a guild's birthday notifications."""
        async with self.pool.acquire() as conn:
            result: str = await conn.execute(
                """
                DELETE FROM birthday_subscriptions
                WHERE guild_id = $1 AND user_id = $2
                """,
                guild_id,
                user_id,
            )
            return result == "DELETE 1"

    async def unsubscribe_user_from_guild(self, guild_id: int, user_id: int) -> None:
        """Remove user's subscription when they leave a guild."""
        await self.unsubscribe(guild_id, user_id)

    async def delete_guild_subscriptions(self, guild_id: int) -> None:
        """Delete all subscriptions for a guild."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM birthday_subscriptions WHERE guild_id = $1",
                guild_id,
            )

    # ==================== Settings Operations ====================

    async def get_settings(self, guild_id: int) -> Optional[BirthdaySettings]:
        """Get guild birthday settings."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM birthday_settings WHERE guild_id = $1",
                guild_id,
            )
            if row:
                return BirthdaySettings(**dict(row))
            return None

    async def create_settings(
        self,
        guild_id: int,
        channel_id: int,
        role_id: int,
        message_template: Optional[str] = None,
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

    async def update_settings(
        self,
        guild_id: int,
        channel_id: Optional[int] = None,
        role_id: Optional[int] = None,
        message_template: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        """Update guild birthday settings."""
        updates: list[str] = []
        values: list[Any] = []
        param_count = 1

        if channel_id is not None:
            updates.append(f"channel_id = ${param_count}")
            values.append(channel_id)
            param_count += 1

        if role_id is not None:
            updates.append(f"role_id = ${param_count}")
            values.append(role_id)
            param_count += 1

        if message_template is not None:
            updates.append(f"message_template = ${param_count}")
            values.append(message_template)
            param_count += 1

        if enabled is not None:
            updates.append(f"enabled = ${param_count}")
            values.append(enabled)
            param_count += 1

        if not updates:
            return

        values.append(guild_id)
        query = f"""
            UPDATE birthday_settings
            SET {", ".join(updates)}, updated_at = NOW()
            WHERE guild_id = ${param_count}
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, *values)

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

    # ==================== Query Operations ====================

    async def get_todays_birthdays(
        self, guild_id: int, month: int, day: int
    ) -> list[tuple[int, Optional[int]]]:
        """Get users with birthdays today in a guild.

        Returns list of (user_id, year) tuples.
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

    async def get_birthdays_in_month(
        self, guild_id: int, month: int
    ) -> list[tuple[int, int, int, Optional[int]]]:
        """Get all birthdays in a month for a guild.

        Returns list of (user_id, month, day, year) tuples, ordered by day.
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
            return [
                (row["user_id"], row["month"], row["day"], row["year"]) for row in rows
            ]

    async def get_upcoming_birthdays(
        self, guild_id: int, current_month: int, current_day: int, limit: int = 5
    ) -> list[tuple[int, int, int, Optional[int]]]:
        """Get upcoming birthdays for a guild.

        Returns list of (user_id, month, day, year) tuples.
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
                  b.month,
                  b.day,
                  b.user_id
                LIMIT $4
                """,
                guild_id,
                current_month,
                current_day,
                limit,
            )
            return [
                (row["user_id"], row["month"], row["day"], row["year"]) for row in rows
            ]

    async def get_all_enabled_settings(self) -> list[BirthdaySettings]:
        """Get all enabled guild settings for background task."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM birthday_settings WHERE enabled = true"
            )
            return [BirthdaySettings(**dict(row)) for row in rows]
