"""Unit tests for shared.repositories.module_config — ModuleConfigRepository.

Regression cases for the JSONB codec interaction: the production pool registers
a JSONB codec (shared.database._register_json_codecs) so asyncpg returns Python
list/dict for JSONB columns. The repository must not call json.loads on an
already-decoded value.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.repositories.module_config import (
    _CACHE_KEY,
    ModuleConfigRepository,
    _module_config_cache,
)


def _make_pool(*, fetchrow=None, execute=None) -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    conn.fetchrow.return_value = fetchrow
    if execute is not None:
        conn.execute.return_value = execute
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _clear_cache() -> None:
    _module_config_cache.clear()
    _module_config_cache._stale.clear()


@pytest.mark.asyncio
class TestGetEnabledPacks:
    async def test_returns_empty_when_no_row(self):
        _clear_cache()
        pool, _ = _make_pool(fetchrow=None)
        repo = ModuleConfigRepository(pool)

        assert await repo.get_enabled_packs() == []

    async def test_handles_codec_decoded_list(self):
        """Production path: JSONB codec decodes value to a Python list."""
        _clear_cache()
        pool, _ = _make_pool(fetchrow={"value": ["twitch_culture", "lol_lingo"]})
        repo = ModuleConfigRepository(pool)

        assert await repo.get_enabled_packs() == ["twitch_culture", "lol_lingo"]

    async def test_handles_empty_list_value(self):
        """Seed migration stores '[]'::jsonb → decoded to []."""
        _clear_cache()
        pool, _ = _make_pool(fetchrow={"value": []})
        repo = ModuleConfigRepository(pool)

        assert await repo.get_enabled_packs() == []

    async def test_handles_raw_json_string(self):
        """Defensive: if codec isn't registered, value comes back as a string."""
        _clear_cache()
        pool, _ = _make_pool(fetchrow={"value": '["a","b"]'})
        repo = ModuleConfigRepository(pool)

        assert await repo.get_enabled_packs() == ["a", "b"]

    async def test_result_is_cached(self):
        _clear_cache()
        pool, conn = _make_pool(fetchrow={"value": []})
        repo = ModuleConfigRepository(pool)

        await repo.get_enabled_packs()
        await repo.get_enabled_packs()

        assert conn.fetchrow.call_count == 1


@pytest.mark.asyncio
class TestSetEnabledPacks:
    async def test_invalidates_cache(self):
        _clear_cache()
        _module_config_cache.set(_CACHE_KEY, ["stale"])
        pool, _ = _make_pool(execute="INSERT 0 1")
        repo = ModuleConfigRepository(pool)

        await repo.set_enabled_packs(["fresh"])

        assert _CACHE_KEY not in _module_config_cache

    async def test_returns_input_list(self):
        _clear_cache()
        pool, _ = _make_pool(execute="INSERT 0 1")
        repo = ModuleConfigRepository(pool)

        result = await repo.set_enabled_packs(["a", "b"])

        assert result == ["a", "b"]
