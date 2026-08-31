"""Typed records for tenant-scoped timed VIP management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class VipEntitlementSource(StrEnum):
    EXTERNAL_BASELINE = "external_baseline"
    EXTERNAL_EVENT = "external_event"
    MANAGED = "managed"


class VipEntitlementStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REMOVED_EXTERNAL = "removed_external"
    RELEASED = "released"


class VipRedemptionStatus(StrEnum):
    RECEIVED = "received"
    GRANTING = "granting"
    GRANTED = "granted"
    EXTENDED = "extended"
    ADOPTED = "adopted"
    KEPT_EXTERNAL = "kept_external"
    NEEDS_REVIEW_EXTERNAL_VIP = "needs_review_external_vip"
    CAPACITY_FULL = "capacity_full"
    MODERATOR_CONFLICT = "moderator_conflict"
    NOT_INITIALIZED = "not_initialized"
    FAILED = "failed"


class VipRedemptionDecision(StrEnum):
    GRANT = "grant"
    EXTEND = "extend"
    NEEDS_REVIEW = "needs_review"
    NOOP_PERMANENT = "noop_permanent"


@dataclass(frozen=True, slots=True)
class VipChannelSettings:
    channel_id: str
    slot_limit: int | None
    tracking_started_at: datetime | None
    last_full_sync_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class VipRewardRule:
    id: int | None
    channel_id: str
    reward_id: str
    reward_name_snapshot: str
    duration_months: int | None
    is_permanent: bool
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class VipEntitlement:
    id: int
    channel_id: str
    user_id: str
    user_login: str
    display_name: str | None
    source: VipEntitlementSource
    status: VipEntitlementStatus
    granted_at: datetime | None
    expires_at: datetime | None
    is_permanent: bool
    last_reward_rule_id: int | None
    last_synced_at: datetime
    expiry_claimed_at: datetime | None = None
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class VipRedemptionEvent:
    id: int
    channel_id: str
    redemption_id: str
    rule_id: int | None
    reward_id: str
    reward_name_snapshot: str
    user_id: str
    user_login: str
    display_name: str | None
    duration_months_snapshot: int | None
    is_permanent_snapshot: bool
    status: VipRedemptionStatus
    error_code: str | None
    occurred_at: datetime
    processed_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class VipRedemptionPlan:
    action: VipRedemptionDecision
    granted_at: datetime
    expires_at: datetime | None
    is_permanent: bool


@dataclass(frozen=True, slots=True)
class VipSnapshotMember:
    user_id: str
    user_login: str
    display_name: str | None


@dataclass(frozen=True, slots=True)
class VipDashboardState:
    settings: VipChannelSettings
    rules: tuple[VipRewardRule, ...]
    entitlements: tuple[VipEntitlement, ...]
    redemptions: tuple[VipRedemptionEvent, ...]
