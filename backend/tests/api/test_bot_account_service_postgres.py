"""PostgreSQL integration regression for bot OAuth invitation consumption."""

from __future__ import annotations

import os
from uuid import uuid4

import asyncpg
import pytest
from api.services.bot_account_service import BotAccountService
from cryptography.fernet import Fernet

from shared.twitch_scopes import BOT_SCOPES

_DATABASE_URL = os.getenv("NIIBOT_TEST_DATABASE_URL")


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_authorize_invite_executes_against_migrated_postgres() -> None:
    """Exercise asyncpg parameter inference instead of accepting SQL in a mock."""
    assert _DATABASE_URL is not None
    pool = await asyncpg.create_pool(_DATABASE_URL, min_size=1, max_size=2)
    suffix = uuid4().hex
    channel_id = f"test-bot-oauth-{suffix}"
    bot_user_id = f"test-bot-{suffix}"
    user_id = str(uuid4())
    service = BotAccountService(
        pool,
        token_encryption_key=Fernet.generate_key().decode(),
    )

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
                channel_id,
            )
            await conn.execute("INSERT INTO users (id) VALUES ($1::uuid)", user_id)

        invite = await service.create_invite(
            channel_id=channel_id,
            creator_user_id=user_id,
        )
        result = await service.authorize_invite(
            invite_id=invite.id,
            state_nonce=invite.state_nonce,
            platform_user_id=bot_user_id,
            access_token="integration-access-token",
            refresh_token="integration-refresh-token",
            scopes=set(BOT_SCOPES),
            login=f"bot_{suffix}",
            display_name="Integration Bot",
            avatar=None,
        )

        assert result.channel_id == channel_id
        assert result.platform_user_id == bot_user_id
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT invite.status, token.encryption_version, token.requires_reauth
                  FROM bot_oauth_invites invite
                  JOIN tokens token
                    ON token.user_id = invite.authorized_bot_user_id
                   AND token.token_type = 'bot'
                 WHERE invite.id = $1::uuid
                """,
                invite.id,
            )
        assert row is not None
        assert tuple(row) == ("authorized", 1, False)
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM tokens WHERE user_id = $1", bot_user_id)
            await conn.execute("DELETE FROM bot_accounts WHERE platform_user_id = $1", bot_user_id)
            await conn.execute("DELETE FROM channels WHERE channel_id = $1", channel_id)
            await conn.execute("DELETE FROM users WHERE id = $1::uuid", user_id)
        await pool.close()
