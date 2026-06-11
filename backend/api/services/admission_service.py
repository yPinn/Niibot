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

from shared.repositories.membership import (
    Membership,
    MembershipEvent,
    MembershipRepository,
)

LOGGER: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdmissionDecision:
    membership: Membership
    event_id: int
    state_changed: bool


class AdmissionService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.repo = MembershipRepository(pool)

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

    async def grant_via_otp(
        self,
        user_id: str,
        *,
        platform: str,
        platform_user_id: str,
        code_hash: str,
    ) -> AdmissionDecision:
        """Activate a membership in response to an OTP redemption.

        Caller is expected to have already validated the code (typically the
        ActivationCodeRepository.redeem call in the auth router).
        """
        metadata = {
            "platform": platform,
            "platform_user_id": platform_user_id,
            "code_hash": code_hash,
        }

        current = await self.repo.get(user_id)
        if current and current.status == "active":
            return AdmissionDecision(membership=current, event_id=0, state_changed=False)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                membership = await self.repo.upsert_status(
                    user_id,
                    "active",
                    reason="otp_redeem",
                    conn=conn,
                )
                event_id = await self.repo.insert_event(
                    user_id,
                    "approved",
                    actor_type="system",
                    reason="otp_redeem",
                    metadata=metadata,
                    conn=conn,
                )
        return AdmissionDecision(membership=membership, event_id=event_id, state_changed=True)

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
