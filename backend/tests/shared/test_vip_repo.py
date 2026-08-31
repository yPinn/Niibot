"""Persistence contracts for tenant-scoped timed VIP management."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.models.vip import VipRedemptionStatus, VipSnapshotMember
from shared.repositories.vip import VipRepository

_NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)


def _pool() -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    transaction = MagicMock()
    transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    transaction.return_value.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = transaction
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _settings_row() -> dict:
    return {
        "channel_id": "ch1",
        "slot_limit": 25,
        "tracking_started_at": None,
        "last_full_sync_at": None,
        "created_at": _NOW,
        "updated_at": _NOW,
    }


def _receipt_row() -> dict:
    return {
        "id": 8,
        "channel_id": "ch1",
        "redemption_id": "redemption-1",
        "rule_id": 3,
        "reward_id": "reward-1",
        "reward_name_snapshot": "VIP 三個月",
        "user_id": "u1",
        "user_login": "alice",
        "display_name": "Alice",
        "duration_months_snapshot": 3,
        "is_permanent_snapshot": False,
        "status": "received",
        "error_code": None,
        "occurred_at": _NOW,
        "processed_at": None,
        "created_at": _NOW,
    }


@pytest.mark.asyncio
class TestVipRepository:
    async def test_get_or_create_settings_is_channel_scoped(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = _settings_row()
        repo = VipRepository(pool)

        settings = await repo.get_or_create_settings("ch1")

        assert settings.channel_id == "ch1"
        assert "ON CONFLICT (channel_id)" in conn.execute.await_args.args[0]
        assert "WHERE channel_id = $1" in conn.fetchrow.await_args.args[0]
        assert conn.fetchrow.await_args.args[1] == "ch1"

    async def test_record_redemption_is_idempotent_per_channel(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = _receipt_row()
        repo = VipRepository(pool)

        receipt = await repo.record_redemption(
            channel_id="ch1",
            redemption_id="redemption-1",
            rule_id=3,
            reward_id="reward-1",
            reward_name="VIP 三個月",
            user_id="u1",
            user_login="alice",
            display_name="Alice",
            duration_months=3,
            is_permanent=False,
            occurred_at=_NOW,
        )

        sql = conn.fetchrow.await_args.args[0]
        assert "ON CONFLICT (channel_id, redemption_id)" in sql
        assert "WHERE vip_redemption_events.channel_id = $1" in sql
        assert receipt.status is VipRedemptionStatus.RECEIVED

    async def test_list_reward_rules_filters_by_channel(self):
        pool, conn = _pool()
        conn.fetch.return_value = []
        repo = VipRepository(pool)

        assert await repo.list_reward_rules("ch1") == ()

        sql, channel_id = conn.fetch.await_args.args
        assert "WHERE channel_id = $1" in sql
        assert channel_id == "ch1"

    async def test_claim_due_entitlements_is_bounded_and_locked(self):
        pool, conn = _pool()
        conn.fetch.return_value = []
        repo = VipRepository(pool)

        assert await repo.claim_due_entitlements(now=_NOW, limit=50) == ()

        sql, now, limit = conn.fetch.await_args.args
        assert "status = 'active'" in sql
        assert "source = 'managed'" in sql
        assert "FOR UPDATE SKIP LOCKED" in sql
        assert "UPDATE vip_entitlements" in sql
        assert "expiry_claimed_at" in sql
        assert now == _NOW
        assert limit == 50

    async def test_claim_due_entitlements_rejects_unbounded_limit(self):
        repo = VipRepository(MagicMock())

        with pytest.raises(ValueError, match="between 1 and 500"):
            await repo.claim_due_entitlements(now=_NOW, limit=501)

    async def test_reconcile_treats_readded_inactive_managed_vip_as_external(self):
        pool, conn = _pool()
        repo = VipRepository(pool)

        await repo.reconcile_snapshot(
            channel_id="ch1",
            members=(VipSnapshotMember("u1", "alice", "Alice"),),
            synced_at=_NOW,
        )

        insert_sql = conn.execute.await_args_list[0].args[0]
        assert "vip_entitlements.status = 'active'" in insert_sql
        assert "ELSE EXCLUDED.source" in insert_sql
        assert conn.execute.await_args_list[0].args[5] == "external_event"

    async def test_event_removal_marks_claimed_expiry_as_expired(self):
        pool, conn = _pool()
        repo = VipRepository(pool)

        await repo.mark_removed_external(channel_id="ch1", user_id="u1", synced_at=_NOW)

        sql = conn.execute.await_args.args[0]
        assert "expiry_claimed_at IS NOT NULL" in sql
        assert "THEN 'expired'" in sql
