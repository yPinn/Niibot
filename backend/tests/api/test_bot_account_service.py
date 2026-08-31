"""Bot OAuth invite service security and transaction contracts."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from api.services.bot_account_service import (
    BotAccountNotFoundError,
    BotAccountService,
    BotInviteExpiredError,
    BotInviteLimitError,
    BotInviteNotFoundError,
    BotInviteReplayError,
    BotInviteWrongAccountError,
    BotMissingScopesError,
)
from cryptography.fernet import Fernet

from shared.twitch_scopes import BOT_SCOPES
from shared.twitch_token_crypto import decrypt_twitch_token

_KEY = Fernet.generate_key().decode()
_NOW = datetime.now(UTC)
_STATE_NONCE = "state-nonce"


def _pool_with(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


def _tx_cm() -> MagicMock:
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=None)
    return tx


def _invite_row(**overrides):
    row = {
        "id": "11111111-2222-3333-4444-555555555555",
        "channel_id": "channel-a",
        "purpose": "link_new",
        "expected_bot_user_id": None,
        "created_by_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "status": "pending",
        "expires_at": _NOW + timedelta(minutes=20),
        "consumed_at": None,
        "state_nonce_hash": hashlib.sha256(_STATE_NONCE.encode()).hexdigest(),
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_create_invite_persists_only_hashes_and_returns_raw_token_once():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_tx_cm())
    conn.fetchval.return_value = 0
    conn.fetchrow.return_value = {
        "id": "11111111-2222-3333-4444-555555555555",
        "expires_at": _NOW + timedelta(minutes=30),
    }
    service = BotAccountService(_pool_with(conn), token_encryption_key=_KEY)

    created = await service.create_invite(
        channel_id="channel-a",
        creator_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )

    sql, *args = conn.fetchrow.await_args.args
    assert "public_token_hash" in sql
    assert "state_nonce_hash" in sql
    assert created.public_token not in args
    assert hashlib.sha256(created.public_token.encode()).hexdigest() in args
    assert created.expires_at > _NOW


@pytest.mark.asyncio
async def test_create_invite_caps_pending_links_per_tenant():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_tx_cm())
    conn.fetchval.return_value = 5
    service = BotAccountService(_pool_with(conn), token_encryption_key=_KEY)

    with pytest.raises(BotInviteLimitError):
        await service.create_invite(
            channel_id="channel-a",
            creator_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        )

    conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_system_reset_invite_bootstraps_expected_account_registry_row():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_tx_cm())
    conn.fetchval.return_value = 0
    conn.fetchrow.return_value = {
        "id": "11111111-2222-3333-4444-555555555555",
        "expires_at": _NOW + timedelta(minutes=30),
    }
    service = BotAccountService(_pool_with(conn), token_encryption_key=_KEY)

    await service.create_invite(
        channel_id="channel-a",
        creator_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        purpose="system_default_reset",
        expected_bot_user_id="niibot-id",
    )

    bootstrap = next(
        call.args
        for call in conn.execute.await_args_list
        if "INSERT INTO bot_accounts" in call.args[0]
    )
    assert bootstrap[1:] == ("niibot-id",)
    assert "is_system_default" not in bootstrap[0]


@pytest.mark.asyncio
async def test_reauthorize_invite_cannot_target_another_tenants_bot():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_tx_cm())
    conn.fetchval.return_value = False
    service = BotAccountService(_pool_with(conn), token_encryption_key=_KEY)

    with pytest.raises(BotAccountNotFoundError):
        await service.create_invite(
            channel_id="channel-a",
            creator_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            purpose="reauthorize",
            expected_bot_user_id="bot-from-channel-c",
        )

    sql, channel_id, bot_id = conn.fetchval.await_args.args
    assert "channel_bot_accounts" in sql
    assert (channel_id, bot_id) == ("channel-a", "bot-from-channel-c")


@pytest.mark.asyncio
async def test_missing_bot_scope_fails_before_any_credential_write():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_tx_cm())
    conn.fetchrow.return_value = _invite_row()
    service = BotAccountService(_pool_with(conn), token_encryption_key=_KEY)

    with pytest.raises(BotMissingScopesError):
        await service.authorize_invite(
            invite_id=_invite_row()["id"],
            state_nonce=_STATE_NONCE,
            platform_user_id="bot-b",
            access_token="access",
            refresh_token="refresh",
            scopes={"user:bot"},
            login="bot_b",
            display_name="Bot B",
            avatar=None,
        )

    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_or_consumed_invite_fails_closed():
    for row, error in (
        (_invite_row(expires_at=_NOW - timedelta(seconds=1)), BotInviteExpiredError),
        (_invite_row(status="authorized", consumed_at=_NOW), BotInviteReplayError),
    ):
        conn = AsyncMock()
        conn.transaction = MagicMock(return_value=_tx_cm())
        conn.fetchrow.return_value = row
        service = BotAccountService(_pool_with(conn), token_encryption_key=_KEY)

        with pytest.raises(error):
            await service.authorize_invite(
                invite_id=_invite_row()["id"],
                state_nonce=_STATE_NONCE,
                platform_user_id="bot-b",
                access_token="access",
                refresh_token="refresh",
                scopes=set(BOT_SCOPES),
                login="bot_b",
                display_name="Bot B",
                avatar=None,
            )


@pytest.mark.asyncio
async def test_expected_account_cannot_be_substituted_in_callback():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_tx_cm())
    conn.fetchrow.return_value = _invite_row(
        purpose="reauthorize", expected_bot_user_id="expected-bot"
    )
    service = BotAccountService(_pool_with(conn), token_encryption_key=_KEY)

    with pytest.raises(BotInviteWrongAccountError):
        await service.authorize_invite(
            invite_id=_invite_row()["id"],
            state_nonce=_STATE_NONCE,
            platform_user_id="attacker-bot",
            access_token="access",
            refresh_token="refresh",
            scopes=set(BOT_SCOPES),
            login="attacker",
            display_name="Attacker",
            avatar=None,
        )


@pytest.mark.asyncio
async def test_success_encrypts_token_and_atomically_maps_only_invite_tenant():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_tx_cm())
    conn.fetchrow.side_effect = [_invite_row(), None]
    conn.execute.return_value = "INSERT 0 1"
    service = BotAccountService(_pool_with(conn), token_encryption_key=_KEY)

    result = await service.authorize_invite(
        invite_id=_invite_row()["id"],
        state_nonce=_STATE_NONCE,
        platform_user_id="bot-b",
        access_token="access-secret",
        refresh_token="refresh-secret",
        scopes=set(BOT_SCOPES),
        login="bot_b",
        display_name="Bot B",
        avatar="https://example.test/avatar.png",
    )

    assert result.channel_id == "channel-a"
    statements = [call.args for call in conn.execute.await_args_list]
    token_write = next(args for args in statements if "INSERT INTO tokens" in args[0])
    assert "access-secret" not in token_write[1:]
    assert "refresh-secret" not in token_write[1:]
    assert decrypt_twitch_token(token_write[2], version=1, key=_KEY) == "access-secret"
    assert decrypt_twitch_token(token_write[3], version=1, key=_KEY) == "refresh-secret"

    mapping_write = next(
        args for args in statements if "INSERT INTO channel_bot_accounts" in args[0]
    )
    assert mapping_write[1:] == (
        "channel-a",
        "bot-b",
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        _invite_row()["id"],
    )
    assert any("status = 'authorized'" in args[0] for args in statements)
    assert any("INSERT INTO tenant_audit_events" in args[0] for args in statements)
    notify = next(args for args in statements if "pg_notify('bot_token_updated'" in args[0])
    assert "access-secret" not in notify
    assert "refresh-secret" not in notify


@pytest.mark.asyncio
async def test_tenant_list_query_never_reads_global_custom_accounts_without_mapping():
    conn = AsyncMock()
    conn.fetch.return_value = []
    service = BotAccountService(_pool_with(conn), token_encryption_key=_KEY)

    assert await service.list_for_tenant("channel-a") == []

    sql, channel_id = conn.fetch.await_args.args
    assert "JOIN channel_bot_accounts" in sql
    assert "mapping.channel_id = $1" in sql
    assert channel_id == "channel-a"


@pytest.mark.asyncio
async def test_invite_poll_is_bound_to_both_tenant_and_invite_id():
    conn = AsyncMock()
    conn.fetchrow.return_value = {
        "id": _invite_row()["id"],
        "status": "authorized",
        "expires_at": _NOW + timedelta(minutes=20),
        "consumed_at": _NOW,
        "platform_user_id": "bot-b",
        "login": "bot_b",
        "display_name": "Bot B",
        "avatar": None,
        "requires_reauth": False,
        "last_validated_at": _NOW,
        "revoked_at": None,
    }
    service = BotAccountService(_pool_with(conn), token_encryption_key=_KEY)

    result = await service.get_invite_status(
        channel_id="channel-a",
        invite_id=_invite_row()["id"],
    )

    assert result.status == "authorized"
    sql, invite_id, channel_id = conn.fetchrow.await_args.args
    assert "invite.id = $1::uuid" in sql
    assert "invite.channel_id = $2" in sql
    assert invite_id == _invite_row()["id"]
    assert channel_id == "channel-a"


@pytest.mark.asyncio
async def test_public_invite_requires_both_capabilities_and_returns_safe_summary():
    conn = AsyncMock()
    conn.fetchrow.return_value = {
        **_invite_row(),
        "invite_id": _invite_row()["id"],
        "channel_name": "alice",
        "display_name": "Alice",
    }
    service = BotAccountService(_pool_with(conn), token_encryption_key=_KEY)

    summary = await service.get_public_invite(
        public_token="opaque",
        state_nonce=_STATE_NONCE,
    )

    assert summary.channel_name == "alice"
    sql, token_hash = conn.fetchrow.await_args.args
    assert "public_token_hash = $1" in sql
    assert token_hash == hashlib.sha256(b"opaque").hexdigest()
    assert not hasattr(summary, "created_by_user_id")

    conn.fetchrow.return_value = {
        **_invite_row(),
        "invite_id": _invite_row()["id"],
        "channel_name": "alice",
        "display_name": "Alice",
    }
    with pytest.raises(BotInviteNotFoundError):
        await service.get_public_invite(
            public_token="opaque",
            state_nonce="wrong-nonce",
        )


@pytest.mark.asyncio
async def test_decline_consumes_pending_invite_once_without_creating_credentials():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_tx_cm())
    conn.fetchrow.return_value = _invite_row()
    service = BotAccountService(_pool_with(conn), token_encryption_key=_KEY)

    await service.decline_invite(
        public_token="opaque",
        state_nonce=_STATE_NONCE,
    )

    writes = [call.args for call in conn.execute.await_args_list]
    assert any("status = 'declined'" in args[0] for args in writes)
    assert all("INSERT INTO tokens" not in args[0] for args in writes)
