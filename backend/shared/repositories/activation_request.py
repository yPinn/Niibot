"""Repository for activation_requests table."""

from __future__ import annotations

import asyncpg


class ActivationRequestRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def create(
        self, user_id: str, platform: str, platform_user_id: str, note: str = ""
    ) -> int:
        """Create a pending request, replacing any prior pending one for the same user."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM activation_requests"
                    " WHERE user_id = $1::uuid AND status = 'pending'",
                    user_id,
                )
                row = await conn.fetchrow(
                    "INSERT INTO activation_requests (user_id, platform, platform_user_id, note)"
                    " VALUES ($1::uuid, $2, $3, $4) RETURNING id",
                    user_id,
                    platform,
                    platform_user_id,
                    note,
                )
        return row["id"]

    async def get_for_user(self, user_id: str) -> dict | None:
        """Return the most recent request (any status) for a user."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, status, created_at"
                " FROM activation_requests"
                " WHERE user_id = $1::uuid"
                " ORDER BY created_at DESC LIMIT 1",
                user_id,
            )
        return dict(row) if row else None

    async def list_pending(self) -> list[dict]:
        """Return all pending requests with user display info."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ar.id, ar.platform_user_id, ar.note, ar.created_at,
                       u.display_name, u.avatar,
                       ula.username
                FROM activation_requests ar
                JOIN users u ON u.id = ar.user_id
                LEFT JOIN user_linked_accounts ula
                    ON ula.user_id = ar.user_id AND ula.platform = ar.platform
                WHERE ar.status = 'pending'
                ORDER BY ar.created_at ASC
                """
            )
        return [dict(r) for r in rows]

    async def approve(self, request_id: int) -> bool:
        """Approve the request and mark the user as activated. Returns False if not found."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "UPDATE activation_requests"
                    " SET status = 'approved', reviewed_at = NOW()"
                    " WHERE id = $1 AND status = 'pending'"
                    " RETURNING user_id",
                    request_id,
                )
                if not row:
                    return False
                await conn.execute(
                    "UPDATE users SET is_activated = TRUE WHERE id = $1",
                    row["user_id"],
                )
        return True

    async def reject(self, request_id: int) -> bool:
        """Reject the pending request. Returns False if not found."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE activation_requests"
                " SET status = 'rejected', reviewed_at = NOW()"
                " WHERE id = $1 AND status = 'pending'",
                request_id,
            )
        return result != "UPDATE 0"
