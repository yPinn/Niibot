"""Repository for activation_codes — the *grant to activate* table.

Two kinds of grant live here (see migration 089):

* ``channel_points`` — issued by the Twitch bot when a viewer redeems the
  ``niibot_auth`` reward. Carries the redemption provenance. Consumed
  automatically the next time that Twitch identity logs in
  (:meth:`find_unconsumed_grant` + :meth:`consume`) — no code entry.
* ``owner_manual`` — issued by the owner from the admin panel. A bearer code
  redeemed by typing it on ``/activate`` (:meth:`redeem`). Unbound to any
  account until redeemed.

``status`` moves ``issued → consumed | expired | revoked``. Terminal rows are
kept for the onboarding funnel; :meth:`mark_expired` / :meth:`scrub_terminal`
are run by a daily loop in the API lifespan.

Write methods accept an optional ``conn`` so the caller (the auth router) can
fold code consumption and the membership transition into one transaction.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

import asyncpg

LOGGER: logging.Logger = logging.getLogger(__name__)

_EXPIRES_HOURS = 72


def _generate_otp() -> str:
    return str(secrets.randbelow(900000) + 100000)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class ActivationCodeRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ------------------------------------------------------------------
    # Issue
    # ------------------------------------------------------------------

    async def create_channel_points_grant(
        self,
        platform_user_id: str,
        *,
        platform: str = "twitch",
        redemption_id: str | None = None,
        channel_id: str | None = None,
        reward_cost: int | None = None,
    ) -> str:
        """Issue a channel-points grant for a redeemer. Returns the raw code.

        Any prior *live* code for the same identity is revoked (superseded)
        rather than deleted, so the funnel keeps a full history.
        """
        code = _generate_otp()
        expires_at = datetime.now(UTC) + timedelta(hours=_EXPIRES_HOURS)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE activation_codes SET status = 'revoked'"
                    " WHERE platform = $1 AND platform_user_id = $2 AND status = 'issued'",
                    platform,
                    platform_user_id,
                )
                await conn.execute(
                    "INSERT INTO activation_codes"
                    " (code_hash, code_plain, platform, platform_user_id, expires_at,"
                    "  kind, status, redemption_id, channel_id, reward_cost)"
                    " VALUES ($1, $2, $3, $4, $5, 'channel_points', 'issued', $6, $7, $8)",
                    _hash_code(code),
                    code,
                    platform,
                    platform_user_id,
                    expires_at,
                    redemption_id,
                    channel_id,
                    reward_cost,
                )
        return code

    async def create_owner_code(
        self,
        *,
        issued_by_user_id: str,
        platform: str = "twitch",
    ) -> str:
        """Issue an unbound owner_manual bearer code. Returns the raw code."""
        code = _generate_otp()
        expires_at = datetime.now(UTC) + timedelta(hours=_EXPIRES_HOURS)
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO activation_codes"
                " (code_hash, code_plain, platform, platform_user_id, expires_at,"
                "  kind, status, issued_by_user_id)"
                " VALUES ($1, $2, $3, NULL, $4, 'owner_manual', 'issued', $5::uuid)",
                _hash_code(code),
                code,
                platform,
                expires_at,
                issued_by_user_id,
            )
        return code

    # Transitional: the bot still calls create(); migrated in a later commit.
    async def create(self, platform: str, platform_user_id: str) -> str:
        return await self.create_channel_points_grant(platform_user_id, platform=platform)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_plain_code(self, platform: str, platform_user_id: str) -> str | None:
        """Plain code of the caller's own live grant, or None."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT code_plain FROM activation_codes"
                " WHERE platform = $1 AND platform_user_id = $2"
                "   AND status = 'issued' AND expires_at > NOW()"
                " ORDER BY expires_at DESC LIMIT 1",
                platform,
                platform_user_id,
            )
        return row["code_plain"] if row else None

    async def find_unconsumed_grant(
        self,
        platform: str,
        platform_user_id: str,
    ) -> asyncpg.Record | None:
        """The live channel-points grant for this identity, if any."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT id, code_hash, redemption_id, channel_id, reward_cost, issued_at"
                "  FROM activation_codes"
                " WHERE platform = $1 AND platform_user_id = $2"
                "   AND kind = 'channel_points' AND status = 'issued'"
                "   AND expires_at > NOW()"
                " ORDER BY issued_at DESC LIMIT 1",
                platform,
                platform_user_id,
            )

    # ------------------------------------------------------------------
    # Consume
    # ------------------------------------------------------------------

    async def consume(
        self,
        grant_id: int,
        user_id: str,
        *,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        """Mark a grant consumed. Idempotent-safe: only touches 'issued' rows."""
        sql = (
            "UPDATE activation_codes"
            "   SET status = 'consumed', used_at = NOW(),"
            "       used_by_user_id = $2::uuid, code_plain = NULL"
            " WHERE id = $1 AND status = 'issued'"
        )
        if conn is not None:
            await conn.execute(sql, grant_id, user_id)
        else:
            async with self.pool.acquire() as own:
                await own.execute(sql, grant_id, user_id)

    async def redeem(
        self,
        code: str,
        platform: str,
        platform_user_id: str,
        user_id: str,
        *,
        conn: asyncpg.Connection | None = None,
    ) -> bool:
        """Validate and consume a typed code (owner_manual path).

        Binds the code to the redeeming identity. Returns True on success.
        A failed match against an existing live code bumps its attempt_count
        for admin visibility (no lockout).
        """
        if conn is not None:
            return await self._redeem(conn, code, platform, platform_user_id, user_id)
        async with self.pool.acquire() as own:
            async with own.transaction():
                return await self._redeem(own, code, platform, platform_user_id, user_id)

    @staticmethod
    async def _redeem(
        conn: asyncpg.Connection,
        code: str,
        platform: str,
        platform_user_id: str,
        user_id: str,
    ) -> bool:
        code_hash = _hash_code(code)
        row = await conn.fetchrow(
            "SELECT id, platform_user_id FROM activation_codes"
            " WHERE code_hash = $1 AND platform = $2"
            "   AND status = 'issued' AND expires_at > NOW()"
            " FOR UPDATE",
            code_hash,
            platform,
        )
        if not row:
            return False
        # A code bound to a different identity is not redeemable by this caller.
        if row["platform_user_id"] not in (None, platform_user_id):
            await conn.execute(
                "UPDATE activation_codes SET attempt_count = attempt_count + 1 WHERE id = $1",
                row["id"],
            )
            return False
        await conn.execute(
            "UPDATE activation_codes"
            "   SET status = 'consumed', used_at = NOW(), used_by_user_id = $2::uuid,"
            "       platform_user_id = COALESCE(platform_user_id, $3), code_plain = NULL"
            " WHERE id = $1",
            row["id"],
            user_id,
            platform_user_id,
        )
        return True

    # ------------------------------------------------------------------
    # Revoke / housekeeping
    # ------------------------------------------------------------------

    async def revoke(self, grant_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE activation_codes SET status = 'revoked'"
                " WHERE id = $1 AND status = 'issued'",
                grant_id,
            )
        return result != "UPDATE 0"

    # Transitional: admin router still revokes by identity; migrated later.
    async def invalidate(self, platform: str, platform_user_id: str) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE activation_codes SET status = 'revoked'"
                " WHERE platform = $1 AND platform_user_id = $2 AND status = 'issued'",
                platform,
                platform_user_id,
            )
        return result != "UPDATE 0"

    async def mark_expired(self) -> int:
        """Flip live codes past their expiry to 'expired'. Returns row count."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE activation_codes SET status = 'expired'"
                " WHERE status = 'issued' AND expires_at <= NOW()"
            )
        return int(result.split()[-1]) if result.startswith("UPDATE") else 0

    async def scrub_terminal(self, older_than_days: int = 90) -> int:
        """Hard-delete terminal rows older than the cutoff. Returns row count."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM activation_codes"
                " WHERE status IN ('consumed', 'expired', 'revoked')"
                "   AND COALESCE(used_at, expires_at) < NOW() - ($1 || ' days')::interval",
                str(older_than_days),
            )
        return int(result.split()[-1]) if result.startswith("DELETE") else 0

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    async def list_grants(
        self,
        *,
        kind: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT ac.id, ac.kind, ac.status, ac.platform, ac.platform_user_id,"
                "       ac.code_plain, ac.reward_cost, ac.channel_id, ac.redemption_id,"
                "       ac.issued_at, ac.expires_at, ac.used_at, ac.attempt_count,"
                "       u.display_name, u.avatar, i.username"
                "  FROM activation_codes ac"
                "  LEFT JOIN identities i"
                "    ON i.platform = ac.platform AND i.platform_user_id = ac.platform_user_id"
                "  LEFT JOIN users u ON u.id = COALESCE(i.user_id, ac.used_by_user_id)"
                " WHERE ($1::text IS NULL OR ac.kind = $1)"
                "   AND ($2::text IS NULL OR ac.status = $2)"
                " ORDER BY ac.issued_at DESC"
                " LIMIT $3",
                kind,
                status,
                limit,
            )

    async def funnel_counts(self) -> list[asyncpg.Record]:
        """Per-kind issue/consume counts over 7d / 30d / all-time."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT kind,
                       COUNT(*)                                             AS issued_all,
                       COUNT(*) FILTER (WHERE status = 'consumed')          AS consumed_all,
                       COUNT(*) FILTER (WHERE issued_at > NOW() - INTERVAL '30 days')
                                                                           AS issued_30d,
                       COUNT(*) FILTER (WHERE status = 'consumed'
                                         AND used_at > NOW() - INTERVAL '30 days')
                                                                           AS consumed_30d,
                       COUNT(*) FILTER (WHERE issued_at > NOW() - INTERVAL '7 days')
                                                                           AS issued_7d,
                       COUNT(*) FILTER (WHERE status = 'consumed'
                                         AND used_at > NOW() - INTERVAL '7 days')
                                                                           AS consumed_7d,
                       COUNT(*) FILTER (WHERE status = 'issued')            AS outstanding
                  FROM activation_codes
                 GROUP BY kind
                """
            )


async def activation_grant_cleanup_loop(db_manager) -> None:
    """Once a day: expire stale grants and hard-delete old terminal rows."""
    while True:
        try:
            await asyncio.sleep(86_400)
            if not db_manager.is_connected:
                continue
            repo = ActivationCodeRepository(db_manager.pool)
            expired = await repo.mark_expired()
            scrubbed = await repo.scrub_terminal(90)
            if expired or scrubbed:
                LOGGER.info(
                    "activation_grants_cleaned",
                    extra={"expired": expired, "scrubbed": scrubbed},
                )
        except asyncio.CancelledError:
            return
        except Exception:
            LOGGER.exception("activation_grant_cleanup_failed")
