"""Unit tests for shared.repositories.command_config."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.builtin_commands import BUILTIN_DEFS
from shared.repositories.command_config import (
    CommandConfigRepository,
    RedemptionConfigRepository,
    _cmd_cache,
    _cmd_list_cache,
    _redemption_cache,
    _seeded_redemptions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 1, 1, tzinfo=UTC)

# A row that represents a DB-stored builtin override (command_name must be in BUILTIN_DEFS)
_BUILTIN_OVERRIDE_ROW: dict[str, Any] = {
    "id": 1,
    "channel_id": "ch1",
    "command_name": "hi",  # canonical builtin name
    "command_type": "builtin",
    "enabled": False,  # user disabled it
    "custom_response": None,
    "cooldown": 10,
    "min_role": "everyone",
    "aliases": "hello,hey",
    "usage_count": 5,
    "created_at": _NOW,
    "updated_at": _NOW,
}

# A legacy row used by get_config / upsert tests (non-builtin canonical name)
_CMD_ROW: dict[str, Any] = {
    "id": 1,
    "channel_id": "ch1",
    "command_name": "hello",
    "command_type": "builtin",
    "enabled": True,
    "custom_response": None,
    "cooldown": None,
    "min_role": "everyone",
    "aliases": None,
    "usage_count": 0,
    "created_at": _NOW,
    "updated_at": _NOW,
}

_CUSTOM_ROW: dict[str, Any] = {
    "id": 2,
    "channel_id": "ch1",
    "command_name": "mycommand",
    "command_type": "custom",
    "enabled": True,
    "custom_response": "Hello!",
    "cooldown": 5,
    "min_role": "everyone",
    "aliases": None,
    "usage_count": 0,
    "created_at": _NOW,
    "updated_at": _NOW,
}

_REDEMPTION_ROW = {
    "id": 1,
    "channel_id": "ch1",
    "action_type": "vip",
    "reward_name": "vip",
    "enabled": True,
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

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _clear_caches() -> None:
    for cache in (_cmd_cache, _cmd_list_cache, _redemption_cache):
        cache.clear()
        cache._stale.clear()
    _seeded_redemptions.clear()


# ---------------------------------------------------------------------------
# CommandConfigRepository
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetConfig:
    async def test_returns_none_when_not_found_and_not_builtin(self):
        """Non-builtin name with no DB row returns None."""
        _clear_caches()
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        repo = CommandConfigRepository(pool)

        result = await repo.get_config("ch1", "nonexistent")

        assert result is None

    async def test_returns_virtual_for_known_builtin_with_no_db_row(self):
        """Known builtin with no DB row returns virtual default (id=None, enabled=True)."""
        _clear_caches()
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        repo = CommandConfigRepository(pool)

        result = await repo.get_config("ch1", "hi")

        assert result is not None
        assert result.command_name == "hi"
        assert result.id is None
        assert result.enabled is True
        assert result.command_type == "builtin"

    async def test_returns_db_row_when_present(self):
        """DB row (with overrides) takes precedence over virtual default."""
        _clear_caches()
        pool, _ = _make_pool(fetchrow=_BUILTIN_OVERRIDE_ROW)
        repo = CommandConfigRepository(pool)

        result = await repo.get_config("ch1", "hi")

        assert result is not None
        assert result.command_name == "hi"
        assert result.id == 1
        assert result.enabled is False  # DB override respected

    async def test_result_is_cached(self):
        _clear_caches()
        pool, conn = _make_pool(fetchrow=_CMD_ROW)
        repo = CommandConfigRepository(pool)

        await repo.get_config("ch1", "hello")
        await repo.get_config("ch1", "hello")

        assert conn.fetchrow.call_count == 1


@pytest.mark.asyncio
class TestFindByNameOrAlias:
    async def test_returns_config_by_exact_name(self):
        _clear_caches()
        pool, _ = _make_pool(fetchrow=_CMD_ROW)
        repo = CommandConfigRepository(pool)

        result = await repo.find_by_name_or_alias("ch1", "hello")

        assert result is not None
        assert result.command_name == "hello"

    async def test_falls_through_to_alias_when_name_not_found_in_db(self):
        """Name not in DB and not a builtin name → check DB alias search."""
        _clear_caches()
        pool, conn = _make_pool()
        # get_config: fetchrow → None (not in DB, not in BUILTIN_MAP → None)
        # _find_by_alias: fetchrow → _CMD_ROW (found as alias)
        conn.fetchrow.side_effect = [None, _CMD_ROW]
        repo = CommandConfigRepository(pool)

        result = await repo.find_by_name_or_alias("ch1", "xyz_alias")

        assert result is not None
        assert conn.fetchrow.call_count == 2

    async def test_returns_virtual_for_builtin_alias(self):
        """Alias of a known builtin returns virtual default when no DB row exists."""
        _clear_caches()
        pool, conn = _make_pool()
        # DB returns None for both exact name and alias lookup
        conn.fetchrow.return_value = None
        repo = CommandConfigRepository(pool)

        # "hello" is a registered alias for builtin "hi"
        result = await repo.find_by_name_or_alias("ch1", "hello")

        assert result is not None
        assert result.command_name == "hi"
        assert result.id is None  # virtual

    async def test_returns_none_when_neither_found(self):
        _clear_caches()
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        repo = CommandConfigRepository(pool)

        result = await repo.find_by_name_or_alias("ch1", "unknown_xyz")

        assert result is None


@pytest.mark.asyncio
class TestListConfigs:
    async def test_returns_all_builtins_when_db_is_empty(self):
        """Empty DB still returns all builtin virtual defaults."""
        _clear_caches()
        pool, _ = _make_pool(fetch=[])
        repo = CommandConfigRepository(pool)

        result = await repo.list_configs("ch1")

        assert len(result) == len(BUILTIN_DEFS)
        assert all(r.id is None for r in result)  # all virtual
        assert all(r.command_type == "builtin" for r in result)

    async def test_db_override_replaces_virtual_for_matching_builtin(self):
        """DB row for a known builtin replaces the virtual default."""
        _clear_caches()
        pool, _ = _make_pool(fetch=[_BUILTIN_OVERRIDE_ROW])
        repo = CommandConfigRepository(pool)

        result = await repo.list_configs("ch1")

        hi = next(r for r in result if r.command_name == "hi")
        assert hi.id == 1  # came from DB
        assert hi.enabled is False  # override respected
        assert len(result) == len(BUILTIN_DEFS)  # still the same total count

    async def test_custom_commands_appended_after_builtins(self):
        """Custom commands from DB appear after all builtins."""
        _clear_caches()
        pool, _ = _make_pool(fetch=[_CUSTOM_ROW])
        repo = CommandConfigRepository(pool)

        result = await repo.list_configs("ch1")

        builtins = [r for r in result if r.command_type == "builtin"]
        customs = [r for r in result if r.command_type == "custom"]
        assert len(builtins) == len(BUILTIN_DEFS)
        assert len(customs) == 1
        assert customs[0].command_name == "mycommand"

    async def test_result_is_cached(self):
        _clear_caches()
        pool, conn = _make_pool(fetch=[])
        repo = CommandConfigRepository(pool)

        await repo.list_configs("ch1")
        await repo.list_configs("ch1")

        assert conn.fetch.call_count == 1


@pytest.mark.asyncio
class TestUpsertConfig:
    async def test_returns_inserted_config(self):
        pool, _ = _make_pool(fetchrow=_CMD_ROW)
        repo = CommandConfigRepository(pool)

        result = await repo.upsert_config("ch1", "hello")

        assert result.command_name == "hello"

    async def test_invalidates_cmd_and_list_caches(self):
        _cmd_cache.set("cmd_config:ch1:hello", _CMD_ROW)
        _cmd_list_cache.set("cmd_list:ch1", [_CMD_ROW])
        pool, _ = _make_pool(fetchrow=_CMD_ROW)
        repo = CommandConfigRepository(pool)

        await repo.upsert_config("ch1", "hello")

        from shared.cache import _MISSING

        assert _cmd_cache.get("cmd_config:ch1:hello") is _MISSING
        assert _cmd_list_cache.get("cmd_list:ch1") is _MISSING

    async def test_invalidates_alias_caches_when_aliases_provided(self):
        _cmd_cache.set("cmd_alias:ch1:hi", _CMD_ROW)
        pool, _ = _make_pool(fetchrow=_CMD_ROW)
        repo = CommandConfigRepository(pool)

        await repo.upsert_config("ch1", "hello", aliases="hi,hey")

        from shared.cache import _MISSING

        assert _cmd_cache.get("cmd_alias:ch1:hi") is _MISSING
        assert _cmd_cache.get("cmd_alias:ch1:hey") is _MISSING

    async def test_invalidates_builtin_default_aliases_on_builtin_update(self):
        """Toggling a builtin also invalidates its default alias cache entries."""
        _cmd_cache.set("cmd_alias:ch1:hello", "cached_value")
        _cmd_cache.set("cmd_alias:ch1:hey", "cached_value")
        pool, _ = _make_pool(fetchrow=_BUILTIN_OVERRIDE_ROW)
        repo = CommandConfigRepository(pool)

        await repo.upsert_config("ch1", "hi", enabled=False)

        from shared.cache import _MISSING

        # "hello" and "hey" are default aliases for "hi" → should be invalidated
        assert _cmd_cache.get("cmd_alias:ch1:hello") is _MISSING
        assert _cmd_cache.get("cmd_alias:ch1:hey") is _MISSING


@pytest.mark.asyncio
class TestDeleteConfig:
    async def test_returns_true_when_deleted(self):
        _clear_caches()
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None  # get_config returns None
        conn.execute.return_value = "DELETE 1"
        repo = CommandConfigRepository(pool)

        result = await repo.delete_config("ch1", "hello")

        assert result is True

    async def test_returns_false_when_not_found(self):
        _clear_caches()
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        conn.execute.return_value = "DELETE 0"
        repo = CommandConfigRepository(pool)

        result = await repo.delete_config("ch1", "noexist")

        assert result is False

    async def test_invalidates_alias_caches_when_config_has_aliases(self):
        _clear_caches()
        from shared.models.command_config import CommandConfig

        cfg_with_aliases = CommandConfig(**{**_CMD_ROW, "aliases": "hi,hey"})
        _cmd_cache.set("cmd_config:ch1:hello", cfg_with_aliases)
        _cmd_cache.set("cmd_alias:ch1:hi", cfg_with_aliases)

        pool, conn = _make_pool()
        conn.fetchrow.return_value = None  # fresh fetch returns None (invalidated)
        conn.execute.return_value = "DELETE 1"
        repo = CommandConfigRepository(pool)

        await repo.delete_config("ch1", "hello")

        from shared.cache import _MISSING

        assert _cmd_list_cache.get("cmd_list:ch1") is _MISSING


@pytest.mark.asyncio
class TestWarmCache:
    async def test_returns_count_including_virtual_builtins(self):
        """warm_cache returns len(BUILTIN_DEFS) even with empty DB."""
        _clear_caches()
        pool, _ = _make_pool(fetch=[])
        repo = CommandConfigRepository(pool)

        count = await repo.warm_cache("ch1")

        assert count == len(BUILTIN_DEFS)

    async def test_populates_name_keys_for_virtual_builtins(self):
        _clear_caches()
        pool, _ = _make_pool(fetch=[])
        repo = CommandConfigRepository(pool)

        await repo.warm_cache("ch1")

        # "hi" is in BUILTIN_DEFS → should be cached as virtual
        assert _cmd_cache.get("cmd_config:ch1:hi") is not None

    async def test_populates_alias_keys(self):
        _clear_caches()
        pool, _ = _make_pool(fetch=[_BUILTIN_OVERRIDE_ROW])
        repo = CommandConfigRepository(pool)

        await repo.warm_cache("ch1")

        # "hi" override row has aliases "hello,hey"
        assert _cmd_cache.get("cmd_alias:ch1:hello") is not None
        assert _cmd_cache.get("cmd_alias:ch1:hey") is not None


# ---------------------------------------------------------------------------
# RedemptionConfigRepository
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRedemptionListConfigs:
    async def test_returns_empty_list(self):
        pool, _ = _make_pool(fetch=[])
        repo = RedemptionConfigRepository(pool)

        result = await repo.list_configs("ch1")

        assert result == []

    async def test_returns_redemption_list(self):
        pool, _ = _make_pool(fetch=[_REDEMPTION_ROW])
        repo = RedemptionConfigRepository(pool)

        result = await repo.list_configs("ch1")

        assert len(result) == 1
        assert result[0].action_type == "vip"


@pytest.mark.asyncio
class TestFindByRewardName:
    async def test_returns_config_when_reward_name_is_substring(self):
        _clear_caches()
        # reward_name "vip" should match title "VIP Crown"
        pool, _ = _make_pool(fetch=[_REDEMPTION_ROW])
        repo = RedemptionConfigRepository(pool)

        result = await repo.find_by_reward_name("ch1", "VIP Crown")

        assert result is not None
        assert result.action_type == "vip"

    async def test_returns_none_when_no_match(self):
        _clear_caches()
        pool, _ = _make_pool(fetch=[_REDEMPTION_ROW])
        repo = RedemptionConfigRepository(pool)

        result = await repo.find_by_reward_name("ch1", "unrelated reward")

        assert result is None

    async def test_result_is_cached(self):
        _clear_caches()
        pool, conn = _make_pool(fetch=[_REDEMPTION_ROW])
        repo = RedemptionConfigRepository(pool)

        await repo.find_by_reward_name("ch1", "VIP Crown")
        await repo.find_by_reward_name("ch1", "VIP Crown")

        assert conn.fetch.call_count == 1


@pytest.mark.asyncio
class TestRedemptionUpsertConfig:
    async def test_returns_inserted_config(self):
        pool, _ = _make_pool(fetchrow=_REDEMPTION_ROW)
        repo = RedemptionConfigRepository(pool)

        result = await repo.upsert_config("ch1", "vip", "vip")

        assert result.action_type == "vip"

    async def test_clears_redemption_cache(self):
        _redemption_cache.set("redemption:ch1:vip", _REDEMPTION_ROW)
        pool, _ = _make_pool(fetchrow=_REDEMPTION_ROW)
        repo = RedemptionConfigRepository(pool)

        await repo.upsert_config("ch1", "vip", "vip")

        from shared.cache import _MISSING

        assert _redemption_cache.get("redemption:ch1:vip") is _MISSING


@pytest.mark.asyncio
class TestRedemptionEnsureDefaults:
    async def test_seeds_defaults_on_first_call(self):
        _clear_caches()
        pool, conn = _make_pool(fetch=[_REDEMPTION_ROW], execute="INSERT 0 1")
        repo = RedemptionConfigRepository(pool)

        await repo.ensure_defaults("ch1")

        assert conn.execute.called
        assert "ch1" in _seeded_redemptions

    async def test_skips_niibot_auth_for_non_owner(self):
        _clear_caches()
        pool, conn = _make_pool(fetch=[_REDEMPTION_ROW], execute="INSERT 0 1")
        repo = RedemptionConfigRepository(pool)

        await repo.ensure_defaults("ch1", owner_id="owner999")

        # niibot_auth should not be inserted
        inserted_types = [call[0][2] for call in conn.execute.call_args_list]
        assert "niibot_auth" not in inserted_types

    async def test_seeds_niibot_auth_for_owner(self):
        _clear_caches()
        pool, conn = _make_pool(fetch=[_REDEMPTION_ROW], execute="INSERT 0 1")
        repo = RedemptionConfigRepository(pool)

        await repo.ensure_defaults("owner1", owner_id="owner1")

        inserted_types = [call[0][2] for call in conn.execute.call_args_list]
        assert "niibot_auth" in inserted_types

    async def test_skips_seed_on_second_call(self):
        _clear_caches()
        pool, conn = _make_pool(fetch=[_REDEMPTION_ROW], execute="INSERT 0 1")
        repo = RedemptionConfigRepository(pool)

        await repo.ensure_defaults("ch1")
        first_count = conn.execute.call_count

        await repo.ensure_defaults("ch1")

        assert conn.execute.call_count == first_count
