"""Event recording and chatter-stats operations for AnalyticsRepository.

Depends on attributes defined in AnalyticsRepository.__init__:
    self.pool
"""

from __future__ import annotations

import logging
from datetime import datetime

import asyncpg
from asyncpg.exceptions import UndefinedTableError

LOGGER: logging.Logger = logging.getLogger(__name__)


class _AnalyticsEventsMixin:
    pool: asyncpg.Pool  # type: ignore[assignment]

    # ==================== Stream event recording ====================

    async def record_command_usage(
        self, session_id: int, channel_id: str, command_name: str
    ) -> None:
        """Increment (or create) a command usage counter for a session."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO command_stats (session_id, channel_id, command_name, usage_count, last_used_at)
                VALUES ($1, $2, $3, 1, NOW())
                ON CONFLICT (session_id, command_name)
                DO UPDATE SET
                    usage_count  = command_stats.usage_count + 1,
                    last_used_at = NOW()
                """,
                session_id,
                channel_id,
                command_name,
            )

    async def record_follow_event(
        self,
        session_id: int,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        occurred_at: datetime,
    ) -> None:
        """Record a follow event."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_events
                    (session_id, channel_id, event_type, user_id, username, display_name, occurred_at)
                VALUES ($1, $2, 'follow', $3, $4, $5, $6)
                """,
                session_id,
                channel_id,
                user_id,
                username,
                display_name,
                occurred_at,
            )

    async def record_subscribe_event(
        self,
        session_id: int,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        tier: str,
        is_gift: bool,
        occurred_at: datetime,
    ) -> None:
        """Record a subscribe event."""
        metadata = {"tier": tier, "is_gift": is_gift}
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_events
                    (session_id, channel_id, event_type, user_id, username, display_name, metadata, occurred_at)
                VALUES ($1, $2, 'subscribe', $3, $4, $5, $6, $7)
                """,
                session_id,
                channel_id,
                user_id,
                username,
                display_name,
                metadata,
                occurred_at,
            )

    async def record_cheer_event(
        self,
        session_id: int,
        channel_id: str,
        user_id: str | None,
        username: str,
        bits: int,
        occurred_at: datetime,
    ) -> None:
        """Record a cheer (bits) event."""
        metadata = {"bits": bits}
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_events
                    (session_id, channel_id, event_type, user_id, username, metadata, occurred_at)
                VALUES ($1, $2, 'cheer', $3, $4, $5, $6)
                """,
                session_id,
                channel_id,
                user_id,
                username,
                metadata,
                occurred_at,
            )

    async def record_raid_event(
        self,
        session_id: int,
        channel_id: str,
        from_broadcaster_id: str,
        from_broadcaster_name: str,
        viewers: int,
        occurred_at: datetime,
    ) -> None:
        """Record a raid event."""
        metadata = {
            "viewers": viewers,
            "from_broadcaster_id": from_broadcaster_id,
            "from_broadcaster_name": from_broadcaster_name,
        }
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stream_events
                    (session_id, channel_id, event_type, user_id, username, metadata, occurred_at)
                VALUES ($1, $2, 'raid', $3, $4, $5, $6)
                """,
                session_id,
                channel_id,
                from_broadcaster_id,
                from_broadcaster_name,
                metadata,
                occurred_at,
            )

    # ==================== Chatter stats ====================

    async def flush_chatter_stats(
        self,
        session_id: int,
        channel_id: str,
        chatters: dict[str, dict],
    ) -> None:
        """Batch-insert chatter stats for a completed session.

        Args:
            chatters: {user_id: {"username": str, "display_name": str | None, "count": int, "last_at": datetime}}
        """
        if not chatters:
            return

        rows = [
            (
                session_id,
                channel_id,
                user_id,
                data["username"],
                data.get("display_name"),
                data["count"],
                data["last_at"],
            )
            for user_id, data in chatters.items()
        ]

        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO chatter_stats
                    (session_id, channel_id, user_id, username, display_name, message_count, last_message_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (session_id, user_id) DO UPDATE SET
                    username        = EXCLUDED.username,
                    display_name    = EXCLUDED.display_name,
                    message_count   = EXCLUDED.message_count,
                    last_message_at = EXCLUDED.last_message_at
                """,
                rows,
            )

        LOGGER.info(f"Flushed chatter stats for session {session_id}: {len(rows)} chatters")

    async def increment_watch_seconds(
        self,
        session_id: int,
        channel_id: str,
        viewers: list[dict],
        seconds: int,
    ) -> None:
        """Upsert watch_seconds for all current chatroom viewers.

        Args:
            viewers: list of {"user_id", "user_login", "user_name"} from /helix/chat/chatters
        """
        if not viewers:
            return

        rows = [
            (
                session_id,
                channel_id,
                v["user_id"],
                v["user_login"],
                v.get("user_name"),
                seconds,
            )
            for v in viewers
        ]

        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO chatter_stats
                    (session_id, channel_id, user_id, username, display_name,
                     message_count, watch_seconds, last_message_at)
                VALUES ($1, $2, $3, $4, $5, 0, $6, NOW())
                ON CONFLICT (session_id, user_id) DO UPDATE SET
                    username      = EXCLUDED.username,
                    display_name  = COALESCE(EXCLUDED.display_name, chatter_stats.display_name),
                    watch_seconds = chatter_stats.watch_seconds + EXCLUDED.watch_seconds
                """,
                rows,
            )

    async def _execute_upsert(self, sql: str, *args: object) -> None:
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(sql, *args)
        except UndefinedTableError:
            LOGGER.warning(
                "viewer_channel_status table missing — upsert skipped. Run migration 049."
            )

    async def upsert_viewer_gift_count(
        self,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        total_gifts_given: int,
    ) -> None:
        """Upsert cumulative gift sub count from channel.subscription.gift cumulative_total."""
        await self._execute_upsert(
            """
            INSERT INTO viewer_channel_status
                (channel_id, user_id, username, display_name, total_gifts_given, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (channel_id, user_id) DO UPDATE SET
                username          = EXCLUDED.username,
                display_name      = COALESCE(EXCLUDED.display_name, viewer_channel_status.display_name),
                total_gifts_given = GREATEST(viewer_channel_status.total_gifts_given, EXCLUDED.total_gifts_given),
                updated_at        = NOW()
            """,
            channel_id,
            user_id,
            username,
            display_name,
            total_gifts_given,
        )

    async def upsert_viewer_follow_status(
        self,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        follow_since: datetime,
    ) -> None:
        """Set follow_since on first follow; never overwrites an existing value."""
        await self._execute_upsert(
            """
            INSERT INTO viewer_channel_status
                (channel_id, user_id, username, display_name, follow_since, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (channel_id, user_id) DO UPDATE SET
                username     = EXCLUDED.username,
                display_name = COALESCE(EXCLUDED.display_name, viewer_channel_status.display_name),
                follow_since = COALESCE(viewer_channel_status.follow_since, EXCLUDED.follow_since),
                updated_at   = NOW()
            """,
            channel_id,
            user_id,
            username,
            display_name,
            follow_since,
        )

    async def upsert_viewer_subscription(
        self,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        sub_tier: str | None,
        sub_gifted: bool,
    ) -> None:
        """Mark viewer as currently subscribed.

        sub_gifter is not set here; it is populated only by upsert_viewer_gift_count
        via a separate channel.subscription.gift event.
        """
        await self._execute_upsert(
            """
            INSERT INTO viewer_channel_status
                (channel_id, user_id, username, display_name,
                 is_subscribed, sub_tier, sub_gifted, updated_at)
            VALUES ($1, $2, $3, $4, TRUE, $5, $6, NOW())
            ON CONFLICT (channel_id, user_id) DO UPDATE SET
                username      = EXCLUDED.username,
                display_name  = COALESCE(EXCLUDED.display_name, viewer_channel_status.display_name),
                is_subscribed = TRUE,
                sub_tier      = EXCLUDED.sub_tier,
                sub_gifted    = EXCLUDED.sub_gifted,
                updated_at    = NOW()
            """,
            channel_id,
            user_id,
            username,
            display_name,
            sub_tier,
            sub_gifted,
        )

    async def upsert_viewer_subscription_end(
        self,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
    ) -> None:
        """Mark viewer's subscription as ended."""
        await self._execute_upsert(
            """
            INSERT INTO viewer_channel_status
                (channel_id, user_id, username, display_name,
                 is_subscribed, sub_tier, sub_gifted, sub_gifter, updated_at)
            VALUES ($1, $2, $3, $4, FALSE, NULL, NULL, NULL, NOW())
            ON CONFLICT (channel_id, user_id) DO UPDATE SET
                username      = EXCLUDED.username,
                display_name  = COALESCE(EXCLUDED.display_name, viewer_channel_status.display_name),
                is_subscribed = FALSE,
                sub_tier      = NULL,
                sub_gifted    = NULL,
                sub_gifter    = NULL,
                updated_at    = NOW()
            """,
            channel_id,
            user_id,
            username,
            display_name,
        )

    async def upsert_viewer_mod_status(
        self,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        is_mod: bool,
    ) -> None:
        """Set or clear moderator status."""
        await self._execute_upsert(
            """
            INSERT INTO viewer_channel_status
                (channel_id, user_id, username, display_name, is_mod, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (channel_id, user_id) DO UPDATE SET
                username     = EXCLUDED.username,
                display_name = COALESCE(EXCLUDED.display_name, viewer_channel_status.display_name),
                is_mod       = EXCLUDED.is_mod,
                updated_at   = NOW()
            """,
            channel_id,
            user_id,
            username,
            display_name,
            is_mod,
        )

    async def upsert_viewer_vip_status(
        self,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        is_vip: bool,
    ) -> None:
        """Set or clear VIP status."""
        await self._execute_upsert(
            """
            INSERT INTO viewer_channel_status
                (channel_id, user_id, username, display_name, is_vip, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (channel_id, user_id) DO UPDATE SET
                username     = EXCLUDED.username,
                display_name = COALESCE(EXCLUDED.display_name, viewer_channel_status.display_name),
                is_vip       = EXCLUDED.is_vip,
                updated_at   = NOW()
            """,
            channel_id,
            user_id,
            username,
            display_name,
            is_vip,
        )

    async def upsert_viewer_ban(
        self,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        ban_expires_at: datetime | None,
        ban_reason: str | None,
    ) -> None:
        """Record a ban event."""
        await self._execute_upsert(
            """
            INSERT INTO viewer_channel_status
                (channel_id, user_id, username, display_name,
                 is_banned, ban_expires_at, ban_reason, updated_at)
            VALUES ($1, $2, $3, $4, TRUE, $5, $6, NOW())
            ON CONFLICT (channel_id, user_id) DO UPDATE SET
                username       = EXCLUDED.username,
                display_name   = COALESCE(EXCLUDED.display_name, viewer_channel_status.display_name),
                is_banned      = TRUE,
                ban_expires_at = EXCLUDED.ban_expires_at,
                ban_reason     = EXCLUDED.ban_reason,
                updated_at     = NOW()
            """,
            channel_id,
            user_id,
            username,
            display_name,
            ban_expires_at,
            ban_reason,
        )

    async def upsert_viewer_unban(
        self,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
    ) -> None:
        """Clear ban status on unban."""
        await self._execute_upsert(
            """
            INSERT INTO viewer_channel_status
                (channel_id, user_id, username, display_name,
                 is_banned, ban_expires_at, ban_reason, updated_at)
            VALUES ($1, $2, $3, $4, FALSE, NULL, NULL, NOW())
            ON CONFLICT (channel_id, user_id) DO UPDATE SET
                username       = EXCLUDED.username,
                display_name   = COALESCE(EXCLUDED.display_name, viewer_channel_status.display_name),
                is_banned      = FALSE,
                ban_expires_at = NULL,
                ban_reason     = NULL,
                updated_at     = NOW()
            """,
            channel_id,
            user_id,
            username,
            display_name,
        )

    _TIER_MAP: dict[str, str] = {"1000": "T1", "2000": "T2", "3000": "T3"}

    async def bulk_upsert_mod_status(self, channel_id: str, mods: list[dict]) -> int:
        """Set is_mod=TRUE for every user in *mods*. Returns the count upserted."""
        if not mods:
            return 0
        rows = [(channel_id, m["user_id"], m["user_login"], m.get("user_name")) for m in mods]
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO viewer_channel_status
                        (channel_id, user_id, username, display_name, is_mod, updated_at)
                    VALUES ($1, $2, $3, $4, TRUE, NOW())
                    ON CONFLICT (channel_id, user_id) DO UPDATE SET
                        username     = EXCLUDED.username,
                        display_name = COALESCE(EXCLUDED.display_name,
                                                viewer_channel_status.display_name),
                        is_mod       = TRUE,
                        updated_at   = NOW()
                    """,
                    rows,
                )
        except UndefinedTableError:
            LOGGER.warning("viewer_channel_status table missing — bulk mod upsert skipped.")
            return 0
        return len(rows)

    async def bulk_upsert_vip_status(self, channel_id: str, vips: list[dict]) -> int:
        """Set is_vip=TRUE for every user in *vips*. Returns the count upserted."""
        if not vips:
            return 0
        rows = [(channel_id, v["user_id"], v["user_login"], v.get("user_name")) for v in vips]
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO viewer_channel_status
                        (channel_id, user_id, username, display_name, is_vip, updated_at)
                    VALUES ($1, $2, $3, $4, TRUE, NOW())
                    ON CONFLICT (channel_id, user_id) DO UPDATE SET
                        username     = EXCLUDED.username,
                        display_name = COALESCE(EXCLUDED.display_name,
                                                viewer_channel_status.display_name),
                        is_vip       = TRUE,
                        updated_at   = NOW()
                    """,
                    rows,
                )
        except UndefinedTableError:
            LOGGER.warning("viewer_channel_status table missing — bulk VIP upsert skipped.")
            return 0
        return len(rows)

    async def bulk_upsert_follow_dates(self, channel_id: str, followers: list[dict]) -> int:
        """Write follow_since for all followers, preserving any value already in DB.

        followers: list of {"user_id", "user_login", "user_name", "followed_at" (ISO 8601)}
        Uses COALESCE so existing follow_since is never overwritten.
        """
        if not followers:
            return 0
        rows: list[tuple] = []
        for f in followers:
            try:
                followed_at = datetime.fromisoformat(f["followed_at"].replace("Z", "+00:00"))
            except (ValueError, KeyError):
                continue
            rows.append(
                (
                    channel_id,
                    f["user_id"],
                    f.get("user_login") or "",
                    f.get("user_name"),
                    followed_at,
                )
            )
        if not rows:
            return 0
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO viewer_channel_status
                        (channel_id, user_id, username, display_name, follow_since, updated_at)
                    VALUES ($1, $2, $3, $4, $5, NOW())
                    ON CONFLICT (channel_id, user_id) DO UPDATE SET
                        username     = EXCLUDED.username,
                        display_name = COALESCE(EXCLUDED.display_name,
                                                viewer_channel_status.display_name),
                        follow_since = COALESCE(viewer_channel_status.follow_since,
                                                EXCLUDED.follow_since),
                        updated_at   = NOW()
                    """,
                    rows,
                )
        except UndefinedTableError:
            LOGGER.warning("viewer_channel_status table missing — follow date upsert skipped.")
            return 0
        return len(rows)

    async def bulk_upsert_subscribers(self, channel_id: str, subs: list[dict]) -> int:
        """Set is_subscribed=TRUE for every user in *subs*. Returns the count upserted."""
        if not subs:
            return 0
        rows = [
            (
                channel_id,
                s["user_id"],
                s["user_login"],
                s.get("user_name"),
                self._TIER_MAP.get(s.get("tier", ""), s.get("tier")),
                bool(s.get("is_gift", False)),
            )
            for s in subs
        ]
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO viewer_channel_status
                        (channel_id, user_id, username, display_name,
                         is_subscribed, sub_tier, sub_gifted, updated_at)
                    VALUES ($1, $2, $3, $4, TRUE, $5, $6, NOW())
                    ON CONFLICT (channel_id, user_id) DO UPDATE SET
                        username      = EXCLUDED.username,
                        display_name  = COALESCE(EXCLUDED.display_name,
                                                 viewer_channel_status.display_name),
                        is_subscribed = TRUE,
                        sub_tier      = EXCLUDED.sub_tier,
                        sub_gifted    = EXCLUDED.sub_gifted,
                        updated_at    = NOW()
                    """,
                    rows,
                )
        except UndefinedTableError:
            LOGGER.warning("viewer_channel_status table missing — bulk subscriber upsert skipped.")
            return 0
        return len(rows)

    async def upsert_viewer_profile_cache(
        self,
        channel_id: str,
        user_id: str,
        username: str,
        display_name: str | None,
        profile_image_url: str | None,
        offline_image_url: str | None,
        account_created_at: datetime | None,
        broadcaster_type: str | None,
    ) -> None:
        """Cache Twitch profile fields after a get_user_info call.

        account_created_at uses COALESCE(existing, new) — written once and never
        overwritten, since it is immutable on Twitch's side.
        """
        await self._execute_upsert(
            """
            INSERT INTO viewer_channel_status
                (channel_id, user_id, username, display_name,
                 profile_image_url, offline_image_url,
                 account_created_at, broadcaster_type, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            ON CONFLICT (channel_id, user_id) DO UPDATE SET
                username           = EXCLUDED.username,
                display_name       = COALESCE(EXCLUDED.display_name, viewer_channel_status.display_name),
                profile_image_url  = EXCLUDED.profile_image_url,
                offline_image_url  = EXCLUDED.offline_image_url,
                account_created_at = COALESCE(viewer_channel_status.account_created_at, EXCLUDED.account_created_at),
                broadcaster_type   = EXCLUDED.broadcaster_type,
                updated_at         = NOW()
            """,
            channel_id,
            user_id,
            username,
            display_name,
            profile_image_url,
            offline_image_url,
            account_created_at,
            broadcaster_type,
        )
