"""Unit tests for shared.repositories.channel — ChannelRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet

from shared.repositories.channel import (
    ChannelRepository,
    _channel_cache,
    _discord_user_cache,
    _enabled_channels_cache,
    _token_cache,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 1, 1, tzinfo=UTC)
_TOKEN_KEY = Fernet.generate_key().decode()

_TOKEN_ROW = {
    "user_id": "u1",
    "token": "tok",
    "refresh": "ref",
    "token_type": "broadcaster",
    "scopes": "channel:bot channel:read:redemptions",
    "created_at": _NOW,
    "updated_at": _NOW,
}

_CHANNEL_ROW: dict[str, Any] = {
    "channel_id": "u1",
    "channel_name": "streamer",
    "enabled": True,
    "default_cooldown": 5,
    "created_at": _NOW,
    "updated_at": _NOW,
}

_DISCORD_ROW = {
    "user_id": "d1",
    "username": "discordUser",
    "display_name": "Discord User",
    "avatar": None,
    "created_at": _NOW,
    "updated_at": _NOW,
}

_UNSET = object()


def _make_pool(
    *,
    fetch=_UNSET,
    fetchrow=_UNSET,
    execute=_UNSET,
) -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    if fetch is not _UNSET:
        conn.fetch.return_value = fetch
    if fetchrow is not _UNSET:
        conn.fetchrow.return_value = fetchrow
    if execute is not _UNSET:
        conn.execute.return_value = execute

    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=None)
    mock_tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=mock_tx)

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _clear_caches() -> None:
    for cache in (_token_cache, _channel_cache, _enabled_channels_cache, _discord_user_cache):
        cache.clear()
        cache._stale.clear()


# ---------------------------------------------------------------------------
# Token operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetToken:
    async def test_returns_none_when_not_found(self):
        _clear_caches()
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        repo = ChannelRepository(pool)

        result = await repo.get_token("u1")

        assert result is None

    async def test_returns_token_when_found(self):
        _clear_caches()
        pool, _ = _make_pool(fetchrow=_TOKEN_ROW)
        repo = ChannelRepository(pool)

        result = await repo.get_token("u1")

        assert result is not None
        assert result.user_id == "u1"
        assert result.token == "tok"
        assert result.scopes == "channel:bot channel:read:redemptions"

    async def test_result_is_cached(self):
        _clear_caches()
        pool, conn = _make_pool(fetchrow=_TOKEN_ROW)
        repo = ChannelRepository(pool)

        await repo.get_token("u1")
        await repo.get_token("u1")

        assert conn.fetchrow.call_count == 1

    async def test_decrypts_versioned_token_before_returning_model(self):
        from shared.twitch_token_crypto import encrypt_twitch_token

        _clear_caches()
        encrypted_token, version = encrypt_twitch_token("tok", _TOKEN_KEY)
        encrypted_refresh, _ = encrypt_twitch_token("ref", _TOKEN_KEY)
        row = {
            **_TOKEN_ROW,
            "token": encrypted_token,
            "refresh": encrypted_refresh,
            "encryption_version": version,
        }
        pool, _ = _make_pool(fetchrow=row)
        repo = ChannelRepository(pool, token_encryption_key=_TOKEN_KEY)

        result = await repo.get_token("u1")

        assert result is not None
        assert result.token == "tok"
        assert result.refresh == "ref"


@pytest.mark.asyncio
class TestUpsertTokenOnly:
    async def test_invalidates_token_cache(self):
        _token_cache.set("token:u1:broadcaster", _TOKEN_ROW)
        pool, _ = _make_pool(execute="INSERT 0 1")
        repo = ChannelRepository(pool)

        await repo.upsert_token_only("u1", "new_tok", "new_ref")

        from shared.cache import _MISSING

        assert _token_cache.get("token:u1:broadcaster") is _MISSING

    async def test_executes_upsert(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = ChannelRepository(pool)

        await repo.upsert_token_only("u1", "tok", "ref")

        conn.execute.assert_called_once()
        args = conn.execute.call_args[0]
        assert "u1" in args
        assert "tok" in args
        assert "ref" in args
        assert None in args  # scopes defaults to None

    async def test_executes_upsert_with_scopes(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = ChannelRepository(pool)

        await repo.upsert_token_only("u1", "tok", "ref", scopes="channel:bot bits:read")

        args = conn.execute.call_args[0]
        assert "channel:bot bits:read" in args

    async def test_clears_reauth_notified_at_on_success(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = ChannelRepository(pool)

        await repo.upsert_token_only("u1", "tok", "ref")

        sql = conn.execute.call_args[0][0]
        assert "reauth_notified_at = NULL" in sql
        assert "credential_revision = tokens.credential_revision + 1" in sql
        assert "next_validation_at" in sql
        assert "INTERVAL '55 minutes'" in sql

    async def test_encrypts_token_and_refresh_when_key_is_configured(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = ChannelRepository(pool, token_encryption_key=_TOKEN_KEY)

        await repo.upsert_token_only("u1", "tok", "ref")

        args = conn.execute.call_args[0]
        assert "tok" not in args[1:]
        assert "ref" not in args[1:]
        assert str(args[2]).startswith("v1:")
        assert str(args[3]).startswith("v1:")
        assert 1 in args
        assert "encryption_version" in args[0]


@pytest.mark.asyncio
class TestMarkRequiresReauth:
    async def test_sets_flag_and_notified_at(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = ChannelRepository(pool)

        await repo.mark_requires_reauth("u1")

        conn.execute.assert_called_once()
        sql = conn.execute.call_args[0][0]
        assert "requires_reauth = TRUE" in sql
        assert "reauth_notified_at = NOW()" in sql

    async def test_invalidates_token_cache(self):
        _token_cache.set("token:u1:broadcaster", _TOKEN_ROW)
        pool, _ = _make_pool(execute="UPDATE 1")
        repo = ChannelRepository(pool)

        await repo.mark_requires_reauth("u1")

        from shared.cache import _MISSING

        assert _token_cache.get("token:u1:broadcaster") is _MISSING

    async def test_revision_guard_rejects_a_stale_failure(self):
        pool, conn = _make_pool(execute="UPDATE 0")
        repo = ChannelRepository(pool)

        updated = await repo.mark_requires_reauth("u1", expected_revision=7)

        assert updated is False
        sql, user_id, token_type, revision = conn.execute.call_args.args
        assert "credential_revision = $3" in sql
        assert (user_id, token_type, revision) == ("u1", "broadcaster", 7)


@pytest.mark.asyncio
class TestRuntimeTokenValidation:
    async def test_uses_the_same_advisory_lock_key_as_api_reconciliation(self):
        pool, conn = _make_pool(execute="SELECT 1")
        repo = ChannelRepository(pool)

        async with repo.token_validation_lock("u1", "broadcaster") as connection:
            assert connection is conn

        lock_sql, lock_key = conn.execute.await_args_list[0].args
        unlock_sql, unlock_key = conn.execute.await_args_list[-1].args
        assert "pg_advisory_lock" in lock_sql
        assert "pg_advisory_unlock" in unlock_sql
        assert lock_key == unlock_key == "twitch-auth:broadcaster:u1"

    async def test_defers_api_scheduler_with_revision_compare_and_set(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = ChannelRepository(pool)

        updated = await repo.defer_token_validation("u1", "broadcaster", expected_revision=7)

        assert updated is True
        sql, user_id, token_type, revision = conn.execute.await_args.args
        assert "next_validation_at = NOW() + INTERVAL '5 minutes'" in sql
        assert "credential_revision = $3" in sql
        assert (user_id, token_type, revision) == ("u1", "broadcaster", 7)

    async def test_records_success_without_incrementing_credential_revision(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = ChannelRepository(pool)

        updated = await repo.record_token_validation("u1", "broadcaster", expected_revision=7)

        assert updated is True
        sql = conn.execute.await_args.args[0]
        assert "last_checked_at = NOW()" in sql
        assert "last_validated_at = NOW()" in sql
        assert "next_validation_at = NOW() + INTERVAL '55 minutes'" in sql
        assert "credential_revision = credential_revision + 1" not in sql

    async def test_refresh_rotation_is_compare_and_set_by_runtime_revision(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = ChannelRepository(pool, token_encryption_key=_TOKEN_KEY)

        updated = await repo.rotate_token_if_revision(
            "u1",
            "new-token",
            "new-refresh",
            scopes="channel:bot",
            token_type="broadcaster",
            expected_revision=7,
        )

        assert updated is True
        sql, user_id, encrypted_token, encrypted_refresh, scopes, token_type, version, revision = (
            conn.execute.await_args.args
        )
        assert "credential_revision = credential_revision + 1" in sql
        assert "credential_revision = $7" in sql
        assert (user_id, scopes, token_type, version, revision) == (
            "u1",
            "channel:bot",
            "broadcaster",
            1,
            7,
        )
        assert encrypted_token != "new-token"
        assert encrypted_refresh != "new-refresh"


@pytest.mark.asyncio
class TestListTokens:
    async def test_returns_empty_list(self):
        pool, _ = _make_pool(fetch=[])
        repo = ChannelRepository(pool)

        result = await repo.list_tokens()

        assert result == []

    async def test_returns_token_list(self):
        pool, _ = _make_pool(fetch=[_TOKEN_ROW])
        repo = ChannelRepository(pool)

        result = await repo.list_tokens()

        assert len(result) == 1
        assert result[0].user_id == "u1"
        assert result[0].scopes == "channel:bot channel:read:redemptions"

    async def test_can_isolate_a_version_one_row_missing_its_envelope(self, caplog):
        malformed = {
            **_TOKEN_ROW,
            "token": "access-secret",
            "refresh": "refresh-secret",
            "encryption_version": 1,
        }
        pool, _ = _make_pool(fetch=[malformed, _TOKEN_ROW])
        repo = ChannelRepository(pool, token_encryption_key=_TOKEN_KEY)

        result = await repo.list_tokens(skip_invalid_envelopes=True)

        assert len(result) == 1
        assert result[0].user_id == "u1"
        assert "Skipped stored Twitch credential with a missing encryption envelope" in caplog.text
        assert "access-secret" not in caplog.text
        assert "refresh-secret" not in caplog.text

    async def test_missing_envelope_still_fails_closed_by_default(self):
        malformed = {
            **_TOKEN_ROW,
            "token": "access-secret",
            "refresh": "refresh-secret",
            "encryption_version": 1,
        }
        pool, _ = _make_pool(fetch=[malformed])
        repo = ChannelRepository(pool, token_encryption_key=_TOKEN_KEY)

        with pytest.raises(ValueError, match="envelope"):
            await repo.list_tokens()


@pytest.mark.asyncio
class TestUpsertToken:
    async def test_invalidates_token_channel_and_enabled_caches(self):
        _token_cache.set("token:u1:broadcaster", _TOKEN_ROW)
        _channel_cache.set("channel:u1", _CHANNEL_ROW)
        _enabled_channels_cache.set("enabled_channels", [_CHANNEL_ROW])
        pool, _ = _make_pool(execute="INSERT 0 1")
        repo = ChannelRepository(pool)

        await repo.upsert_token("u1", "tok", "ref", channel_name="streamer")

        from shared.cache import _MISSING

        assert _token_cache.get("token:u1:broadcaster") is _MISSING
        assert _channel_cache.get("channel:u1") is _MISSING
        assert _enabled_channels_cache.get("enabled_channels") is _MISSING

    async def test_uses_transaction(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = ChannelRepository(pool)

        await repo.upsert_token("u1", "tok", "ref")

        conn.transaction.assert_called_once()

    async def test_executes_upsert_with_scopes(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = ChannelRepository(pool)

        await repo.upsert_token("u1", "tok", "ref", scopes="channel:bot bits:read")

        first_execute_args = conn.execute.call_args_list[0][0]
        assert "channel:bot bits:read" in first_execute_args
        assert "credential_revision = tokens.credential_revision + 1" in first_execute_args[0]

    async def test_channel_insert_does_not_force_enabled(self):
        # Signup must not enable a channel — admission does (migration 084). The
        # channels upsert must neither insert enabled=TRUE nor touch it on
        # conflict, so a re-auth never re-enables a suspended/pending channel.
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = ChannelRepository(pool)

        await repo.upsert_token("u1", "tok", "ref", channel_name="streamer")

        channels_sql = conn.execute.call_args_list[1][0][0]
        assert "INTO channels" in channels_sql
        assert "enabled" not in channels_sql


# ---------------------------------------------------------------------------
# Channel operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetChannel:
    async def test_returns_none_when_not_found(self):
        _clear_caches()
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        repo = ChannelRepository(pool)

        result = await repo.get_channel("u1")

        assert result is None

    async def test_returns_channel_when_found(self):
        _clear_caches()
        pool, _ = _make_pool(fetchrow=_CHANNEL_ROW)
        repo = ChannelRepository(pool)

        result = await repo.get_channel("u1")

        assert result is not None
        assert result.channel_id == "u1"
        assert result.channel_name == "streamer"
        assert result.enabled is True

    async def test_result_is_cached(self):
        _clear_caches()
        pool, conn = _make_pool(fetchrow=_CHANNEL_ROW)
        repo = ChannelRepository(pool)

        await repo.get_channel("u1")
        await repo.get_channel("u1")

        assert conn.fetchrow.call_count == 1


@pytest.mark.asyncio
class TestListEnabledChannels:
    async def test_returns_empty_list(self):
        _clear_caches()
        pool, _ = _make_pool(fetch=[])
        repo = ChannelRepository(pool)

        result = await repo.list_enabled_channels()

        assert result == []

    async def test_returns_channel_list(self):
        _clear_caches()
        pool, _ = _make_pool(fetch=[_CHANNEL_ROW])
        repo = ChannelRepository(pool)

        result = await repo.list_enabled_channels()

        assert len(result) == 1
        assert result[0].channel_id == "u1"

    async def test_result_is_cached(self):
        _clear_caches()
        pool, conn = _make_pool(fetch=[_CHANNEL_ROW])
        repo = ChannelRepository(pool)

        await repo.list_enabled_channels()
        await repo.list_enabled_channels()

        assert conn.fetch.call_count == 1


class TestWarmChannelCache:
    def test_returns_count_and_populates_cache(self):
        _clear_caches()
        from shared.models.channel import Channel

        ch = Channel(**_CHANNEL_ROW)
        pool = MagicMock()
        repo = ChannelRepository(pool)

        count = repo.warm_channel_cache([ch])

        assert count == 1
        assert _channel_cache.get("channel:u1") is ch


@pytest.mark.asyncio
class TestUpsertChannel:
    async def test_invalidates_channel_and_enabled_caches(self):
        _channel_cache.set("channel:u1", _CHANNEL_ROW)
        _enabled_channels_cache.set("enabled_channels", [_CHANNEL_ROW])
        pool, _ = _make_pool(execute="INSERT 0 1")
        repo = ChannelRepository(pool)

        await repo.upsert_channel("u1", "streamer")

        from shared.cache import _MISSING

        assert _channel_cache.get("channel:u1") is _MISSING
        assert _enabled_channels_cache.get("enabled_channels") is _MISSING

    async def test_conflict_does_not_touch_enabled(self):
        # The bot re-asserts channel rows (e.g. on new_token); it must not flip
        # enabled, which is admission-owned. The ON CONFLICT clause must not
        # assign enabled.
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = ChannelRepository(pool)

        await repo.upsert_channel("u1", "streamer")

        sql = conn.execute.call_args_list[0][0][0]
        conflict_clause = sql.split("ON CONFLICT", 1)[1]
        assert "enabled" not in conflict_clause


@pytest.mark.asyncio
class TestListActiveOwnerChannelIds:
    async def test_returns_channel_ids_with_active_owner(self):
        pool, conn = _make_pool(fetch=[{"channel_id": "c1"}, {"channel_id": "c2"}])
        repo = ChannelRepository(pool)

        result = await repo.list_active_owner_channel_ids()

        assert result == {"c1", "c2"}
        sql = conn.fetch.call_args[0][0]
        assert "memberships" in sql
        assert "'active'" in sql

    async def test_returns_empty_set_when_none(self):
        pool, _ = _make_pool(fetch=[])
        repo = ChannelRepository(pool)

        assert await repo.list_active_owner_channel_ids() == set()


@pytest.mark.asyncio
class TestListMonitoredOwnerChannelStatus:
    async def test_returns_status_and_owner_by_channel_id(self):
        pool, conn = _make_pool(
            fetch=[
                {"channel_id": "c1", "status": "active", "owner_user_id": "u1", "reason": None},
                {
                    "channel_id": "c2",
                    "status": "pending",
                    "owner_user_id": "u2",
                    "reason": "first_signup",
                },
                {
                    "channel_id": "c3",
                    "status": "suspended",
                    "owner_user_id": "u3",
                    "reason": "abuse",
                },
            ]
        )
        repo = ChannelRepository(pool)

        result = await repo.list_monitored_owner_channel_status()

        assert result == {
            "c1": ("active", "u1", None),
            "c2": ("pending", "u2", "first_signup"),
            "c3": ("suspended", "u3", "abuse"),
        }
        sql = conn.fetch.call_args[0][0]
        assert "memberships" in sql
        assert "'active', 'pending', 'suspended'" in sql

    async def test_returns_empty_dict_when_none(self):
        pool, _ = _make_pool(fetch=[])
        repo = ChannelRepository(pool)

        assert await repo.list_monitored_owner_channel_status() == {}


@pytest.mark.asyncio
class TestDisableChannelByName:
    async def test_clears_enabled_channels_cache(self):
        _enabled_channels_cache.set("enabled_channels", [_CHANNEL_ROW])
        pool, _ = _make_pool(execute="UPDATE 1")
        repo = ChannelRepository(pool)

        await repo.disable_channel_by_name("streamer")

        from shared.cache import _MISSING

        assert _enabled_channels_cache.get("enabled_channels") is _MISSING


@pytest.mark.asyncio
class TestUpdateChannelEnabled:
    async def test_invalidates_channel_and_enabled_caches(self):
        _channel_cache.set("channel:u1", _CHANNEL_ROW)
        _enabled_channels_cache.set("enabled_channels", [_CHANNEL_ROW])
        pool, _ = _make_pool(execute="UPDATE 1")
        repo = ChannelRepository(pool)

        await repo.update_channel_enabled("u1", False)

        from shared.cache import _MISSING

        assert _channel_cache.get("channel:u1") is _MISSING
        assert _enabled_channels_cache.get("enabled_channels") is _MISSING


@pytest.mark.asyncio
class TestUpdateChannelDefaults:
    async def test_returns_none_when_channel_not_found(self):
        _clear_caches()
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        repo = ChannelRepository(pool)

        result = await repo.update_channel_defaults("u1", default_cooldown=10)

        assert result is None

    async def test_returns_updated_channel(self):
        _clear_caches()
        pool, _ = _make_pool(fetchrow=_CHANNEL_ROW)
        repo = ChannelRepository(pool)

        result = await repo.update_channel_defaults("u1", default_cooldown=10)

        assert result is not None
        assert result.channel_id == "u1"


# ---------------------------------------------------------------------------
# Discord user operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetDiscordUser:
    async def test_returns_none_when_not_found(self):
        _clear_caches()
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        repo = ChannelRepository(pool)

        result = await repo.get_discord_user("d1")

        assert result is None

    async def test_returns_user_when_found(self):
        _clear_caches()
        pool, _ = _make_pool(fetchrow=_DISCORD_ROW)
        repo = ChannelRepository(pool)

        result = await repo.get_discord_user("d1")

        assert result is not None
        assert result.user_id == "d1"
        assert result.username == "discordUser"

    async def test_result_is_cached(self):
        _clear_caches()
        pool, conn = _make_pool(fetchrow=_DISCORD_ROW)
        repo = ChannelRepository(pool)

        await repo.get_discord_user("d1")
        await repo.get_discord_user("d1")

        assert conn.fetchrow.call_count == 1


@pytest.mark.asyncio
class TestUpsertDiscordUser:
    async def test_invalidates_discord_user_cache(self):
        _discord_user_cache.set("discord_user:d1", _DISCORD_ROW)
        pool, _ = _make_pool(execute="INSERT 0 1")
        repo = ChannelRepository(pool)

        await repo.upsert_discord_user("d1", "discordUser")

        from shared.cache import _MISSING

        assert _discord_user_cache.get("discord_user:d1") is _MISSING
