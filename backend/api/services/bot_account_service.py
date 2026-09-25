"""Tenant-private bot accounts and one-time Twitch OAuth invitations."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import quote, urlencode
from uuid import uuid4

import asyncpg

from shared.errors import ConflictError, InvalidInputError, NotFoundError
from shared.twitch_scopes import BOT_SCOPES
from shared.twitch_token_crypto import (
    encrypt_twitch_token,
    require_twitch_token_encryption_key,
)

BotInvitePurpose = Literal["link_new", "reauthorize", "system_default_reset"]


@dataclass(frozen=True)
class BotInviteCreated:
    id: str
    public_token: str
    state_nonce: str
    expires_at: datetime


@dataclass(frozen=True)
class BotAuthorizationResult:
    channel_id: str
    platform_user_id: str
    login: str
    display_name: str
    avatar: str | None


@dataclass(frozen=True)
class BotAccountSummary:
    platform_user_id: str
    login: str
    display_name: str
    avatar: str | None
    requires_reauth: bool
    last_validated_at: datetime | None
    revoked_at: datetime | None
    last_checked_at: datetime | None = None
    validation_error_code: str | None = None
    linked_at: datetime | None = None
    is_active: bool = False
    is_desired: bool = False


@dataclass(frozen=True)
class PublicBotInviteSummary:
    invite_id: str
    channel_name: str
    display_name: str | None
    purpose: BotInvitePurpose
    status: Literal["pending", "authorized", "declined", "expired"]
    expires_at: datetime


@dataclass(frozen=True)
class BotInviteStatus:
    id: str
    status: Literal["pending", "authorized", "declined", "expired"]
    expires_at: datetime
    consumed_at: datetime | None
    account: BotAccountSummary | None


class BotInviteNotFoundError(NotFoundError):
    code = "BOT_INVITE.NOT_FOUND"
    user_message = "這個 Bot 授權連結無效"


class BotAccountNotFoundError(NotFoundError):
    code = "BOT_ACCOUNT.NOT_FOUND"
    user_message = "找不到這個 Bot 帳號"


class BotInviteExpiredError(ConflictError):
    code = "BOT_INVITE.EXPIRED"
    user_message = "這個 Bot 授權連結已過期"


class BotInviteReplayError(ConflictError):
    code = "BOT_INVITE.ALREADY_USED"
    user_message = "這個 Bot 授權連結已經使用過"


class BotInviteLimitError(ConflictError):
    code = "BOT_INVITE.LIMIT_REACHED"
    user_message = "待處理的 Bot 邀請已達上限"


class BotInviteWrongAccountError(ConflictError):
    code = "BOT_INVITE.WRONG_ACCOUNT"
    user_message = "登入的 Twitch 帳號不符合授權目標"


class BotMissingScopesError(InvalidInputError):
    code = "BOT_ACCOUNT.MISSING_SCOPES"
    user_message = "Bot 權限不完整，請重新授權"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def build_bot_invite_url(frontend_url: str, created: BotInviteCreated) -> str:
    token = quote(created.public_token, safe="")
    query = urlencode({"nonce": created.state_nonce})
    return f"{frontend_url.rstrip('/')}/bot-invite/{token}?{query}"


class BotAccountService:
    """Owns invitation consumption and the credential/mapping transaction."""

    def __init__(self, pool: asyncpg.Pool, *, token_encryption_key: str) -> None:
        self.pool = pool
        self.token_encryption_key = token_encryption_key

    async def create_invite(
        self,
        *,
        channel_id: str,
        creator_user_id: str,
        purpose: BotInvitePurpose = "link_new",
        expected_bot_user_id: str | None = None,
        lifetime: timedelta = timedelta(minutes=30),
    ) -> BotInviteCreated:
        """Create a one-time invitation and return its secrets exactly once."""
        require_twitch_token_encryption_key(self.token_encryption_key)
        if purpose != "link_new" and not expected_bot_user_id:
            raise ValueError("expected_bot_user_id is required for reset invitations")

        invite_id = str(uuid4())
        public_token = secrets.token_urlsafe(32)
        state_nonce = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + lifetime

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if purpose == "reauthorize":
                    linked = await conn.fetchval(
                        """
                        SELECT EXISTS (
                            SELECT 1
                              FROM channel_bot_accounts
                             WHERE channel_id = $1
                               AND bot_user_id = $2
                        )
                        """,
                        channel_id,
                        expected_bot_user_id,
                    )
                    if not linked:
                        raise BotAccountNotFoundError()
                elif purpose == "system_default_reset":
                    # The first web reset must be able to bootstrap the registry
                    # before any bot_accounts row exists. This placeholder carries
                    # no credential and is not globally visible until the callback
                    # proves the configured account and marks it system-default.
                    await conn.execute(
                        """
                        INSERT INTO bot_accounts
                            (platform_user_id, login, display_name)
                        VALUES ($1, $1, $1)
                        ON CONFLICT (platform_user_id) DO NOTHING
                        """,
                        expected_bot_user_id,
                    )
                # Serialize invite creation per tenant so concurrent requests
                # cannot both pass the D5 five-pending-invite limit.
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"bot-invite:{channel_id}",
                )
                pending_count = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                      FROM bot_oauth_invites
                     WHERE channel_id = $1
                       AND status = 'pending'
                       AND expires_at > NOW()
                    """,
                    channel_id,
                )
                if int(pending_count or 0) >= 5:
                    raise BotInviteLimitError(context={"channel_id": channel_id})

                row = await conn.fetchrow(
                    """
                    INSERT INTO bot_oauth_invites
                        (id, channel_id, purpose, expected_bot_user_id,
                         created_by_user_id, public_token_hash, state_nonce_hash,
                         expires_at)
                    VALUES ($1::uuid, $2, $3, $4, $5::uuid, $6, $7, $8)
                    RETURNING id::text, expires_at
                    """,
                    invite_id,
                    channel_id,
                    purpose,
                    expected_bot_user_id,
                    creator_user_id,
                    _sha256(public_token),
                    _sha256(state_nonce),
                    expires_at,
                )

        return BotInviteCreated(
            id=str(row["id"]),
            public_token=public_token,
            state_nonce=state_nonce,
            expires_at=row["expires_at"],
        )

    async def get_public_invite(
        self,
        *,
        public_token: str,
        state_nonce: str,
    ) -> PublicBotInviteSummary:
        """Resolve only the consent-page fields for a valid invite capability."""
        async with self.pool.acquire() as conn:
            invite = await conn.fetchrow(
                """
                SELECT invite.id::text AS invite_id,
                       invite.purpose,
                       invite.state_nonce_hash,
                       invite.status,
                       invite.expires_at,
                       channel.channel_name,
                       channel.display_name
                  FROM bot_oauth_invites invite
                  JOIN channels channel
                    ON channel.channel_id = invite.channel_id
                 WHERE invite.public_token_hash = $1
                """,
                _sha256(public_token),
            )
        if invite is None or not hmac.compare_digest(
            str(invite["state_nonce_hash"]), _sha256(state_nonce)
        ):
            raise BotInviteNotFoundError()

        status = str(invite["status"])
        if status == "pending" and invite["expires_at"] <= datetime.now(UTC):
            status = "expired"
        return PublicBotInviteSummary(
            invite_id=str(invite["invite_id"]),
            channel_name=str(invite["channel_name"]),
            display_name=invite["display_name"],
            purpose=str(invite["purpose"]),  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            expires_at=invite["expires_at"],
        )

    async def decline_invite(self, *, public_token: str, state_nonce: str) -> None:
        """Consume an invitation as declined without creating any credential."""
        now = datetime.now(UTC)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                invite = await conn.fetchrow(
                    """
                    SELECT id::text, channel_id,
                           state_nonce_hash, status, expires_at, consumed_at
                      FROM bot_oauth_invites
                     WHERE public_token_hash = $1
                     FOR UPDATE
                    """,
                    _sha256(public_token),
                )
                if invite is None or not hmac.compare_digest(
                    str(invite["state_nonce_hash"]), _sha256(state_nonce)
                ):
                    raise BotInviteNotFoundError()
                if invite["status"] != "pending" or invite["consumed_at"] is not None:
                    raise BotInviteReplayError()
                if invite["expires_at"] <= now:
                    raise BotInviteExpiredError()

                await conn.execute(
                    """
                    UPDATE bot_oauth_invites
                       SET status = 'declined', consumed_at = $2
                     WHERE id = $1::uuid
                    """,
                    invite["id"],
                    now,
                )
                await conn.execute(
                    """
                    INSERT INTO tenant_audit_events
                        (channel_id, event_type, target_type, target_id, metadata)
                    VALUES ($1, 'bot_invite.declined', 'bot_invite', $2, '{}'::jsonb)
                    """,
                    invite["channel_id"],
                    invite["id"],
                )

    async def authorize_invite(
        self,
        *,
        invite_id: str,
        state_nonce: str,
        platform_user_id: str,
        access_token: str,
        refresh_token: str,
        scopes: set[str],
        login: str,
        display_name: str,
        avatar: str | None,
    ) -> BotAuthorizationResult:
        """Consume an invitation and atomically persist the bot for its tenant."""
        token_encryption_key = require_twitch_token_encryption_key(self.token_encryption_key)
        now = datetime.now(UTC)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                invite = await conn.fetchrow(
                    """
                    SELECT id::text, channel_id, purpose, expected_bot_user_id,
                           created_by_user_id::text, state_nonce_hash, status,
                           expires_at, consumed_at
                      FROM bot_oauth_invites
                     WHERE id = $1::uuid
                     FOR UPDATE
                    """,
                    invite_id,
                )
                if invite is None or not hmac.compare_digest(
                    str(invite["state_nonce_hash"]), _sha256(state_nonce)
                ):
                    raise BotInviteNotFoundError()
                if invite["status"] != "pending" or invite["consumed_at"] is not None:
                    raise BotInviteReplayError()
                if invite["expires_at"] <= now:
                    raise BotInviteExpiredError()

                missing_scopes = [scope for scope in BOT_SCOPES if scope not in scopes]
                if missing_scopes:
                    raise BotMissingScopesError(context={"missing_scopes": missing_scopes})

                expected_bot_user_id = invite["expected_bot_user_id"]
                if expected_bot_user_id and expected_bot_user_id != platform_user_id:
                    raise BotInviteWrongAccountError(
                        context={"expected_bot_user_id": expected_bot_user_id}
                    )

                encrypted_access, encryption_version = encrypt_twitch_token(
                    access_token, token_encryption_key
                )
                encrypted_refresh, refresh_version = encrypt_twitch_token(
                    refresh_token, token_encryption_key
                )
                if refresh_version != encryption_version:
                    raise RuntimeError("Twitch credential encryption versions diverged")

                identity = await conn.fetchrow(
                    """
                    SELECT id::text
                      FROM identities
                     WHERE platform = 'twitch'
                       AND platform_user_id = $1
                    """,
                    platform_user_id,
                )
                identity_id = str(identity["id"]) if identity else None
                normalized_scopes = " ".join(sorted(scopes))

                # Match lifecycle validation/unlink lock ordering. New accounts
                # have no row to lock and cannot yet be visible to those flows.
                await conn.execute(
                    """
                    SELECT platform_user_id
                      FROM bot_accounts
                     WHERE platform_user_id = $1
                     FOR UPDATE
                    """,
                    platform_user_id,
                )
                await conn.execute(
                    """
                    INSERT INTO tokens
                        (user_id, token, refresh, token_type, scopes, identity_id,
                         requires_reauth, encryption_version, last_checked_at,
                         last_validated_at, next_validation_at, invalidated_at,
                         validation_error_code)
                    VALUES (
                        $1, $2, $3, 'bot', $4, $5::uuid, FALSE, $6, $7, $7,
                        $7 + INTERVAL '55 minutes', NULL, NULL
                    )
                    ON CONFLICT (user_id, token_type) DO UPDATE SET
                        token = EXCLUDED.token,
                        refresh = EXCLUDED.refresh,
                        scopes = EXCLUDED.scopes,
                        identity_id = COALESCE(EXCLUDED.identity_id, tokens.identity_id),
                        requires_reauth = FALSE,
                        encryption_version = EXCLUDED.encryption_version,
                        last_checked_at = EXCLUDED.last_checked_at,
                        last_validated_at = EXCLUDED.last_validated_at,
                        next_validation_at = EXCLUDED.next_validation_at,
                        invalidated_at = NULL,
                        validation_error_code = NULL,
                        credential_revision = tokens.credential_revision + 1,
                        updated_at = NOW()
                    """,
                    platform_user_id,
                    encrypted_access,
                    encrypted_refresh,
                    normalized_scopes,
                    identity_id,
                    encryption_version,
                    now,
                )
                await conn.execute(
                    """
                    INSERT INTO bot_accounts
                        (platform_user_id, identity_id, login, display_name, avatar,
                         requires_reauth, last_validated_at, revoked_at)
                    VALUES ($1, $2::uuid, $3, $4, $5, FALSE, $6, NULL)
                    ON CONFLICT (platform_user_id) DO UPDATE SET
                        identity_id = COALESCE(EXCLUDED.identity_id, bot_accounts.identity_id),
                        login = EXCLUDED.login,
                        display_name = EXCLUDED.display_name,
                        avatar = EXCLUDED.avatar,
                        requires_reauth = FALSE,
                        last_validated_at = EXCLUDED.last_validated_at,
                        revoked_at = NULL,
                        updated_at = NOW()
                    """,
                    platform_user_id,
                    identity_id,
                    login,
                    display_name,
                    avatar,
                    now,
                )

                purpose = str(invite["purpose"])
                if purpose == "system_default_reset":
                    await conn.execute(
                        """
                        UPDATE bot_accounts
                           SET is_system_default = FALSE
                         WHERE is_system_default
                           AND platform_user_id <> $1
                        """,
                        platform_user_id,
                    )
                    await conn.execute(
                        """
                        UPDATE bot_accounts
                           SET is_system_default = TRUE
                         WHERE platform_user_id = $1
                        """,
                        platform_user_id,
                    )
                else:
                    await conn.execute(
                        """
                        INSERT INTO channel_bot_accounts
                            (channel_id, bot_user_id, linked_by_user_id,
                             linked_via_invite_id)
                        VALUES ($1, $2, $3::uuid, $4::uuid)
                        ON CONFLICT (channel_id, bot_user_id) DO UPDATE SET
                            linked_by_user_id = EXCLUDED.linked_by_user_id,
                            linked_via_invite_id = EXCLUDED.linked_via_invite_id,
                            linked_at = NOW()
                        """,
                        invite["channel_id"],
                        platform_user_id,
                        invite["created_by_user_id"],
                        invite["id"],
                    )

                await conn.execute(
                    """
                    UPDATE bot_oauth_invites
                       SET status = 'authorized',
                           consumed_at = $2,
                           authorized_bot_user_id = $3
                     WHERE id = $1::uuid
                    """,
                    invite["id"],
                    now,
                    platform_user_id,
                )
                await conn.execute(
                    """
                    INSERT INTO tenant_audit_events
                        (channel_id, actor_user_id, external_actor_user_id,
                         event_type, target_type, target_id, metadata)
                    VALUES ($1, $2::uuid, $3, $4, 'bot_account', $3, $5::jsonb)
                    """,
                    invite["channel_id"],
                    invite["created_by_user_id"],
                    platform_user_id,
                    f"bot_account.{purpose}.authorized",
                    json.dumps({"invite_id": invite["id"]}),
                )
                await conn.execute(
                    "SELECT pg_notify('bot_token_updated', $1)",
                    json.dumps({"user_id": platform_user_id}),
                )

        return BotAuthorizationResult(
            channel_id=str(invite["channel_id"]),
            platform_user_id=platform_user_id,
            login=login,
            display_name=display_name,
            avatar=avatar,
        )

    async def list_for_tenant(self, channel_id: str) -> list[BotAccountSummary]:
        """List custom accounts explicitly mapped to one tenant."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT account.platform_user_id,
                       account.login,
                       account.display_name,
                       account.avatar,
                       account.requires_reauth,
                       account.last_validated_at,
                       account.revoked_at,
                       token.last_checked_at,
                       token.validation_error_code,
                       mapping.linked_at,
                       COALESCE(settings.active_bot_user_id = account.platform_user_id, FALSE)
                           AS is_active,
                       COALESCE(settings.desired_bot_user_id = account.platform_user_id, FALSE)
                           AS is_desired
                  FROM bot_accounts account
                  JOIN channel_bot_accounts mapping
                    ON mapping.bot_user_id = account.platform_user_id
                  LEFT JOIN tokens token
                    ON token.user_id = account.platform_user_id
                   AND token.token_type = 'bot'
                  LEFT JOIN channel_bot_settings settings
                    ON settings.channel_id = mapping.channel_id
                 WHERE mapping.channel_id = $1
                 ORDER BY mapping.linked_at ASC, account.platform_user_id ASC
                """,
                channel_id,
            )
        return [BotAccountSummary(**dict(row)) for row in rows]

    async def assert_available_to_tenant(self, *, channel_id: str, bot_user_id: str) -> None:
        """Allow only the global system account or an explicit tenant mapping."""
        async with self.pool.acquire() as conn:
            available = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                      FROM bot_accounts account
                      LEFT JOIN channel_bot_accounts mapping
                        ON mapping.bot_user_id = account.platform_user_id
                       AND mapping.channel_id = $1
                     WHERE account.platform_user_id = $2
                       AND (account.is_system_default OR mapping.channel_id IS NOT NULL)
                )
                """,
                channel_id,
                bot_user_id,
            )
        if not available:
            raise BotAccountNotFoundError()

    async def get_system_default(self) -> BotAccountSummary | None:
        """Return the one globally visible account, never arbitrary custom rows."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT platform_user_id, login, display_name, avatar,
                       account.requires_reauth, account.last_validated_at,
                       account.revoked_at, token.last_checked_at,
                       token.validation_error_code
                  FROM bot_accounts account
                  LEFT JOIN tokens token
                    ON token.user_id = account.platform_user_id
                   AND token.token_type = 'bot'
                 WHERE account.is_system_default = TRUE
                """
            )
        return BotAccountSummary(**dict(row)) if row else None

    async def get_invite_status(
        self,
        *,
        channel_id: str,
        invite_id: str,
    ) -> BotInviteStatus:
        """Poll one owner-visible invitation without returning its capabilities."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT invite.id::text,
                       invite.status,
                       invite.expires_at,
                       invite.consumed_at,
                       account.platform_user_id,
                       account.login,
                       account.display_name,
                       account.avatar,
                       account.requires_reauth,
                       account.last_validated_at,
                       account.revoked_at
                  FROM bot_oauth_invites invite
                  LEFT JOIN bot_accounts account
                    ON account.platform_user_id = invite.authorized_bot_user_id
                 WHERE invite.id = $1::uuid
                   AND invite.channel_id = $2
                """,
                invite_id,
                channel_id,
            )
        if row is None:
            raise BotInviteNotFoundError()

        resolved_status = str(row["status"])
        if resolved_status == "pending" and row["expires_at"] <= datetime.now(UTC):
            resolved_status = "expired"
        account = None
        if row["platform_user_id"] is not None:
            account = BotAccountSummary(
                platform_user_id=str(row["platform_user_id"]),
                login=str(row["login"]),
                display_name=str(row["display_name"]),
                avatar=row["avatar"],
                requires_reauth=bool(row["requires_reauth"]),
                last_validated_at=row["last_validated_at"],
                revoked_at=row["revoked_at"],
            )
        return BotInviteStatus(
            id=str(row["id"]),
            status=resolved_status,  # type: ignore[arg-type]
            expires_at=row["expires_at"],
            consumed_at=row["consumed_at"],
            account=account,
        )
