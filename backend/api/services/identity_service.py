"""IdentityService — find-or-link platform identities to internal users.

Replaces `services.oauth_service.find_or_create_user` with a stronger contract:

  1. **Idempotent on reauth.** Calling find_or_link with the same
     (platform, platform_user_id) twice returns the same identity / user
     pair and does NOT touch admission state. This fixes the bug where
     reauth flows were creating ghost activation_requests rows.

  2. **Self-healing on data drift.** If the identity row is missing but a
     channels row for the same platform_user_id has an owner_user_id (i.e.
     this Twitch broadcaster was previously linked to some User), the
     service reconciles by re-inserting an identity row against the
     existing User instead of creating a brand-new user.

  3. **Multi-platform aware.** Accepts an optional ``link_to_user_id`` so
     a logged-in Twitch user can attach a Discord identity to the same
     User via a future "link account" flow without re-running admission.

Concurrent OAuth callbacks are handled via a transactional INSERT that
relies on the (platform, platform_user_id) UNIQUE constraint: the loser
catches UniqueViolationError and re-reads.

Audit: every successful find_or_link emits an auth_events row (login /
reauth / reconciled) describing what happened. AdmissionService is NOT
invoked here — admission is a separate concern.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import asyncpg
from asyncpg.exceptions import UniqueViolationError

from shared.repositories.identity import Identity, IdentityRepository

LOGGER: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FindOrLinkResult:
    """Outcome of a find_or_link call."""

    identity: Identity
    user_id: str
    is_new_user: bool  # True iff a brand-new users row was created
    is_new_identity: bool  # True iff a brand-new identities row was created
    was_reconciled: bool  # True iff identity was re-linked to a pre-existing User


class IdentityService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.repo = IdentityRepository(pool)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def find_or_link(
        self,
        *,
        platform: str,
        platform_user_id: str,
        username: str,
        display_name: str | None = None,
        avatar: str | None = None,
        link_to_user_id: str | None = None,
    ) -> FindOrLinkResult:
        """Resolve (platform, platform_user_id) -> identity + user_id.

        Behaviour:
            fast path        existing identity → touch last_seen_at, return
            reconciliation   identity missing but channels.owner_user_id
                             points at this broadcaster → re-attach identity
                             to that user
            link path        link_to_user_id given → attach new identity to
                             the supplied user (account linking)
            new path         no match → create new user + identity
        """
        # 1. Fast path: identity already exists.
        existing = await self.repo.find_by_platform_id(platform, platform_user_id)
        if existing is not None:
            await self.repo.touch_last_seen(existing.id)
            if existing.username != username:
                await self.repo.update_username(existing.id, username)
            await self._emit_auth_event(
                user_id=existing.user_id,
                identity_id=existing.id,
                event_type="reauth",
                metadata={"platform": platform, "platform_user_id": platform_user_id},
            )
            return FindOrLinkResult(
                identity=existing,
                user_id=existing.user_id,
                is_new_user=False,
                is_new_identity=False,
                was_reconciled=False,
            )

        # 2. Explicit account-linking path: caller is already authenticated as
        #    another User and wants to attach this new identity to it.
        if link_to_user_id is not None:
            return await self._link_to_existing_user(
                user_id=link_to_user_id,
                platform=platform,
                platform_user_id=platform_user_id,
                username=username,
            )

        # 3. Reconciliation: identity row gone but channels.owner_user_id
        #    remembers the previous owner of this Twitch broadcaster. Avoid
        #    creating a ghost users row.
        recovered_user_id = await self._lookup_orphan_owner(platform, platform_user_id)
        if recovered_user_id is not None:
            return await self._reconcile_identity(
                user_id=recovered_user_id,
                platform=platform,
                platform_user_id=platform_user_id,
                username=username,
            )

        # 4. Fresh signup.
        return await self._create_new_user(
            platform=platform,
            platform_user_id=platform_user_id,
            username=username,
            display_name=display_name,
            avatar=avatar,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _lookup_orphan_owner(
        self,
        platform: str,
        platform_user_id: str,
    ) -> str | None:
        """Return the User UUID that previously owned this platform identity.

        Heuristics (in order):
          1. channels.owner_user_id matching channel_id == platform_user_id
             (twitch only — channels keys broadcasters by their twitch id).
          2. activation_codes.used_by_user_id pointing at this platform pair.

        Returns the User UUID as text, or None if nothing recoverable.
        """
        async with self.pool.acquire() as conn:
            if platform == "twitch":
                row = await conn.fetchrow(
                    "SELECT owner_user_id::text AS user_id"
                    "  FROM channels"
                    " WHERE channel_id = $1 AND owner_user_id IS NOT NULL"
                    " LIMIT 1",
                    platform_user_id,
                )
                if row:
                    return row["user_id"]
            row = await conn.fetchrow(
                "SELECT used_by_user_id::text AS user_id"
                "  FROM activation_codes"
                " WHERE platform = $1 AND platform_user_id = $2"
                "   AND used_by_user_id IS NOT NULL"
                " ORDER BY used_at DESC NULLS LAST"
                " LIMIT 1",
                platform,
                platform_user_id,
            )
        return row["user_id"] if row else None

    async def _link_to_existing_user(
        self,
        *,
        user_id: str,
        platform: str,
        platform_user_id: str,
        username: str,
    ) -> FindOrLinkResult:
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    identity = await self.repo.insert_for_user(
                        user_id=user_id,
                        platform=platform,
                        platform_user_id=platform_user_id,
                        username=username,
                        conn=conn,
                    )
        except UniqueViolationError:
            # Lost a race against a concurrent OAuth callback; re-read.
            recovered = await self.repo.find_by_platform_id(platform, platform_user_id)
            if recovered is None:
                raise RuntimeError(
                    f"Concurrent OAuth race for {platform}:{platform_user_id} — "
                    "winner's identity missing on fallback SELECT"
                ) from None
            return FindOrLinkResult(
                identity=recovered,
                user_id=recovered.user_id,
                is_new_user=False,
                is_new_identity=False,
                was_reconciled=False,
            )

        await self._emit_auth_event(
            user_id=user_id,
            identity_id=identity.id,
            event_type="login",
            metadata={
                "platform": platform,
                "platform_user_id": platform_user_id,
                "mode": "account_link",
            },
        )
        return FindOrLinkResult(
            identity=identity,
            user_id=user_id,
            is_new_user=False,
            is_new_identity=True,
            was_reconciled=False,
        )

    async def _reconcile_identity(
        self,
        *,
        user_id: str,
        platform: str,
        platform_user_id: str,
        username: str,
    ) -> FindOrLinkResult:
        """Re-link an identity row to a previously-known User."""
        LOGGER.warning(
            "Reconciling missing identity for %s:%s → user %s",
            platform,
            platform_user_id,
            user_id,
        )
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    identity = await self.repo.insert_for_user(
                        user_id=user_id,
                        platform=platform,
                        platform_user_id=platform_user_id,
                        username=username,
                        conn=conn,
                    )
        except UniqueViolationError:
            # Another callback finished reconciliation first.
            recovered = await self.repo.find_by_platform_id(platform, platform_user_id)
            assert recovered is not None
            return FindOrLinkResult(
                identity=recovered,
                user_id=recovered.user_id,
                is_new_user=False,
                is_new_identity=False,
                was_reconciled=True,
            )

        await self._emit_auth_event(
            user_id=user_id,
            identity_id=identity.id,
            event_type="reconciled",
            metadata={"platform": platform, "platform_user_id": platform_user_id},
        )
        return FindOrLinkResult(
            identity=identity,
            user_id=user_id,
            is_new_user=False,
            is_new_identity=True,
            was_reconciled=True,
        )

    async def _create_new_user(
        self,
        *,
        platform: str,
        platform_user_id: str,
        username: str,
        display_name: str | None,
        avatar: str | None,
    ) -> FindOrLinkResult:
        """Create a fresh users row + matching identity, atomically."""
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    user_row = await conn.fetchrow(
                        "INSERT INTO users (display_name, avatar)"
                        " VALUES ($1, $2)"
                        " RETURNING id::text AS id",
                        display_name or username,
                        avatar,
                    )
                    user_id = user_row["id"]
                    identity = await self.repo.insert_for_user(
                        user_id=user_id,
                        platform=platform,
                        platform_user_id=platform_user_id,
                        username=username,
                        conn=conn,
                    )
        except UniqueViolationError:
            # Concurrent first-time signup; the winner already created both rows.
            recovered = await self.repo.find_by_platform_id(platform, platform_user_id)
            if recovered is None:
                raise RuntimeError(
                    f"Concurrent OAuth race for {platform}:{platform_user_id} — "
                    "winner's identity missing on fallback SELECT"
                ) from None
            return FindOrLinkResult(
                identity=recovered,
                user_id=recovered.user_id,
                is_new_user=False,
                is_new_identity=False,
                was_reconciled=False,
            )

        await self._emit_auth_event(
            user_id=user_id,
            identity_id=identity.id,
            event_type="login",
            metadata={
                "platform": platform,
                "platform_user_id": platform_user_id,
                "mode": "first_signup",
            },
        )
        return FindOrLinkResult(
            identity=identity,
            user_id=user_id,
            is_new_user=True,
            is_new_identity=True,
            was_reconciled=False,
        )

    async def _emit_auth_event(
        self,
        *,
        user_id: str,
        identity_id: str | None,
        event_type: str,
        metadata: dict,
    ) -> None:
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO auth_events"
                    " (user_id, identity_id, event_type, metadata)"
                    " VALUES ($1::uuid, $2::uuid, $3, $4::jsonb)",
                    user_id,
                    identity_id,
                    event_type,
                    json.dumps(metadata),
                )
        except Exception:
            # Audit log failure must never break the auth flow.
            LOGGER.exception("Failed to write auth_event %s for user %s", event_type, user_id)
