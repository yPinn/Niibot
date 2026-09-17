"""Persistence for tenant-scoped timed VIP rules and entitlement state."""

from __future__ import annotations

from datetime import datetime

import asyncpg

from shared.models.vip import (
    VipChannelSettings,
    VipEntitlement,
    VipEntitlementSource,
    VipEntitlementStatus,
    VipRedemptionEvent,
    VipRedemptionStatus,
    VipRewardRule,
    VipSnapshotMember,
)

_SETTINGS_COLUMNS = (
    "channel_id, slot_limit, tracking_started_at, last_full_sync_at, created_at, updated_at"
)
_RULE_COLUMNS = (
    "id, channel_id, reward_id, reward_name_snapshot, duration_months, is_permanent, "
    "enabled, created_at, updated_at"
)
_ENTITLEMENT_COLUMNS = (
    "id, channel_id, user_id, user_login, display_name, source, status, granted_at, "
    "expires_at, is_permanent, last_reward_rule_id, last_synced_at, expiry_claimed_at, "
    "version, created_at, updated_at"
)
_EVENT_COLUMNS = (
    "id, channel_id, redemption_id, rule_id, reward_id, reward_name_snapshot, user_id, "
    "user_login, display_name, duration_months_snapshot, is_permanent_snapshot, status, "
    "error_code, occurred_at, processed_at, created_at"
)


def _rule(row: asyncpg.Record) -> VipRewardRule:
    return VipRewardRule(**dict(row))


def _entitlement(row: asyncpg.Record) -> VipEntitlement:
    values = dict(row)
    values["source"] = VipEntitlementSource(values["source"])
    values["status"] = VipEntitlementStatus(values["status"])
    return VipEntitlement(**values)


def _event(row: asyncpg.Record) -> VipRedemptionEvent:
    values = dict(row)
    values["status"] = VipRedemptionStatus(values["status"])
    return VipRedemptionEvent(**values)


class VipRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_or_create_settings(self, channel_id: str) -> VipChannelSettings:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO vip_channel_settings (channel_id) VALUES ($1) "
                    "ON CONFLICT (channel_id) DO NOTHING",
                    channel_id,
                )
                row = await conn.fetchrow(
                    f"SELECT {_SETTINGS_COLUMNS} FROM vip_channel_settings WHERE channel_id = $1",
                    channel_id,
                )
        if row is None:
            raise RuntimeError(f"Failed to load VIP settings for channel {channel_id}")
        return VipChannelSettings(**dict(row))

    async def update_slot_limit(self, *, channel_id: str, slot_limit: int) -> VipChannelSettings:
        if not 1 <= slot_limit <= 500:
            raise ValueError("slot_limit must be between 1 and 500")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO vip_channel_settings (channel_id, slot_limit)
                VALUES ($1, $2)
                ON CONFLICT (channel_id) DO UPDATE SET
                    slot_limit = EXCLUDED.slot_limit,
                    updated_at = NOW()
                RETURNING {_SETTINGS_COLUMNS}
                """,
                channel_id,
                slot_limit,
            )
        if row is None:
            raise RuntimeError(f"Failed to update VIP settings for channel {channel_id}")
        return VipChannelSettings(**dict(row))

    async def list_reward_rules(self, channel_id: str) -> tuple[VipRewardRule, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_RULE_COLUMNS} FROM vip_reward_rules WHERE channel_id = $1 ORDER BY id",
                channel_id,
            )
        return tuple(_rule(row) for row in rows)

    async def get_reward_rule(self, *, channel_id: str, reward_id: str) -> VipRewardRule | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_RULE_COLUMNS} FROM vip_reward_rules "
                "WHERE channel_id = $1 AND reward_id = $2",
                channel_id,
                reward_id,
            )
        return _rule(row) if row is not None else None

    async def set_rules_enabled(
        self, *, channel_id: str, enabled: bool
    ) -> tuple[VipRewardRule, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                UPDATE vip_reward_rules
                SET enabled = $2, updated_at = NOW()
                WHERE channel_id = $1
                RETURNING {_RULE_COLUMNS}
                """,
                channel_id,
                enabled,
            )
        return tuple(_rule(row) for row in rows)

    async def upsert_reward_rule(self, rule: VipRewardRule) -> VipRewardRule:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO vip_reward_rules
                    (channel_id, reward_id, reward_name_snapshot, duration_months,
                     is_permanent, enabled)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (channel_id, reward_id) DO UPDATE SET
                    reward_name_snapshot = EXCLUDED.reward_name_snapshot,
                    duration_months = EXCLUDED.duration_months,
                    is_permanent = EXCLUDED.is_permanent,
                    enabled = EXCLUDED.enabled,
                    updated_at = NOW()
                RETURNING {_RULE_COLUMNS}
                """,
                rule.channel_id,
                rule.reward_id,
                rule.reward_name_snapshot,
                rule.duration_months,
                rule.is_permanent,
                rule.enabled,
            )
        if row is None:
            raise RuntimeError("Failed to upsert VIP reward rule")
        return _rule(row)

    async def get_entitlement(self, *, channel_id: str, user_id: str) -> VipEntitlement | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_ENTITLEMENT_COLUMNS} FROM vip_entitlements "
                "WHERE channel_id = $1 AND user_id = $2",
                channel_id,
                user_id,
            )
        return _entitlement(row) if row is not None else None

    async def mark_removed_external(
        self, *, channel_id: str, user_id: str, synced_at: datetime
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE vip_entitlements
                SET status = CASE
                        WHEN expiry_claimed_at IS NOT NULL THEN 'expired'
                        ELSE 'removed_external'
                    END,
                    expiry_claimed_at = NULL,
                    last_synced_at = $3,
                    version = version + 1,
                    updated_at = NOW()
                WHERE channel_id = $1 AND user_id = $2 AND status = 'active'
                """,
                channel_id,
                user_id,
                synced_at,
            )

    async def observe_vip_added(
        self,
        *,
        channel_id: str,
        member: VipSnapshotMember,
        observed_at: datetime,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO vip_entitlements
                    (channel_id, user_id, user_login, display_name, source, status,
                     last_synced_at)
                VALUES ($1, $2, $3, $4, 'external_event', 'active', $5)
                ON CONFLICT (channel_id, user_id) DO UPDATE SET
                    user_login = EXCLUDED.user_login,
                    display_name = EXCLUDED.display_name,
                    source = CASE
                        WHEN vip_entitlements.source = 'managed'
                             AND vip_entitlements.status = 'active' THEN 'managed'
                        WHEN vip_entitlements.status = 'active' THEN vip_entitlements.source
                        ELSE 'external_event'
                    END,
                    status = 'active',
                    granted_at = CASE
                        WHEN vip_entitlements.source = 'managed'
                             AND vip_entitlements.status = 'active'
                            THEN vip_entitlements.granted_at
                        ELSE NULL
                    END,
                    expires_at = CASE
                        WHEN vip_entitlements.source = 'managed'
                             AND vip_entitlements.status = 'active'
                            THEN vip_entitlements.expires_at
                        ELSE NULL
                    END,
                    is_permanent = CASE
                        WHEN vip_entitlements.source = 'managed'
                             AND vip_entitlements.status = 'active'
                            THEN vip_entitlements.is_permanent
                        ELSE FALSE
                    END,
                    last_synced_at = EXCLUDED.last_synced_at,
                    expiry_claimed_at = NULL,
                    version = vip_entitlements.version + 1,
                    updated_at = NOW()
                """,
                channel_id,
                member.user_id,
                member.user_login,
                member.display_name,
                observed_at,
            )

    async def count_active(self, channel_id: str) -> int:
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT COUNT(*) FROM vip_entitlements WHERE channel_id = $1 AND status = 'active'",
                channel_id,
            )
        return int(value or 0)

    async def list_entitlements(self, channel_id: str) -> tuple[VipEntitlement, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_ENTITLEMENT_COLUMNS} FROM vip_entitlements "
                "WHERE channel_id = $1 ORDER BY status, expires_at NULLS LAST, user_login",
                channel_id,
            )
        return tuple(_entitlement(row) for row in rows)

    async def initialize_snapshot(
        self,
        *,
        channel_id: str,
        slot_limit: int,
        members: tuple[VipSnapshotMember, ...],
        synced_at: datetime,
    ) -> VipChannelSettings:
        if not 1 <= slot_limit <= 500:
            raise ValueError("slot_limit must be between 1 and 500")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await self._reconcile_members(
                    conn,
                    channel_id=channel_id,
                    members=members,
                    synced_at=synced_at,
                    new_source=VipEntitlementSource.EXTERNAL_BASELINE,
                )
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO vip_channel_settings
                        (channel_id, slot_limit, tracking_started_at, last_full_sync_at)
                    VALUES ($1, $2, $3, $3)
                    ON CONFLICT (channel_id) DO UPDATE SET
                        slot_limit = EXCLUDED.slot_limit,
                        tracking_started_at = COALESCE(
                            vip_channel_settings.tracking_started_at,
                            EXCLUDED.tracking_started_at
                        ),
                        last_full_sync_at = EXCLUDED.last_full_sync_at,
                        updated_at = NOW()
                    RETURNING {_SETTINGS_COLUMNS}
                    """,
                    channel_id,
                    slot_limit,
                    synced_at,
                )
        if row is None:
            raise RuntimeError("Failed to initialize VIP tracking")
        return VipChannelSettings(**dict(row))

    async def reconcile_snapshot(
        self,
        *,
        channel_id: str,
        members: tuple[VipSnapshotMember, ...],
        synced_at: datetime,
    ) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await self._reconcile_members(
                    conn,
                    channel_id=channel_id,
                    members=members,
                    synced_at=synced_at,
                    new_source=VipEntitlementSource.EXTERNAL_EVENT,
                )
                await conn.execute(
                    "UPDATE vip_channel_settings SET last_full_sync_at = $2, updated_at = NOW() "
                    "WHERE channel_id = $1",
                    channel_id,
                    synced_at,
                )

    @staticmethod
    async def _reconcile_members(
        conn: asyncpg.Connection,
        *,
        channel_id: str,
        members: tuple[VipSnapshotMember, ...],
        synced_at: datetime,
        new_source: VipEntitlementSource,
    ) -> None:
        member_ids = [member.user_id for member in members]
        for member in members:
            await conn.execute(
                """
                INSERT INTO vip_entitlements
                    (channel_id, user_id, user_login, display_name, source, status,
                     last_synced_at)
                VALUES ($1, $2, $3, $4, $5, 'active', $6)
                ON CONFLICT (channel_id, user_id) DO UPDATE SET
                    user_login = EXCLUDED.user_login,
                    display_name = EXCLUDED.display_name,
                    source = CASE
                        WHEN vip_entitlements.source = 'managed'
                             AND vip_entitlements.status = 'active' THEN 'managed'
                        WHEN vip_entitlements.status = 'active' THEN vip_entitlements.source
                        ELSE EXCLUDED.source
                    END,
                    status = 'active',
                    granted_at = CASE
                        WHEN vip_entitlements.source = 'managed'
                             AND vip_entitlements.status = 'active'
                            THEN vip_entitlements.granted_at
                        ELSE NULL
                    END,
                    expires_at = CASE
                        WHEN vip_entitlements.source = 'managed'
                             AND vip_entitlements.status = 'active'
                            THEN vip_entitlements.expires_at
                        ELSE NULL
                    END,
                    is_permanent = CASE
                        WHEN vip_entitlements.source = 'managed'
                             AND vip_entitlements.status = 'active'
                            THEN vip_entitlements.is_permanent
                        ELSE FALSE
                    END,
                    last_synced_at = EXCLUDED.last_synced_at,
                    expiry_claimed_at = NULL,
                    version = vip_entitlements.version + 1,
                    updated_at = NOW()
                """,
                channel_id,
                member.user_id,
                member.user_login,
                member.display_name,
                new_source.value,
                synced_at,
            )

        await conn.execute(
            """
            UPDATE vip_entitlements
            SET status = 'removed_external',
                expiry_claimed_at = NULL,
                last_synced_at = $3,
                version = version + 1,
                updated_at = NOW()
            WHERE channel_id = $1
              AND status = 'active'
              AND NOT (user_id = ANY($2::TEXT[]))
            """,
            channel_id,
            member_ids,
            synced_at,
        )

    async def apply_managed_entitlement(
        self,
        *,
        channel_id: str,
        user_id: str,
        user_login: str,
        display_name: str | None,
        granted_at: datetime,
        expires_at: datetime | None,
        is_permanent: bool,
        reward_rule_id: int,
        synced_at: datetime,
    ) -> VipEntitlement:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO vip_entitlements
                    (channel_id, user_id, user_login, display_name, source, status,
                     granted_at, expires_at, is_permanent, last_reward_rule_id,
                     last_synced_at)
                VALUES ($1, $2, $3, $4, 'managed', 'active', $5, $6, $7, $8, $9)
                ON CONFLICT (channel_id, user_id) DO UPDATE SET
                    user_login = EXCLUDED.user_login,
                    display_name = EXCLUDED.display_name,
                    source = 'managed',
                    status = 'active',
                    granted_at = EXCLUDED.granted_at,
                    expires_at = EXCLUDED.expires_at,
                    is_permanent = EXCLUDED.is_permanent,
                    last_reward_rule_id = EXCLUDED.last_reward_rule_id,
                    last_synced_at = EXCLUDED.last_synced_at,
                    expiry_claimed_at = NULL,
                    version = vip_entitlements.version + 1,
                    updated_at = NOW()
                RETURNING {_ENTITLEMENT_COLUMNS}
                """,
                channel_id,
                user_id,
                user_login,
                display_name,
                granted_at,
                expires_at,
                is_permanent,
                reward_rule_id,
                synced_at,
            )
        if row is None:
            raise RuntimeError("Failed to persist managed VIP entitlement")
        return _entitlement(row)

    async def record_redemption(
        self,
        *,
        channel_id: str,
        redemption_id: str,
        rule_id: int | None,
        reward_id: str,
        reward_name: str,
        user_id: str,
        user_login: str,
        display_name: str | None,
        duration_months: int | None,
        is_permanent: bool,
        occurred_at: datetime,
    ) -> VipRedemptionEvent:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                WITH inserted AS (
                    INSERT INTO vip_redemption_events
                        (channel_id, redemption_id, rule_id, reward_id,
                         reward_name_snapshot, user_id, user_login, display_name,
                         duration_months_snapshot, is_permanent_snapshot, occurred_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (channel_id, redemption_id) DO NOTHING
                    RETURNING {_EVENT_COLUMNS}
                )
                SELECT {_EVENT_COLUMNS} FROM inserted
                UNION ALL
                SELECT {_EVENT_COLUMNS} FROM vip_redemption_events
                WHERE vip_redemption_events.channel_id = $1
                  AND vip_redemption_events.redemption_id = $2
                LIMIT 1
                """,
                channel_id,
                redemption_id,
                rule_id,
                reward_id,
                reward_name,
                user_id,
                user_login,
                display_name,
                duration_months,
                is_permanent,
                occurred_at,
            )
        if row is None:
            raise RuntimeError("Failed to record VIP redemption")
        return _event(row)

    async def get_redemption(
        self, *, channel_id: str, redemption_id: str
    ) -> VipRedemptionEvent | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_EVENT_COLUMNS} FROM vip_redemption_events "
                "WHERE channel_id = $1 AND redemption_id = $2",
                channel_id,
                redemption_id,
            )
        return _event(row) if row is not None else None

    async def list_redemptions(
        self, channel_id: str, *, limit: int = 100
    ) -> tuple[VipRedemptionEvent, ...]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_EVENT_COLUMNS} FROM vip_redemption_events "
                "WHERE channel_id = $1 ORDER BY occurred_at DESC, id DESC LIMIT $2",
                channel_id,
                limit,
            )
        return tuple(_event(row) for row in rows)

    async def list_stale_granting(
        self, *, now: datetime, limit: int = 50
    ) -> tuple[VipRedemptionEvent, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_EVENT_COLUMNS} FROM vip_redemption_events "
                "WHERE status = 'granting' "
                "AND processed_at < $1::timestamptz - INTERVAL '1 minute' "
                "ORDER BY processed_at, id LIMIT $2",
                now,
                limit,
            )
        return tuple(_event(row) for row in rows)

    async def transition_redemption(
        self,
        *,
        channel_id: str,
        redemption_id: str,
        status: VipRedemptionStatus,
        error_code: str | None,
    ) -> None:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE vip_redemption_events
                SET status = $3,
                    error_code = $4,
                    processed_at = NOW()
                WHERE channel_id = $1 AND redemption_id = $2
                """,
                channel_id,
                redemption_id,
                status.value,
                error_code,
            )
        if result == "UPDATE 0":
            raise RuntimeError("VIP redemption receipt was not found")

    async def finish_expiry(
        self,
        *,
        channel_id: str,
        entitlement_id: int,
        removed_at: datetime,
        externally_removed: bool,
    ) -> None:
        status = (
            VipEntitlementStatus.REMOVED_EXTERNAL
            if externally_removed
            else VipEntitlementStatus.EXPIRED
        )
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE vip_entitlements
                SET status = $3,
                    expiry_claimed_at = NULL,
                    last_synced_at = $4,
                    version = version + 1,
                    updated_at = NOW()
                WHERE channel_id = $1 AND id = $2
                  AND status = 'active' AND source = 'managed'
                """,
                channel_id,
                entitlement_id,
                status.value,
                removed_at,
            )

    async def release_expiry_claim(self, *, channel_id: str, entitlement_id: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE vip_entitlements
                SET expiry_claimed_at = NULL,
                    version = version + 1,
                    updated_at = NOW()
                WHERE channel_id = $1 AND id = $2 AND status = 'active'
                """,
                channel_id,
                entitlement_id,
            )

    async def claim_due_entitlements(
        self, *, now: datetime, limit: int = 100
    ) -> tuple[VipEntitlement, ...]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                WITH due AS (
                    SELECT id
                    FROM vip_entitlements
                    WHERE status = 'active'
                      AND source = 'managed'
                      AND NOT is_permanent
                      AND expires_at <= $1
                      AND (expiry_claimed_at IS NULL OR expiry_claimed_at < $1 - INTERVAL '10 minutes')
                    ORDER BY expires_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT $2
                )
                UPDATE vip_entitlements AS entitlement
                SET expiry_claimed_at = $1,
                    version = entitlement.version + 1,
                    updated_at = NOW()
                FROM due
                WHERE entitlement.id = due.id
                RETURNING {", ".join(f"entitlement.{column.strip()}" for column in _ENTITLEMENT_COLUMNS.split(","))}
                """,
                now,
                limit,
            )
        return tuple(_entitlement(row) for row in rows)
