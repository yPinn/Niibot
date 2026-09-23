"""Twitch credential health, tenant unlink, and broadcaster disconnect lifecycle."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import asyncpg

from services.twitch_api import TwitchAPIClient
from shared.errors import ConflictError, NotFoundError
from shared.twitch_scopes import BOT_SCOPES, BROADCASTER_SCOPES
from shared.twitch_token_crypto import (
    decrypt_twitch_token,
    encrypt_twitch_token,
    require_twitch_token_encryption_key,
)

LOGGER = logging.getLogger(__name__)

TokenType = Literal["bot", "broadcaster"]
AuthorizationStatus = Literal[
    "valid", "requires_reauthorization", "temporarily_unavailable", "not_checked"
]


@dataclass(frozen=True)
class CredentialHealth:
    user_id: str
    token_type: TokenType
    status: AuthorizationStatus
    last_checked_at: datetime | None = None
    last_validated_at: datetime | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class AuthorizationRemovalResult:
    credential_retained: bool
    upstream_revoke_confirmed: bool


@dataclass(frozen=True)
class BroadcasterAuthorizationSummary:
    channel_id: str
    channel_name: str
    display_name: str | None
    enabled: bool
    status: AuthorizationStatus
    last_checked_at: datetime | None
    last_validated_at: datetime | None
    error_code: str | None


class CredentialNotFoundError(NotFoundError):
    code = "TWITCH_AUTH.NOT_FOUND"
    user_message = "找不到這筆 Twitch 授權"


class SystemBotProtectedError(ConflictError):
    code = "BOT_ACCOUNT.SYSTEM_PROTECTED"
    user_message = "系統 Bot 不能從頻道移除"


class BotAccountInUseError(ConflictError):
    code = "BOT_ACCOUNT.IN_USE"
    user_message = "請先改用其他 Bot，再移除這個帳號"


class TwitchAuthorizationService:
    """Central policy boundary for both token purposes.

    Bot and broadcaster credentials remain distinct rows because they have
    different scopes and revocation consequences. They only share validation,
    refresh, health-state, and best-effort upstream revocation mechanics.
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        twitch_api: TwitchAPIClient,
        token_encryption_key: str,
        client_id: str,
    ) -> None:
        self.pool = pool
        self.twitch = twitch_api
        self.token_encryption_key = token_encryption_key
        self.client_id = client_id

    @staticmethod
    def _health_status(row) -> AuthorizationStatus:
        if row["invalidated_at"] is not None or bool(row["requires_reauth"]):
            return "requires_reauthorization"
        if row["validation_error_code"] == "provider_unavailable":
            return "temporarily_unavailable"
        if row["last_validated_at"] is not None:
            return "valid"
        return "not_checked"

    async def check_credential(
        self,
        *,
        user_id: str,
        token_type: TokenType,
        required_scopes: set[str],
        force: bool = True,
    ) -> CredentialHealth:
        """Validate one credential under a transaction-scoped advisory lock."""
        token_encryption_key = require_twitch_token_encryption_key(self.token_encryption_key)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"twitch-auth:{token_type}:{user_id}",
                )
                if token_type == "bot":
                    # Bot unlink and OAuth authorization use the same
                    # account -> token lock order, preventing deadlocks.
                    await conn.execute(
                        """
                        SELECT platform_user_id
                          FROM bot_accounts
                         WHERE platform_user_id = $1
                         FOR UPDATE
                        """,
                        user_id,
                    )
                row = await conn.fetchrow(
                    """
                    SELECT user_id, token_type, token, refresh, encryption_version,
                           requires_reauth, last_checked_at, last_validated_at,
                           invalidated_at, validation_error_code
                      FROM tokens
                     WHERE user_id = $1 AND token_type = $2
                     FOR UPDATE
                    """,
                    user_id,
                    token_type,
                )
                if row is None:
                    raise CredentialNotFoundError()
                already_requires_reauthorization = bool(row["requires_reauth"]) or (
                    row["invalidated_at"] is not None
                )
                existing_error_code = row["validation_error_code"]
                if (
                    not force
                    and row["last_checked_at"] is not None
                    and row["last_checked_at"] > datetime.now(UTC) - timedelta(minutes=55)
                ):
                    return CredentialHealth(
                        user_id=user_id,
                        token_type=token_type,
                        status=self._health_status(row),
                        last_checked_at=row["last_checked_at"],
                        last_validated_at=row["last_validated_at"],
                        error_code=row["validation_error_code"],
                    )

                access_token = decrypt_twitch_token(
                    str(row["token"]),
                    version=int(row["encryption_version"]),
                    key=token_encryption_key,
                )
                refresh_token = decrypt_twitch_token(
                    str(row["refresh"]),
                    version=int(row["encryption_version"]),
                    key=token_encryption_key,
                )

                validation = await self.twitch.validate_token_details(access_token)
                if validation.status == "invalid":
                    refreshed = await self.twitch.refresh_access_token(refresh_token)
                    if not refreshed.success:
                        if refreshed.error_code == "provider_unavailable":
                            return await self._mark_temporarily_unavailable(
                                conn,
                                user_id=user_id,
                                token_type=token_type,
                                already_requires_reauthorization=already_requires_reauthorization,
                                existing_error_code=existing_error_code,
                            )
                        return await self._mark_definitely_invalid(
                            conn,
                            user_id=user_id,
                            token_type=token_type,
                            error_code="refresh_failed",
                        )

                    assert refreshed.access_token is not None
                    assert refreshed.refresh_token is not None
                    access_token = refreshed.access_token
                    refresh_token = refreshed.refresh_token
                    encrypted_access, encryption_version = encrypt_twitch_token(
                        access_token, token_encryption_key
                    )
                    encrypted_refresh, refresh_version = encrypt_twitch_token(
                        refresh_token, token_encryption_key
                    )
                    if refresh_version != encryption_version:
                        raise RuntimeError("Twitch credential encryption versions diverged")
                    await conn.execute(
                        """
                        UPDATE tokens
                           SET token = $3, refresh = $4, encryption_version = $5,
                               updated_at = NOW()
                         WHERE user_id = $1 AND token_type = $2
                        """,
                        user_id,
                        token_type,
                        encrypted_access,
                        encrypted_refresh,
                        encryption_version,
                    )
                    notify_channel = "bot_token_updated" if token_type == "bot" else "token_reauth"
                    await conn.execute(
                        "SELECT pg_notify($1, $2)",
                        notify_channel,
                        json.dumps({"user_id": user_id}),
                    )
                    validation = await self.twitch.validate_token_details(access_token)

                if validation.status == "unavailable":
                    return await self._mark_temporarily_unavailable(
                        conn,
                        user_id=user_id,
                        token_type=token_type,
                        already_requires_reauthorization=already_requires_reauthorization,
                        existing_error_code=existing_error_code,
                    )
                if validation.status == "invalid":
                    return await self._mark_definitely_invalid(
                        conn,
                        user_id=user_id,
                        token_type=token_type,
                        error_code="invalid_token",
                    )

                error_code: str | None = None
                if validation.client_id != self.client_id:
                    error_code = "client_mismatch"
                elif validation.user_id != user_id:
                    error_code = "identity_mismatch"
                elif not required_scopes.issubset(validation.scopes):
                    error_code = "missing_scopes"
                if error_code is not None:
                    return await self._mark_definitely_invalid(
                        conn,
                        user_id=user_id,
                        token_type=token_type,
                        error_code=error_code,
                    )

                await conn.execute(
                    """
                    UPDATE tokens
                       SET last_checked_at = NOW(), last_validated_at = NOW(),
                           invalidated_at = NULL, validation_error_code = NULL,
                           requires_reauth = FALSE, reauth_notified_at = NULL
                     WHERE user_id = $1 AND token_type = $2
                    """,
                    user_id,
                    token_type,
                )
                if token_type == "bot":
                    await conn.execute(
                        """
                        UPDATE bot_accounts
                           SET requires_reauth = FALSE, last_validated_at = NOW(),
                               revoked_at = NULL
                         WHERE platform_user_id = $1
                        """,
                        user_id,
                    )
                return CredentialHealth(
                    user_id=user_id,
                    token_type=token_type,
                    status="valid",
                    last_checked_at=datetime.now(UTC),
                    last_validated_at=datetime.now(UTC),
                )

    async def _mark_temporarily_unavailable(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: str,
        token_type: TokenType,
        already_requires_reauthorization: bool,
        existing_error_code: str | None,
    ) -> CredentialHealth:
        await conn.execute(
            """
            UPDATE tokens
               SET last_checked_at = NOW(),
                   validation_error_code = CASE
                       WHEN $3 THEN validation_error_code
                       ELSE 'provider_unavailable'
                   END
             WHERE user_id = $1 AND token_type = $2
            """,
            user_id,
            token_type,
            already_requires_reauthorization,
        )
        status: AuthorizationStatus = (
            "requires_reauthorization"
            if already_requires_reauthorization
            else "temporarily_unavailable"
        )
        return CredentialHealth(
            user_id=user_id,
            token_type=token_type,
            status=status,
            last_checked_at=datetime.now(UTC),
            error_code=(
                existing_error_code if already_requires_reauthorization else "provider_unavailable"
            ),
        )

    async def _mark_definitely_invalid(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: str,
        token_type: TokenType,
        error_code: str,
    ) -> CredentialHealth:
        await conn.execute(
            """
            UPDATE tokens
               SET last_checked_at = NOW(), invalidated_at = COALESCE(invalidated_at, NOW()),
                   validation_error_code = $3, requires_reauth = TRUE
             WHERE user_id = $1 AND token_type = $2
            """,
            user_id,
            token_type,
            error_code,
        )
        if token_type == "bot":
            await conn.execute(
                """
                UPDATE bot_accounts
                   SET requires_reauth = TRUE, revoked_at = COALESCE(revoked_at, NOW())
                 WHERE platform_user_id = $1
                """,
                user_id,
            )
            await conn.execute(
                """
                UPDATE channel_bot_settings
                   SET desired_bot_user_id = NULL,
                       active_bot_user_id = NULL,
                       selection_version = selection_version + 1,
                       acked_version = selection_version + 1,
                       status = 'active',
                       last_error_code = $2
                 WHERE desired_bot_user_id = $1 OR active_bot_user_id = $1
                """,
                user_id,
                error_code,
            )
            await conn.execute(
                "SELECT pg_notify('bot_selection_changed', $1)",
                json.dumps({"bot_user_id": user_id, "reason": error_code}),
            )
        else:
            # A definite broadcaster-token failure means Niibot can no longer
            # safely provide channel features. Transient outages never reach here.
            await conn.execute(
                "UPDATE channels SET enabled = FALSE WHERE channel_id = $1",
                user_id,
            )
        return CredentialHealth(
            user_id=user_id,
            token_type=token_type,
            status="requires_reauthorization",
            last_checked_at=datetime.now(UTC),
            error_code=error_code,
        )

    async def list_due_credentials(self, *, limit: int = 25) -> list[tuple[str, TokenType]]:
        """Return a bounded, stable batch that has not been checked in the last 55 minutes."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, token_type
                  FROM tokens
                 WHERE invalidated_at IS NULL
                   AND (last_checked_at IS NULL OR last_checked_at < NOW() - INTERVAL '55 minutes')
                 ORDER BY last_checked_at NULLS FIRST, user_id, token_type
                 LIMIT $1
                """,
                limit,
            )
        result: list[tuple[str, TokenType]] = []
        for row in rows:
            token_type = str(row["token_type"])
            if token_type == "bot":
                result.append((str(row["user_id"]), "bot"))
            elif token_type == "broadcaster":
                result.append((str(row["user_id"]), "broadcaster"))
        return result

    async def check_due_credentials(self, *, limit: int = 25) -> int:
        require_twitch_token_encryption_key(self.token_encryption_key)
        due = await self.list_due_credentials(limit=limit)
        for user_id, token_type in due:
            required = set(BOT_SCOPES if token_type == "bot" else BROADCASTER_SCOPES)
            try:
                await self.check_credential(
                    user_id=user_id,
                    token_type=token_type,
                    required_scopes=required,
                    force=False,
                )
            except CredentialNotFoundError:
                continue
            except Exception:
                LOGGER.exception(
                    "Twitch credential reconciliation failed",
                    extra={"user_id": user_id, "token_type": token_type},
                )
                try:
                    async with self.pool.acquire() as conn:
                        await conn.execute(
                            """
                            UPDATE tokens
                               SET last_checked_at = NOW(),
                                   validation_error_code = CASE
                                       WHEN invalidated_at IS NULL
                                           THEN 'provider_unavailable'
                                       ELSE validation_error_code
                                   END
                             WHERE user_id = $1 AND token_type = $2
                            """,
                            user_id,
                            token_type,
                        )
                except Exception:
                    LOGGER.exception(
                        "Failed to defer Twitch credential after reconciliation error",
                        extra={"user_id": user_id, "token_type": token_type},
                    )
        return len(due)

    async def get_broadcaster_summary(self, *, channel_id: str) -> BroadcasterAuthorizationSummary:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT channel.channel_id, channel.channel_name, channel.display_name,
                       channel.enabled, token.user_id AS token_user_id, token.requires_reauth,
                       token.last_checked_at, token.last_validated_at,
                       token.invalidated_at, token.validation_error_code
                  FROM channels channel
                  LEFT JOIN tokens token
                    ON token.user_id = channel.channel_id
                   AND token.token_type = 'broadcaster'
                 WHERE channel.channel_id = $1
                """,
                channel_id,
            )
        if row is None:
            raise CredentialNotFoundError()
        if row["token_user_id"] is None:
            # A channel without a matching token is disconnected, not merely unchecked.
            status: AuthorizationStatus = "requires_reauthorization"
        else:
            status = self._health_status(row)
        return BroadcasterAuthorizationSummary(
            channel_id=str(row["channel_id"]),
            channel_name=str(row["channel_name"]),
            display_name=row["display_name"],
            enabled=bool(row["enabled"]),
            status=status,
            last_checked_at=row["last_checked_at"],
            last_validated_at=row["last_validated_at"],
            error_code=row["validation_error_code"],
        )

    async def _revoke_removed_token(self, access_token: str | None) -> bool:
        """Best-effort upstream cleanup after the local transaction has committed."""
        if access_token is None:
            return False
        try:
            revoke = await self.twitch.revoke_access_token(access_token)
        except Exception:
            # Local removal is already complete. Never turn that successful,
            # privacy-preserving result into a misleading API failure.
            LOGGER.exception("Twitch token revocation failed after local credential removal")
            return False
        return revoke.status in {"revoked", "already_invalid"}

    async def unlink_bot_from_tenant(
        self,
        *,
        channel_id: str,
        bot_user_id: str,
        actor_user_id: str,
    ) -> AuthorizationRemovalResult:
        token_encryption_key = require_twitch_token_encryption_key(self.token_encryption_key)
        access_token: str | None = None
        credential_retained = True
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                account = await conn.fetchrow(
                    """
                    SELECT account.is_system_default, account.platform_user_id
                      FROM bot_accounts account
                     WHERE account.platform_user_id = $1
                     FOR UPDATE
                    """,
                    bot_user_id,
                )
                if account is None:
                    raise CredentialNotFoundError()
                if bool(account["is_system_default"]):
                    raise SystemBotProtectedError()

                # Count mappings only after acquiring the account lock. Concurrent
                # tenant unlinks for this shared credential are therefore serialized,
                # and this second READ COMMITTED statement sees the committed result.
                mapping = await conn.fetchrow(
                    """
                    SELECT COALESCE(settings.active_bot_user_id = mapping.bot_user_id, FALSE)
                               AS is_active,
                           COALESCE(settings.desired_bot_user_id = mapping.bot_user_id, FALSE)
                               AS is_desired,
                           (SELECT COUNT(*) FROM channel_bot_accounts all_mappings
                             WHERE all_mappings.bot_user_id = mapping.bot_user_id) AS mapping_count
                      FROM channel_bot_accounts mapping
                      LEFT JOIN channel_bot_settings settings
                        ON settings.channel_id = mapping.channel_id
                     WHERE mapping.channel_id = $1 AND mapping.bot_user_id = $2
                    """,
                    channel_id,
                    bot_user_id,
                )
                if mapping is None:
                    raise CredentialNotFoundError()
                if bool(mapping["is_active"]) or bool(mapping["is_desired"]):
                    raise BotAccountInUseError()

                if int(mapping["mapping_count"]) == 1:
                    credential_retained = False
                    credential = await conn.fetchrow(
                        """
                        SELECT token, encryption_version
                          FROM tokens
                         WHERE user_id = $1 AND token_type = 'bot'
                         FOR UPDATE
                        """,
                        bot_user_id,
                    )
                    if credential is not None:
                        access_token = decrypt_twitch_token(
                            str(credential["token"]),
                            version=int(credential["encryption_version"]),
                            key=token_encryption_key,
                        )

                await conn.execute(
                    "DELETE FROM channel_bot_accounts WHERE channel_id = $1 AND bot_user_id = $2",
                    channel_id,
                    bot_user_id,
                )
                if not credential_retained:
                    await conn.execute(
                        "DELETE FROM tokens WHERE user_id = $1 AND token_type = 'bot'",
                        bot_user_id,
                    )
                    await conn.execute(
                        """
                        UPDATE bot_accounts
                           SET requires_reauth = TRUE, revoked_at = NOW()
                         WHERE platform_user_id = $1
                        """,
                        bot_user_id,
                    )
                await conn.execute(
                    """
                    INSERT INTO tenant_audit_events
                        (channel_id, actor_user_id, event_type, target_type, target_id, metadata)
                    VALUES ($1, $2::uuid, 'bot_account.unlinked', 'bot_account', $3,
                            jsonb_build_object('credential_retained', $4::boolean))
                    """,
                    channel_id,
                    actor_user_id,
                    bot_user_id,
                    credential_retained,
                )
                await conn.execute(
                    "SELECT pg_notify('bot_selection_changed', $1)",
                    json.dumps({"channel_id": channel_id, "bot_user_id": bot_user_id}),
                )

        revoke_confirmed = await self._revoke_removed_token(access_token)
        return AuthorizationRemovalResult(
            credential_retained=credential_retained,
            upstream_revoke_confirmed=revoke_confirmed,
        )

    async def disconnect_broadcaster(
        self,
        *,
        channel_id: str,
        owner_user_id: str,
    ) -> AuthorizationRemovalResult:
        token_encryption_key = require_twitch_token_encryption_key(self.token_encryption_key)
        access_token: str | None = None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT token, encryption_version
                      FROM tokens
                     WHERE user_id = $1 AND token_type = 'broadcaster'
                     FOR UPDATE
                    """,
                    channel_id,
                )
                if row is None:
                    raise CredentialNotFoundError()
                access_token = decrypt_twitch_token(
                    str(row["token"]),
                    version=int(row["encryption_version"]),
                    key=token_encryption_key,
                )
                await conn.execute(
                    "UPDATE channels SET enabled = FALSE WHERE channel_id = $1",
                    channel_id,
                )
                await conn.execute(
                    "UPDATE users SET session_version = session_version + 1 WHERE id = $1::uuid",
                    owner_user_id,
                )
                await conn.execute(
                    "DELETE FROM tokens WHERE user_id = $1 AND token_type = 'broadcaster'",
                    channel_id,
                )
                await conn.execute(
                    """
                    INSERT INTO tenant_audit_events
                        (channel_id, actor_user_id, event_type, target_type, target_id, metadata)
                    VALUES ($1, $2::uuid, 'broadcaster.disconnected', 'twitch_authorization',
                            $1, '{"historical_data_retained": true}'::jsonb)
                    """,
                    channel_id,
                    owner_user_id,
                )
                await conn.execute(
                    "SELECT pg_notify('token_reauth', $1)",
                    json.dumps({"user_id": channel_id, "disconnected": True}),
                )

        return AuthorizationRemovalResult(
            credential_retained=False,
            upstream_revoke_confirmed=await self._revoke_removed_token(access_token),
        )
