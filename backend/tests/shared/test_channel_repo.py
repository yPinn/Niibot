"""Unit tests for shared.repositories.channel — ChannelRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

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

_TOKEN_ROW = {
    "user_id": "u1",
    "token": "tok",
    "refresh": "ref",
    "created_at": _NOW,
    "updated_at": _NOW,
}

_CHANNEL_ROW = {
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

    async def test_result_is_cached(self):
        _clear_caches()
        pool, conn = _make_pool(fetchrow=_TOKEN_ROW)
        repo = ChannelRepository(pool)

        await repo.get_token("u1")
        await repo.get_token("u1")

        assert conn.fetchrow.call_count == 1


@pytest.mark.asyncio
class TestUpsertTokenOnly:
    async def test_invalidates_token_cache(self):
        _token_cache.set("token:u1", _TOKEN_ROW)
        pool, _ = _make_pool(execute="INSERT 0 1")
        repo = ChannelRepository(pool)

        await repo.upsert_token_only("u1", "new_tok", "new_ref")

        from shared.cache import _MISSING

        assert _token_cache.get("token:u1") is _MISSING

    async def test_executes_upsert(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = ChannelRepository(pool)

        await repo.upsert_token_only("u1", "tok", "ref")

        conn.execute.assert_called_once()
        args = conn.execute.call_args[0]
        assert "u1" in args
        assert "tok" in args
        assert "ref" in args


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


@pytest.mark.asyncio
class TestUpsertToken:
    async def test_invalidates_token_channel_and_enabled_caches(self):
        _token_cache.set("token:u1", _TOKEN_ROW)
        _channel_cache.set("channel:u1", _CHANNEL_ROW)
        _enabled_channels_cache.set("enabled_channels", [_CHANNEL_ROW])
        pool, _ = _make_pool(execute="INSERT 0 1")
        repo = ChannelRepository(pool)

        await repo.upsert_token("u1", "tok", "ref", channel_name="streamer")

        from shared.cache import _MISSING

        assert _token_cache.get("token:u1") is _MISSING
        assert _channel_cache.get("channel:u1") is _MISSING
        assert _enabled_channels_cache.get("enabled_channels") is _MISSING

    async def test_uses_transaction(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = ChannelRepository(pool)

        await repo.upsert_token("u1", "tok", "ref")

        conn.transaction.assert_called_once()


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
