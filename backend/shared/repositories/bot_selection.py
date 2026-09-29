"""Persistence boundary for per-channel bot sender desired/active state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

import asyncpg

SelectionStatus = Literal["active", "switching", "failed"]


@dataclass(frozen=True, slots=True)
class BotSelectionState:
    channel_id: str
    desired_bot_user_id: str | None
    active_bot_user_id: str | None
    selection_version: int
    acked_version: int
    status: SelectionStatus
    last_error_code: str | None


class BotSelectionRepository:
    """Serialize desired writes and version-guard runtime acknowledgements."""

    _COLUMNS = """
        channel_id, desired_bot_user_id, active_bot_user_id,
        selection_version, acked_version, status, last_error_code
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @staticmethod
    def _state(row) -> BotSelectionState:
        return BotSelectionState(
            channel_id=str(row["channel_id"]),
            desired_bot_user_id=row["desired_bot_user_id"],
            active_bot_user_id=row["active_bot_user_id"],
            selection_version=int(row["selection_version"]),
            acked_version=int(row["acked_version"]),
            status=str(row["status"]),  # type: ignore[arg-type]
            last_error_code=row["last_error_code"],
        )

    async def get(self, channel_id: str) -> BotSelectionState:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {self._COLUMNS} FROM channel_bot_settings WHERE channel_id = $1",
                channel_id,
            )
        if row is None:
            return BotSelectionState(
                channel_id=channel_id,
                desired_bot_user_id=None,
                active_bot_user_id=None,
                selection_version=0,
                acked_version=0,
                status="active",
                last_error_code=None,
            )
        return self._state(row)

    async def list_switching(self) -> list[BotSelectionState]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {self._COLUMNS}
                  FROM channel_bot_settings
                 WHERE status = 'switching'
                 ORDER BY updated_at, channel_id
                """
            )
        return [self._state(row) for row in rows]

    async def is_candidate_available(
        self,
        *,
        channel_id: str,
        bot_user_id: str | None,
        system_bot_id: str,
    ) -> bool:
        actual_bot_id = bot_user_id or system_bot_id
        async with self.pool.acquire() as conn:
            return bool(
                await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                          FROM bot_accounts account
                         WHERE account.platform_user_id = $2
                           AND (
                               ($3::boolean AND account.is_system_default)
                               OR (
                                   NOT $3::boolean
                                   AND EXISTS (
                                       SELECT 1
                                         FROM channel_bot_accounts mapping
                                        WHERE mapping.channel_id = $1
                                          AND mapping.bot_user_id = account.platform_user_id
                                   )
                               )
                           )
                    )
                    """,
                    channel_id,
                    actual_bot_id,
                    bot_user_id is None,
                )
            )

    @staticmethod
    async def _candidate_ready(
        conn: asyncpg.Connection,
        *,
        channel_id: str,
        bot_user_id: str | None,
        system_bot_id: str,
        required_scopes: set[str],
    ) -> bool:
        actual_bot_id = bot_user_id or system_bot_id
        return bool(
            await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                      FROM bot_accounts account
                      JOIN tokens token
                        ON token.user_id = account.platform_user_id
                       AND token.token_type = 'bot'
                     WHERE account.platform_user_id = $2
                       AND account.requires_reauth = FALSE
                       AND account.revoked_at IS NULL
                       AND token.requires_reauth = FALSE
                       AND token.invalidated_at IS NULL
                       AND NOT EXISTS (
                           SELECT 1
                             FROM tokens broadcaster
                            WHERE broadcaster.user_id = account.platform_user_id
                              AND broadcaster.token_type = 'broadcaster'
                       )
                       AND string_to_array(COALESCE(token.scopes, ''), ' ')
                           @> $4::text[]
                       AND (
                           ($3::boolean AND account.is_system_default)
                           OR (
                               NOT $3::boolean
                               AND EXISTS (
                                   SELECT 1
                                     FROM channel_bot_accounts mapping
                                    WHERE mapping.channel_id = $1
                                      AND mapping.bot_user_id = account.platform_user_id
                               )
                           )
                       )
                )
                """,
                channel_id,
                actual_bot_id,
                bot_user_id is None,
                sorted(required_scopes),
            )
        )

    async def request(
        self,
        *,
        channel_id: str,
        bot_user_id: str | None,
        actor_user_id: str,
        system_bot_id: str,
        required_scopes: set[str],
    ) -> BotSelectionState | None:
        """Write desired state after rechecking the candidate inside the lock.

        ``None`` means the account mapping or credential changed after API
        preflight.  Callers expose one stable, non-enumerating error.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"bot-selection:{channel_id}",
                )
                target_id = bot_user_id or system_bot_id
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"twitch-runtime-identity:{target_id}",
                )
                if not await self._candidate_ready(
                    conn,
                    channel_id=channel_id,
                    bot_user_id=bot_user_id,
                    system_bot_id=system_bot_id,
                    required_scopes=required_scopes,
                ):
                    return None

                current = await conn.fetchrow(
                    f"""
                    SELECT {self._COLUMNS}
                      FROM channel_bot_settings
                     WHERE channel_id = $1
                     FOR UPDATE
                    """,
                    channel_id,
                )
                if (
                    current is not None
                    and current["active_bot_user_id"] == bot_user_id
                    and current["desired_bot_user_id"] == bot_user_id
                    and current["status"] == "active"
                ):
                    return self._state(current)
                if current is None and bot_user_id is None:
                    return BotSelectionState(
                        channel_id=channel_id,
                        desired_bot_user_id=None,
                        active_bot_user_id=None,
                        selection_version=0,
                        acked_version=0,
                        status="active",
                        last_error_code=None,
                    )

                row = await conn.fetchrow(
                    f"""
                    INSERT INTO channel_bot_settings (
                        channel_id, desired_bot_user_id, active_bot_user_id,
                        selection_version, acked_version, status,
                        last_error_code, updated_by_user_id
                    )
                    VALUES ($1, $2, NULL, 1, 0, 'switching', NULL, $3::uuid)
                    ON CONFLICT (channel_id) DO UPDATE SET
                        desired_bot_user_id = EXCLUDED.desired_bot_user_id,
                        selection_version = channel_bot_settings.selection_version + 1,
                        status = 'switching',
                        last_error_code = NULL,
                        updated_by_user_id = EXCLUDED.updated_by_user_id
                    RETURNING {self._COLUMNS}
                    """,
                    channel_id,
                    bot_user_id,
                    actor_user_id,
                )
                state = self._state(row)
                await conn.execute(
                    """
                    INSERT INTO tenant_audit_events
                        (channel_id, actor_user_id, event_type, target_type, target_id, metadata)
                    VALUES ($1, $2::uuid, 'bot_selection_requested', 'bot_account', $3,
                            $4::jsonb)
                    """,
                    channel_id,
                    actor_user_id,
                    target_id,
                    json.dumps({"selection_version": state.selection_version}),
                )
                await conn.execute(
                    "SELECT pg_notify($1, $2)",
                    "bot_selection_changed",
                    json.dumps(
                        {
                            "channel_id": channel_id,
                            "selection_version": state.selection_version,
                        }
                    ),
                )
                return state

    async def mark_active(
        self,
        *,
        channel_id: str,
        selection_version: int,
        bot_user_id: str | None,
    ) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE channel_bot_settings
                   SET active_bot_user_id = $3,
                       acked_version = $2,
                       status = 'active',
                       last_error_code = NULL
                 WHERE channel_id = $1
                   AND selection_version = $2
                   AND status = 'switching'
                RETURNING {self._COLUMNS}
                """,
                channel_id,
                selection_version,
                bot_user_id,
            )
        return row is not None

    async def mark_failed(
        self,
        *,
        channel_id: str,
        selection_version: int,
        error_code: str,
    ) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE channel_bot_settings
                   SET acked_version = $2,
                       status = 'failed',
                       last_error_code = $3
                 WHERE channel_id = $1
                   AND selection_version = $2
                   AND status = 'switching'
                RETURNING {self._COLUMNS}
                """,
                channel_id,
                selection_version,
                error_code,
            )
        return row is not None
