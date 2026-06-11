"""Repository for activation_requests — compatibility shim over memberships.

The legacy ``activation_requests`` table is retained during the rollout for
dual-read safety, but all new writes go through the memberships +
membership_events model. This repository keeps the old surface (``create``,
``get_for_user``, ``approve``, ``reject``, ``list_pending``) so non-API callers
(notably the Twitch bot's channel-points component) keep working unchanged.

When the rollout completes and ``activation_requests`` is dropped, this
repository will become a thin wrapper over MembershipRepository and can be
removed entirely.
"""

from __future__ import annotations

import json

import asyncpg


class ActivationRequestRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def create(
        self, user_id: str, platform: str, platform_user_id: str, note: str = ""
    ) -> int:
        """Upsert a pending membership and append a 'requested' audit event.

        Returns the membership_events.id of the new event for parity with the
        legacy return value (which used to be the int activation_requests.id).
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # 1. Upsert memberships -> 'pending', but only if not already active.
                await conn.execute(
                    """
                    INSERT INTO memberships (user_id, status, reason)
                    VALUES ($1::uuid, 'pending', $2)
                    ON CONFLICT (user_id) DO UPDATE SET
                        status     = CASE
                                       WHEN memberships.status IN ('active', 'suspended')
                                         THEN memberships.status
                                       ELSE 'pending'
                                     END,
                        reason     = COALESCE(EXCLUDED.reason, memberships.reason),
                        updated_at = NOW()
                    """,
                    user_id,
                    note or "channel_points_redeem",
                )
                # 2. Append 'requested' event.
                metadata = json.dumps(
                    {
                        "platform": platform,
                        "platform_user_id": platform_user_id,
                    }
                )
                row = await conn.fetchrow(
                    """
                    INSERT INTO membership_events
                        (user_id, event_type, actor_type, reason, metadata)
                    VALUES ($1::uuid, 'requested', 'system', $2, $3::jsonb)
                    RETURNING id
                    """,
                    user_id,
                    note or "channel_points_redeem",
                    metadata,
                )
        return int(row["id"])

    async def get_for_user(self, user_id: str) -> dict | None:
        """Return the most recent request (any status) for a user.

        Returns the same shape the legacy code expected: ``{id, status, created_at}``.
        ``id`` is the membership_events.id of the latest 'requested' event.
        ``status`` is the current memberships.status.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT m.status,
                       COALESCE(
                           (SELECT id FROM membership_events e
                            WHERE e.user_id = m.user_id
                              AND e.event_type = 'requested'
                            ORDER BY e.occurred_at DESC LIMIT 1),
                           0
                       )                                                 AS id,
                       COALESCE(
                           (SELECT occurred_at FROM membership_events e
                            WHERE e.user_id = m.user_id
                              AND e.event_type = 'requested'
                            ORDER BY e.occurred_at DESC LIMIT 1),
                           m.updated_at
                       )                                                 AS created_at
                FROM memberships m
                WHERE m.user_id = $1::uuid
                """,
                user_id,
            )
        return dict(row) if row else None

    async def list_pending(self) -> list[dict]:
        """Return all pending memberships joined with user display info."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT m.user_id::text                                    AS id,
                       COALESCE(i.platform_user_id, '')                   AS platform_user_id,
                       COALESCE(
                           (SELECT reason FROM membership_events e
                            WHERE e.user_id = m.user_id
                              AND e.event_type = 'requested'
                            ORDER BY e.occurred_at DESC LIMIT 1),
                           ''
                       )                                                  AS note,
                       COALESCE(
                           (SELECT occurred_at FROM membership_events e
                            WHERE e.user_id = m.user_id
                              AND e.event_type = 'requested'
                            ORDER BY e.occurred_at DESC LIMIT 1),
                           m.updated_at
                       )                                                  AS created_at,
                       u.display_name,
                       u.avatar,
                       i.username
                FROM memberships m
                JOIN users u ON u.id = m.user_id
           LEFT JOIN identities i
                  ON i.user_id = m.user_id AND i.platform = 'twitch'
               WHERE m.status = 'pending'
            ORDER BY created_at ASC
                """
            )
        return [dict(r) for r in rows]

    async def approve(self, request_id: int) -> bool:
        """Approve via the legacy int request_id path.

        Looks up the user_id that corresponds to the given membership_events.id
        (which the legacy `create` returned) and promotes their membership to
        'active'. Returns False if the event doesn't exist or the user is not
        currently pending.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT user_id::text AS user_id FROM membership_events WHERE id = $1",
                    request_id,
                )
                if not row:
                    return False
                user_id = row["user_id"]
                result = await conn.execute(
                    """
                    UPDATE memberships
                       SET status     = 'active',
                           granted_at = COALESCE(granted_at, NOW()),
                           reason     = COALESCE(reason, 'legacy_approve'),
                           updated_at = NOW()
                     WHERE user_id = $1::uuid AND status = 'pending'
                    """,
                    user_id,
                )
                if result == "UPDATE 0":
                    return False
                await conn.execute(
                    """
                    INSERT INTO membership_events
                        (user_id, event_type, actor_type, reason)
                    VALUES ($1::uuid, 'approved', 'owner', 'legacy_approve')
                    """,
                    user_id,
                )
        return True

    async def reject(self, request_id: int) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT user_id::text AS user_id FROM membership_events WHERE id = $1",
                    request_id,
                )
                if not row:
                    return False
                user_id = row["user_id"]
                result = await conn.execute(
                    """
                    UPDATE memberships
                       SET status     = 'rejected',
                           reason     = COALESCE(reason, 'legacy_reject'),
                           updated_at = NOW()
                     WHERE user_id = $1::uuid AND status = 'pending'
                    """,
                    user_id,
                )
                if result == "UPDATE 0":
                    return False
                await conn.execute(
                    """
                    INSERT INTO membership_events
                        (user_id, event_type, actor_type, reason)
                    VALUES ($1::uuid, 'rejected', 'owner', 'legacy_reject')
                    """,
                    user_id,
                )
        return True
