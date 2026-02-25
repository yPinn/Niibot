"""Unit tests for shared.repositories.video_queue."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.repositories.video_queue import (
    VideoQueueRepository,
    VideoQueueSettingsRepository,
    _parse_iso8601_duration,
    _settings_cache,
    extract_youtube_id,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 1, 1, tzinfo=UTC)

_ENTRY_ROW = {
    "id": 1,
    "channel_id": "ch1",
    "video_id": "dQw4w9WgXcQ",
    "title": "Never Gonna Give You Up",
    "duration_seconds": 213,
    "requested_by": "user1",
    "source": "chat",
    "status": "queued",
    "created_at": _NOW,
    "started_at": None,
    "ended_at": None,
}

_SETTINGS_ROW = {
    "channel_id": "ch1",
    "enabled": True,
    "min_role_chat": "everyone",
    "max_duration_seconds": 600,
    "max_queue_size": 20,
    "created_at": _NOW,
    "updated_at": _NOW,
}

_UNSET = object()


def _make_pool(
    *,
    fetch=_UNSET,
    fetchrow=_UNSET,
    execute=_UNSET,
    fetchval=_UNSET,
) -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    if fetch is not _UNSET:
        conn.fetch.return_value = fetch
    if fetchrow is not _UNSET:
        conn.fetchrow.return_value = fetchrow
    if execute is not _UNSET:
        conn.execute.return_value = execute
    if fetchval is not _UNSET:
        conn.fetchval.return_value = fetchval

    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=None)
    mock_tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=mock_tx)

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _clear_caches() -> None:
    _settings_cache.clear()
    _settings_cache._stale.clear()


# ---------------------------------------------------------------------------
# Pure utility functions
# ---------------------------------------------------------------------------


class TestExtractYoutubeId:
    def test_standard_watch_url(self):
        assert extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert extract_youtube_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        assert extract_youtube_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_url_with_extra_params(self):
        assert (
            extract_youtube_id("https://www.youtube.com/watch?t=30&v=dQw4w9WgXcQ&list=PL")
            == "dQw4w9WgXcQ"
        )

    def test_returns_none_for_non_youtube_url(self):
        assert extract_youtube_id("https://www.twitch.tv/something") is None

    def test_returns_none_for_plain_text(self):
        assert extract_youtube_id("no url here") is None

    def test_extracts_from_mid_sentence(self):
        assert (
            extract_youtube_id("check this out https://youtu.be/dQw4w9WgXcQ thanks")
            == "dQw4w9WgXcQ"
        )


class TestParseIso8601Duration:
    def test_hours_minutes_seconds(self):
        assert _parse_iso8601_duration("PT1H3M45S") == 3825

    def test_minutes_seconds(self):
        assert _parse_iso8601_duration("PT3M33S") == 213

    def test_seconds_only(self):
        assert _parse_iso8601_duration("PT45S") == 45

    def test_hours_only(self):
        assert _parse_iso8601_duration("PT2H") == 7200

    def test_returns_zero_for_invalid(self):
        assert _parse_iso8601_duration("") == 0

    def test_returns_zero_for_non_matching(self):
        assert _parse_iso8601_duration("P1D") == 0


# ---------------------------------------------------------------------------
# VideoQueueRepository
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAdd:
    async def test_returns_new_entry(self):
        pool, _ = _make_pool(fetchrow=_ENTRY_ROW)
        repo = VideoQueueRepository(pool)

        result = await repo.add(
            "ch1", "dQw4w9WgXcQ", "user1", "chat", title="Rick Roll", duration_seconds=213
        )

        assert result.video_id == "dQw4w9WgXcQ"
        assert result.status == "queued"


@pytest.mark.asyncio
class TestGetCurrent:
    async def test_returns_none_when_nothing_playing(self):
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        repo = VideoQueueRepository(pool)

        result = await repo.get_current("ch1")

        assert result is None

    async def test_returns_playing_entry(self):
        pool, _ = _make_pool(fetchrow={**_ENTRY_ROW, "status": "playing"})
        repo = VideoQueueRepository(pool)

        result = await repo.get_current("ch1")

        assert result is not None
        assert result.status == "playing"


@pytest.mark.asyncio
class TestGetQueued:
    async def test_returns_empty_list(self):
        pool, _ = _make_pool(fetch=[])
        repo = VideoQueueRepository(pool)

        result = await repo.get_queued("ch1")

        assert result == []

    async def test_returns_queued_entries(self):
        pool, _ = _make_pool(fetch=[_ENTRY_ROW])
        repo = VideoQueueRepository(pool)

        result = await repo.get_queued("ch1")

        assert len(result) == 1
        assert result[0].status == "queued"


@pytest.mark.asyncio
class TestGetQueueSize:
    async def test_returns_count(self):
        pool, _ = _make_pool(fetchval=3)
        repo = VideoQueueRepository(pool)

        result = await repo.get_queue_size("ch1")

        assert result == 3


@pytest.mark.asyncio
class TestVideoIsActive:
    async def test_returns_true_when_active(self):
        pool, _ = _make_pool(fetchval=1)
        repo = VideoQueueRepository(pool)

        result = await repo.video_is_active("ch1", "dQw4w9WgXcQ")

        assert result is True

    async def test_returns_false_when_not_active(self):
        pool, _ = _make_pool(fetchval=0)
        repo = VideoQueueRepository(pool)

        result = await repo.video_is_active("ch1", "dQw4w9WgXcQ")

        assert result is False


@pytest.mark.asyncio
class TestStatusTransitions:
    async def test_set_playing_executes_update(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.set_playing(1)

        conn.execute.assert_called_once()
        assert "playing" in conn.execute.call_args[0][0]

    async def test_mark_done_executes_update(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.mark_done(1, "ch1")

        conn.execute.assert_called_once()
        assert "done" in conn.execute.call_args[0][0]

    async def test_mark_skipped_executes_update(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.mark_skipped(1, "ch1")

        conn.execute.assert_called_once()
        assert "skipped" in conn.execute.call_args[0][0]

    async def test_update_duration_executes_update(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.update_duration(1, 300, "ch1")

        conn.execute.assert_called_once()


@pytest.mark.asyncio
class TestClearQueued:
    async def test_returns_affected_count(self):
        pool, _ = _make_pool(execute="UPDATE 5")
        repo = VideoQueueRepository(pool)

        count = await repo.clear_queued("ch1")

        assert count == 5

    async def test_returns_zero_when_nothing_queued(self):
        pool, _ = _make_pool(execute="UPDATE 0")
        repo = VideoQueueRepository(pool)

        count = await repo.clear_queued("ch1")

        assert count == 0


@pytest.mark.asyncio
class TestFindLastQueuedByUser:
    async def test_returns_none_when_not_found(self):
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        repo = VideoQueueRepository(pool)

        result = await repo.find_last_queued_by_user("ch1", "user1")

        assert result is None

    async def test_returns_entry_when_found(self):
        pool, _ = _make_pool(fetchrow=_ENTRY_ROW)
        repo = VideoQueueRepository(pool)

        result = await repo.find_last_queued_by_user("ch1", "user1")

        assert result is not None
        assert result.requested_by == "user1"


# ---------------------------------------------------------------------------
# VideoQueueSettingsRepository
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetOrCreate:
    async def test_returns_settings(self):
        _clear_caches()
        pool, _ = _make_pool(fetchrow=_SETTINGS_ROW)
        repo = VideoQueueSettingsRepository(pool)

        result = await repo.get_or_create("ch1")

        assert result.channel_id == "ch1"
        assert result.enabled is True

    async def test_result_is_cached(self):
        _clear_caches()
        pool, conn = _make_pool(fetchrow=_SETTINGS_ROW)
        repo = VideoQueueSettingsRepository(pool)

        await repo.get_or_create("ch1")
        await repo.get_or_create("ch1")

        assert conn.fetchrow.call_count == 1

    async def test_uses_transaction(self):
        _clear_caches()
        pool, conn = _make_pool(fetchrow=_SETTINGS_ROW)
        repo = VideoQueueSettingsRepository(pool)

        await repo.get_or_create("ch1")

        conn.transaction.assert_called_once()


@pytest.mark.asyncio
class TestUpdateSettings:
    async def test_returns_updated_settings(self):
        _clear_caches()
        updated_row = {**_SETTINGS_ROW, "max_queue_size": 50}
        pool, _ = _make_pool(fetchrow=updated_row)
        repo = VideoQueueSettingsRepository(pool)

        result = await repo.update_settings("ch1", max_queue_size=50)

        assert result.max_queue_size == 50

    async def test_invalidates_settings_cache(self):
        _settings_cache.set("vq_settings:ch1", _SETTINGS_ROW)
        pool, _ = _make_pool(fetchrow=_SETTINGS_ROW)
        repo = VideoQueueSettingsRepository(pool)

        await repo.update_settings("ch1", enabled=False)

        from shared.cache import _MISSING

        assert _settings_cache.get("vq_settings:ch1") is _MISSING
