"""AdmissionService — owns membership state transitions.

State machine (memberships.status):

    [NONE]
       |
       v
    pending  --(approve / OTP)--> active  --(suspend)--> suspended
       |                                       ^
       v                                       |
    rejected --(re-request)--> pending --(reinstate)--+

Every state change emits a matching membership_events row inside the same
transaction so audit log and state can never disagree.

Idempotency: ensure_pending and reapply are safe to call repeatedly; they
short-circuit when the membership is already active. Owner-initiated
approve/reject require a reason argument so operator decisions are
attributable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import asyncpg

from shared.repositories.activation_code import ActivationCodeRepository
from shared.repositories.membership import (
    Membership,
    MembershipEvent,
    MembershipRepository,
)

LOGGER: logging.Logger = logging.getLogger(__name__)

# Operator decisions the system must never silently override.
_LOCKED_STATUSES = ("suspended", "rejected")


@dataclass(frozen=True)
class AdmissionDecision:
    membership: Membership
    event_id: int
    state_changed: bool


class MembershipLockedError(Exception):
    """A system activation was attempted on an operator-locked membership.

    Raised by grant_via_otp when the membership is suspended or rejected so a
    router transaction that already consumed a code rolls the consumption back.
    """

    def __init__(self, user_id: str, status: str) -> None:
        super().__init__(f"membership {user_id} is {status} — needs operator reinstate")
        self.user_id = user_id
        self.status = status


class AdmissionService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.repo = MembershipRepository(pool)
        self.grants = ActivationCodeRepository(pool)

    # ------------------------------------------------------------------
    # User-initiated actions
    # ------------------------------------------------------------------

    async def ensure_pending(
        self,
        user_id: str,
        *,
        reason: str = "first_signup",
        metadata: dict[str, Any] | None = None,
    ) -> AdmissionDecision:
        """Idempotently put the user into a pending state.

        Called from the OAuth callback for genuinely-new users. If the user
        has ANY existing membership row this is a no-op — including 'pending'
        (calling again must NOT create a duplicate 'requested' event, which
        would re-trigger the very bug this refactor removes).
        """
        current = await self.repo.get(user_id)
        if current is not None:
            return AdmissionDecision(
                membership=current,
                event_id=0,
                state_changed=False,
            )

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                membership = await self.repo.upsert_status(
                    user_id,
                    "pending",
                    reason=reason,
                    conn=conn,
                )
                event_id = await self.repo.insert_event(
                    user_id,
                    "requested",
                    actor_type="system",
                    reason=reason,
                    metadata=metadata,
                    conn=conn,
                )
        return AdmissionDecision(membership=membership, event_id=event_id, state_changed=True)

    async def reapply(self, user_id: str) -> AdmissionDecision:
        """User explicitly re-requests admission after a rejection.

        No-op if the user is already pending or active.
        """
        current = await self.repo.get(user_id)
        if current and current.status in ("pending", "active"):
            return AdmissionDecision(membership=current, event_id=0, state_changed=False)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                membership = await self.repo.upsert_status(
                    user_id,
                    "pending",
                    reason="user_reapply",
                    conn=conn,
                )
                event_id = await self.repo.insert_event(
                    user_id,
                    "requested",
                    actor_type="user",
                    reason="reapply_after_reject",
                    conn=conn,
                )
        return AdmissionDecision(membership=membership, event_id=event_id, state_changed=True)

    async def withdraw(self, user_id: str) -> AdmissionDecision:
        """User voluntarily withdraws their pending request."""
        current = await self.repo.get(user_id)
        if not current or current.status != "pending":
            raise ValueError(f"Cannot withdraw membership in status {current and current.status}")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                membership = await self.repo.upsert_status(
                    user_id,
                    "rejected",
                    reason="user_withdrew",
                    conn=conn,
                )
                event_id = await self.repo.insert_event(
                    user_id,
                    "withdrawn",
                    actor_type="user",
                    conn=conn,
                )
        return AdmissionDecision(membership=membership, event_id=event_id, state_changed=True)

    # ------------------------------------------------------------------
    # System actions (OTP / auto-admit)
    # ------------------------------------------------------------------

    async def auto_admit(
        self,
        user_id: str,
        *,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> AdmissionDecision:
        """System grants admission without owner involvement.

        Used for the bot owner (auto-activated by config) and for any future
        auto-admission rules. Idempotent if already active.
        """
        current = await self.repo.get(user_id)
        if current and current.status == "active":
            return AdmissionDecision(membership=current, event_id=0, state_changed=False)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                membership = await self.repo.upsert_status(
                    user_id,
                    "active",
                    reason=reason,
                    conn=conn,
                )
                event_id = await self.repo.insert_event(
                    user_id,
                    "auto_admitted",
                    actor_type="system",
                    reason=reason,
                    metadata=metadata,
                    conn=conn,
                )
        return AdmissionDecision(membership=membership, event_id=event_id, state_changed=True)

    async def _activate_system(
        self,
        user_id: str,
        *,
        event_type: str,
        reason: str,
        metadata: dict[str, Any],
        conn: asyncpg.Connection | None = None,
    ) -> AdmissionDecision:
        """UPSERT active + append a system event, on a shared or own transaction."""

        async def _run(c: asyncpg.Connection) -> AdmissionDecision:
            membership = await self.repo.upsert_status(user_id, "active", reason=reason, conn=c)
            event_id = await self.repo.insert_event(
                user_id,
                event_type,  # type: ignore[arg-type]
                actor_type="system",
                reason=reason,
                metadata=metadata,
                conn=c,
            )
            return AdmissionDecision(membership=membership, event_id=event_id, state_changed=True)

        if conn is not None:
            return await _run(conn)
        async with self.pool.acquire() as own:
            async with own.transaction():
                return await _run(own)

    async def grant_via_otp(
        self,
        user_id: str,
        *,
        platform: str,
        platform_user_id: str,
        code_hash: str,
        conn: asyncpg.Connection | None = None,
    ) -> AdmissionDecision:
        """Activate a membership in response to an owner_manual code redemption.

        Caller is expected to have already validated + consumed the code
        (ActivationCodeRepository.redeem). Pass ``conn`` to fold this into the
        same transaction as that consumption. Raises MembershipLockedError if
        the membership is suspended/rejected, so the caller's transaction (and
        the code consumption in it) rolls back.
        """
        current = await self.repo.get(user_id)
        if current and current.status == "active":
            return AdmissionDecision(membership=current, event_id=0, state_changed=False)
        if current and current.status in _LOCKED_STATUSES:
            raise MembershipLockedError(user_id, current.status)

        return await self._activate_system(
            user_id,
            event_type="approved",
            reason="otp_redeem",
            metadata={
                "platform": platform,
                "platform_user_id": platform_user_id,
                "code_hash": code_hash,
            },
            conn=conn,
        )

    async def activate_if_entitled(
        self,
        user_id: str,
        *,
        platform: str,
        platform_user_id: str,
    ) -> bool:
        """OAuth-callback path: consume a channel-points grant and activate.

        Returns True iff the user ends up active. No-op (False) when there is no
        live grant for this identity, or when the membership is operator-locked
        (suspended / rejected — those need an explicit reinstate). An already-
        active user still has any dangling grant consumed so the funnel is
        accurate. Never creates a pending row.
        """
        current = await self.repo.get(user_id)
        if current and current.status in _LOCKED_STATUSES:
            return False

        grant = await self.grants.find_unconsumed_grant(platform, platform_user_id)

        if current and current.status == "active":
            if grant is not None:
                await self.grants.consume(grant["id"], user_id)
            return True

        if grant is None:
            return False

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await self.grants.consume(grant["id"], user_id, conn=conn)
                await self._activate_system(
                    user_id,
                    event_type="auto_admitted",
                    reason="channel_points_redeem",
                    metadata={
                        "platform": platform,
                        "platform_user_id": platform_user_id,
                        "grant_id": grant["id"],
                        "redemption_id": grant["redemption_id"],
                        "channel_id": grant["channel_id"],
                        "reward_cost": grant["reward_cost"],
                    },
                    conn=conn,
                )
        return True

    # ------------------------------------------------------------------
    # Owner / admin actions
    # ------------------------------------------------------------------

    async def approve(
        self,
        user_id: str,
        *,
        approver_user_id: str,
        reason: str,
    ) -> AdmissionDecision:
        """Owner approves a pending membership."""
        current = await self.repo.get(user_id)
        if current is None:
            raise ValueError(f"No membership exists for user {user_id}")
        if current.status == "active":
            return AdmissionDecision(membership=current, event_id=0, state_changed=False)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                membership = await self.repo.upsert_status(
                    user_id,
                    "active",
                    granted_by=approver_user_id,
                    reason=reason,
                    conn=conn,
                )
                event_id = await self.repo.insert_event(
                    user_id,
                    "approved",
                    actor_type="owner",
                    actor_user_id=approver_user_id,
                    reason=reason,
                    conn=conn,
                )
        return AdmissionDecision(membership=membership, event_id=event_id, state_changed=True)

    async def reject(
        self,
        user_id: str,
        *,
        approver_user_id: str,
        reason: str,
    ) -> AdmissionDecision:
        """Owner rejects a pending membership."""
        current = await self.repo.get(user_id)
        if current is None:
            raise ValueError(f"No membership exists for user {user_id}")
        if current.status == "rejected":
            return AdmissionDecision(membership=current, event_id=0, state_changed=False)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                membership = await self.repo.upsert_status(
                    user_id,
                    "rejected",
                    reason=reason,
                    conn=conn,
                )
                event_id = await self.repo.insert_event(
                    user_id,
                    "rejected",
                    actor_type="owner",
                    actor_user_id=approver_user_id,
                    reason=reason,
                    conn=conn,
                )
        return AdmissionDecision(membership=membership, event_id=event_id, state_changed=True)

    async def suspend(
        self,
        user_id: str,
        *,
        approver_user_id: str,
        reason: str,
    ) -> AdmissionDecision:
        current = await self.repo.get(user_id)
        if current is None:
            raise ValueError(f"No membership exists for user {user_id}")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                membership = await self.repo.upsert_status(
                    user_id,
                    "suspended",
                    reason=reason,
                    conn=conn,
                )
                event_id = await self.repo.insert_event(
                    user_id,
                    "suspended",
                    actor_type="owner",
                    actor_user_id=approver_user_id,
                    reason=reason,
                    conn=conn,
                )
        return AdmissionDecision(membership=membership, event_id=event_id, state_changed=True)

    async def reinstate(
        self,
        user_id: str,
        *,
        approver_user_id: str,
        reason: str,
    ) -> AdmissionDecision:
        current = await self.repo.get(user_id)
        if current is None:
            raise ValueError(f"No membership exists for user {user_id}")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                membership = await self.repo.upsert_status(
                    user_id,
                    "active",
                    granted_by=approver_user_id,
                    reason=reason,
                    conn=conn,
                )
                event_id = await self.repo.insert_event(
                    user_id,
                    "reinstated",
                    actor_type="owner",
                    actor_user_id=approver_user_id,
                    reason=reason,
                    conn=conn,
                )
        return AdmissionDecision(membership=membership, event_id=event_id, state_changed=True)

    # ------------------------------------------------------------------
    # Read-side helpers (admin UI / dashboard)
    # ------------------------------------------------------------------

    async def get(self, user_id: str) -> Membership | None:
        return await self.repo.get(user_id)

    async def is_active(self, user_id: str) -> bool:
        membership = await self.repo.get(user_id)
        return membership is not None and membership.status == "active"

    async def list_pending(self) -> list[Membership]:
        return await self.repo.list_by_status("pending")

    async def timeline(self, user_id: str, limit: int = 100) -> list[MembershipEvent]:
        return await self.repo.list_events_for_user(user_id, limit=limit)
