"""PostgreSQL integration regression for bot OAuth invitation consumption."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest
from api.services.bot_account_service import BotAccountService
from cryptography.fernet import Fernet

from shared.repositories.bot_selection import BotSelectionRepository
from shared.twitch_scopes import BOT_SCOPES

_DATABASE_URL = os.getenv("NIIBOT_TEST_DATABASE_URL")


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_same_bot_credential_is_canonical_across_tenant_grants() -> None:
    """A and C get separate grants while B keeps one versioned token row."""
    assert _DATABASE_URL is not None
    pool = await asyncpg.create_pool(_DATABASE_URL, min_size=1, max_size=2)
    suffix = uuid4().hex
    channel_ids = [f"test-grant-a-{suffix}", f"test-grant-c-{suffix}"]
    owner_ids = [str(uuid4()), str(uuid4())]
    bot_user_id = f"test-shared-bot-{suffix}"
    service = BotAccountService(pool, token_encryption_key=Fernet.generate_key().decode())

    try:
        async with pool.acquire() as conn:
            for channel_id, owner_id in zip(channel_ids, owner_ids, strict=True):
                await conn.execute(
                    "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
                    channel_id,
                )
                await conn.execute("INSERT INTO users (id) VALUES ($1::uuid)", owner_id)

        for index, (channel_id, owner_id) in enumerate(
            zip(channel_ids, owner_ids, strict=True),
            start=1,
        ):
            invite = await service.create_invite(
                channel_id=channel_id,
                creator_user_id=owner_id,
            )
            await service.authorize_invite(
                invite_id=invite.id,
                state_nonce=invite.state_nonce,
                platform_user_id=bot_user_id,
                access_token=f"access-{index}",
                refresh_token=f"refresh-{index}",
                scopes=set(BOT_SCOPES),
                login=f"shared_bot_{suffix}",
                display_name="Shared Bot",
                avatar=None,
            )

        async with pool.acquire() as conn:
            token_rows = await conn.fetch(
                """
                SELECT credential_revision
                  FROM tokens
                 WHERE user_id = $1 AND token_type = 'bot'
                """,
                bot_user_id,
            )
            mappings = await conn.fetchval(
                """
                SELECT COUNT(*)
                  FROM channel_bot_accounts
                 WHERE bot_user_id = $1
                   AND channel_id = ANY($2::text[])
                """,
                bot_user_id,
                channel_ids,
            )

        assert len(token_rows) == 1
        assert token_rows[0]["credential_revision"] == 2
        assert mappings == 2
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM tokens WHERE user_id = $1", bot_user_id)
            await conn.execute("DELETE FROM bot_accounts WHERE platform_user_id = $1", bot_user_id)
            await conn.execute(
                "DELETE FROM channels WHERE channel_id = ANY($1::text[])", channel_ids
            )
            await conn.execute("DELETE FROM users WHERE id = ANY($1::uuid[])", owner_ids)
        await pool.close()


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


@pytest.mark.skipif(not _DATABASE_URL, reason="NIIBOT_TEST_DATABASE_URL is not configured")
async def test_bot_selection_versions_concurrent_requests_and_guards_runtime_ack() -> None:
    assert _DATABASE_URL is not None
    pool = await asyncpg.create_pool(_DATABASE_URL, min_size=1, max_size=4)
    suffix = uuid4().hex
    channel_id = f"test-bot-selection-{suffix}"
    bot_ids = [f"test-selection-bot-a-{suffix}", f"test-selection-bot-b-{suffix}"]
    user_id = str(uuid4())
    repository = BotSelectionRepository(pool)

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO channels (channel_id, channel_name) VALUES ($1, $1)",
                channel_id,
            )
            await conn.execute("INSERT INTO users (id) VALUES ($1::uuid)", user_id)
            for bot_id in bot_ids:
                await conn.execute(
                    """
                    INSERT INTO bot_accounts (platform_user_id, login, display_name)
                    VALUES ($1, $1, $1)
                    """,
                    bot_id,
                )
                await conn.execute(
                    """
                    INSERT INTO channel_bot_accounts
                        (channel_id, bot_user_id, linked_by_user_id)
                    VALUES ($1, $2, $3::uuid)
                    """,
                    channel_id,
                    bot_id,
                    user_id,
                )
                await conn.execute(
                    """
                    INSERT INTO tokens (user_id, token, refresh, token_type, scopes)
                    VALUES ($1, 'integration-token', 'integration-refresh', 'bot', $2)
                    """,
                    bot_id,
                    " ".join(BOT_SCOPES),
                )

        first, second = await asyncio.gather(
            repository.request(
                channel_id=channel_id,
                bot_user_id=bot_ids[0],
                actor_user_id=user_id,
                system_bot_id="unused-system-bot",
                required_scopes=set(BOT_SCOPES),
            ),
            repository.request(
                channel_id=channel_id,
                bot_user_id=bot_ids[1],
                actor_user_id=user_id,
                system_bot_id="unused-system-bot",
                required_scopes=set(BOT_SCOPES),
            ),
        )
        assert first is not None and second is not None
        assert {first.selection_version, second.selection_version} == {1, 2}

        stale = first if first.selection_version == 1 else second
        current = first if first.selection_version == 2 else second
        assert not await repository.mark_active(
            channel_id=channel_id,
            selection_version=stale.selection_version,
            bot_user_id=stale.desired_bot_user_id,
        )
        assert await repository.mark_active(
            channel_id=channel_id,
            selection_version=current.selection_version,
            bot_user_id=current.desired_bot_user_id,
        )
        final = await repository.get(channel_id)
        assert final.status == "active"
        assert final.selection_version == final.acked_version == 2
        assert final.active_bot_user_id == current.desired_bot_user_id
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM tokens WHERE user_id = ANY($1::text[])", bot_ids)
            await conn.execute("DELETE FROM channel_bot_settings WHERE channel_id = $1", channel_id)
            await conn.execute(
                "DELETE FROM bot_accounts WHERE platform_user_id = ANY($1::text[])", bot_ids
            )
            await conn.execute("DELETE FROM channels WHERE channel_id = $1", channel_id)
            await conn.execute("DELETE FROM users WHERE id = $1::uuid", user_id)
        await pool.close()
