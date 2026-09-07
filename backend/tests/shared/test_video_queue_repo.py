"""Unit tests for shared.repositories.video_queue."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.repositories.video_queue import (
    VideoQueueRepository,
    VideoQueueSettingsRepository,
    _settings_cache,
)
from shared.video_sources import (
    YouTubeInfo,
    _app_token_cache,
    _get_twitch_app_token,
    _parse_hms,
    _parse_iso8601_duration,
    extract_bilibili_bvid,
    extract_twitch_clip_slug,
    extract_twitch_vod_info,
    extract_youtube_id,
    extract_youtube_info,
    fetch_twitch_clip_source,
    fetch_twitch_vod_info,
    fetch_yt_info,
    resolve_bilibili_url,
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
    "is_vertical": False,
    "requested_by": "user1",
    "source": "chat",
    "status": "queued",
    "priority": 0,
    "created_at": _NOW,
    "started_at": None,
}

_SETTINGS_ROW = {
    "channel_id": "ch1",
    "enabled": True,
    "redemption_enabled": True,
    "max_duration_redemption": 600,
    "max_queue_size": 20,
    "min_view_count": 0,
    "user_cooldown_seconds": 0,
    "max_per_user": 0,
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


class TestExtractYoutubeInfo:
    def test_regular_url_not_vertical(self):
        video_id, is_vertical = extract_youtube_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert video_id == "dQw4w9WgXcQ"
        assert is_vertical is False

    def test_short_url_not_vertical(self):
        video_id, is_vertical = extract_youtube_info("https://youtu.be/dQw4w9WgXcQ")
        assert video_id == "dQw4w9WgXcQ"
        assert is_vertical is False

    def test_shorts_url_is_vertical(self):
        video_id, is_vertical = extract_youtube_info("https://www.youtube.com/shorts/dQw4w9WgXcQ")
        assert video_id == "dQw4w9WgXcQ"
        assert is_vertical is True

    def test_invalid_url_returns_none(self):
        video_id, is_vertical = extract_youtube_info("https://www.twitch.tv/something")
        assert video_id is None
        assert is_vertical is False


class TestExtractBilibilibvid:
    def test_standard_url(self):
        assert (
            extract_bilibili_bvid("https://www.bilibili.com/video/BV1GJ411x7h7") == "BV1GJ411x7h7"
        )

    def test_url_without_scheme(self):
        assert extract_bilibili_bvid("bilibili.com/video/BV1GJ411x7h7") == "BV1GJ411x7h7"

    def test_url_with_trailing_params(self):
        assert (
            extract_bilibili_bvid("https://www.bilibili.com/video/BV1GJ411x7h7?p=1&t=30")
            == "BV1GJ411x7h7"
        )

    def test_extracts_from_mid_sentence(self):
        assert (
            extract_bilibili_bvid("看這個 https://www.bilibili.com/video/BV1GJ411x7h7 謝謝")
            == "BV1GJ411x7h7"
        )

    def test_returns_none_for_short_url(self):
        assert extract_bilibili_bvid("https://b23.tv/Ab1Cd2E") is None

    def test_returns_none_for_non_bilibili_url(self):
        assert extract_bilibili_bvid("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is None

    def test_returns_none_for_plain_text(self):
        assert extract_bilibili_bvid("no url here") is None


@pytest.mark.asyncio
class TestResolveBilibiliUrl:
    async def test_full_url_resolved_without_http_call(self):
        result = await resolve_bilibili_url("https://www.bilibili.com/video/BV1GJ411x7h7")
        assert result == "BV1GJ411x7h7"

    async def test_returns_none_for_non_bilibili_url(self):
        result = await resolve_bilibili_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result is None

    async def test_short_url_follows_redirect(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_resp = MagicMock()
        mock_resp.url = "https://www.bilibili.com/video/BV1GJ411x7h7"
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session.close = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await resolve_bilibili_url("https://b23.tv/Ab1Cd2E")

        assert result == "BV1GJ411x7h7"
        mock_session.get.assert_called_once()

    async def test_short_url_network_error_returns_none(self):
        from unittest.mock import patch

        import aiohttp

        with patch("aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.side_effect = aiohttp.ClientError("connection refused")
            mock_session.close = AsyncMock(return_value=None)
            mock_cls.return_value = mock_session

            result = await resolve_bilibili_url("https://b23.tv/Ab1Cd2E")

        assert result is None

    async def test_short_url_redirect_to_non_bilibili_returns_none(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_resp = MagicMock()
        mock_resp.url = "https://some-other-site.com/page"
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session.close = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await resolve_bilibili_url("https://b23.tv/Ab1Cd2E")

        assert result is None


class TestExtractTwitchClipSlug:
    def test_clips_domain(self):
        assert (
            extract_twitch_clip_slug("https://clips.twitch.tv/AwkwardHelplessSmoothiePogChamp")
            == "AwkwardHelplessSmoothiePogChamp"
        )

    def test_channel_clip_url(self):
        assert (
            extract_twitch_clip_slug(
                "https://www.twitch.tv/streamer/clip/AwkwardHelplessSmoothiePogChamp"
            )
            == "AwkwardHelplessSmoothiePogChamp"
        )

    def test_url_without_scheme(self):
        assert (
            extract_twitch_clip_slug("clips.twitch.tv/AwkwardHelplessSmoothiePogChamp")
            == "AwkwardHelplessSmoothiePogChamp"
        )

    def test_slug_with_hyphens(self):
        assert (
            extract_twitch_clip_slug("https://clips.twitch.tv/Slug-With-Hyphens_123")
            == "Slug-With-Hyphens_123"
        )

    def test_returns_none_for_non_clip_twitch_url(self):
        assert extract_twitch_clip_slug("https://www.twitch.tv/streamer") is None

    def test_returns_none_for_non_twitch_url(self):
        assert extract_twitch_clip_slug("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is None

    def test_returns_none_for_plain_text(self):
        assert extract_twitch_clip_slug("no url here") is None


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


def _counts(duplicate: int = 0, queue: int = 0, user: int = 0) -> dict:
    """Row shape returned by add_if_within_limits' single combined counts query."""
    return {"duplicate_count": duplicate, "queue_size": queue, "user_count": user}


@pytest.mark.asyncio
class TestAddIfWithinLimits:
    async def test_inserts_when_within_all_limits(self):
        pool, conn = _make_pool()
        conn.fetchrow.side_effect = [_counts(queue=5), _ENTRY_ROW]
        repo = VideoQueueRepository(pool)

        result = await repo.add_if_within_limits(
            "ch1", "dQw4w9WgXcQ", "user1", "chat", max_queue_size=20, max_per_user=0
        )

        assert result is not None
        assert result.video_id == "dQw4w9WgXcQ"

    async def test_acquires_advisory_lock_scoped_to_channel(self):
        pool, conn = _make_pool()
        conn.fetchrow.side_effect = [_counts(queue=5), _ENTRY_ROW]
        repo = VideoQueueRepository(pool)

        await repo.add_if_within_limits(
            "ch1", "dQw4w9WgXcQ", "user1", "chat", max_queue_size=20, max_per_user=0
        )

        first_call_sql = conn.execute.call_args_list[0][0][0]
        assert "pg_advisory_xact_lock" in first_call_sql

    async def test_checks_all_limits_in_a_single_round_trip(self):
        """Combining the three checks into one query matters here: this runs
        while holding an exclusive advisory lock, so fewer round-trips means
        less time every other request for the channel is blocked."""
        pool, conn = _make_pool()
        conn.fetchrow.side_effect = [_counts(queue=5), _ENTRY_ROW]
        repo = VideoQueueRepository(pool)

        await repo.add_if_within_limits(
            "ch1",
            "dQw4w9WgXcQ",
            "user1",
            "chat",
            max_queue_size=20,
            max_per_user=2,
            requested_by_id="u123",
        )

        # One fetchrow for the combined counts query, one for the INSERT.
        assert conn.fetchrow.call_count == 2

    async def test_returns_none_when_video_already_active(self):
        pool, conn = _make_pool()
        conn.fetchrow.side_effect = [_counts(duplicate=1)]
        repo = VideoQueueRepository(pool)

        result = await repo.add_if_within_limits(
            "ch1", "dQw4w9WgXcQ", "user1", "chat", max_queue_size=20, max_per_user=0
        )

        assert result is None
        # Only the counts query ran — no wasted INSERT attempt after rejection.
        assert conn.fetchrow.call_count == 1

    async def test_returns_none_when_queue_full(self):
        pool, conn = _make_pool()
        conn.fetchrow.side_effect = [_counts(queue=20)]
        repo = VideoQueueRepository(pool)

        result = await repo.add_if_within_limits(
            "ch1", "dQw4w9WgXcQ", "user1", "chat", max_queue_size=20, max_per_user=0
        )

        assert result is None
        assert conn.fetchrow.call_count == 1

    async def test_returns_none_when_user_limit_reached(self):
        pool, conn = _make_pool()
        conn.fetchrow.side_effect = [_counts(queue=5, user=2)]
        repo = VideoQueueRepository(pool)

        result = await repo.add_if_within_limits(
            "ch1",
            "dQw4w9WgXcQ",
            "user1",
            "chat",
            max_queue_size=20,
            max_per_user=2,
            requested_by_id="u123",
        )

        assert result is None
        assert conn.fetchrow.call_count == 1

    async def test_inserts_when_user_limit_not_reached(self):
        pool, conn = _make_pool()
        conn.fetchrow.side_effect = [_counts(queue=5, user=1), _ENTRY_ROW]
        repo = VideoQueueRepository(pool)

        result = await repo.add_if_within_limits(
            "ch1",
            "dQw4w9WgXcQ",
            "user1",
            "chat",
            max_queue_size=20,
            max_per_user=2,
            requested_by_id="u123",
        )

        assert result is not None

    async def test_skips_per_user_check_when_max_per_user_is_zero(self):
        """Even if user_count in the row would exceed a real limit, max_per_user=0
        means "no limit" — the check must be skipped, not evaluated as 0 >= 0."""
        pool, conn = _make_pool()
        conn.fetchrow.side_effect = [_counts(queue=5, user=999), _ENTRY_ROW]
        repo = VideoQueueRepository(pool)

        result = await repo.add_if_within_limits(
            "ch1", "dQw4w9WgXcQ", "user1", "chat", max_queue_size=20, max_per_user=0
        )

        assert result is not None


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
class TestGetHistory:
    async def test_maps_rows_and_passes_cursor_and_limit(self):
        done_row = {**_ENTRY_ROW, "id": 9, "status": "done", "ended_at": _NOW}
        pool, conn = _make_pool(fetch=[done_row])
        repo = VideoQueueRepository(pool)

        result = await repo.get_history("ch1", limit=25, before=_NOW)

        assert [e.id for e in result] == [9]
        assert result[0].ended_at == _NOW
        sql, *params = conn.fetch.call_args.args
        assert "status = ANY($2)" in sql and "ended_at DESC" in sql
        assert params == ["ch1", ["done", "skipped"], _NOW, 25]

    async def test_empty(self):
        pool, _ = _make_pool(fetch=[])
        repo = VideoQueueRepository(pool)
        assert await repo.get_history("ch1") == []


@pytest.mark.asyncio
class TestPlayedWithin:
    async def test_true_when_a_recent_done_row_exists(self):
        pool, conn = _make_pool(fetchval=1)
        repo = VideoQueueRepository(pool)
        assert await repo.played_within("ch1", "vid", 12) is True
        sql, *params = conn.fetchval.call_args.args
        assert "status = 'done'" in sql and "make_interval(hours => $3)" in sql
        assert params == ["ch1", "vid", 12]

    async def test_false_when_none(self):
        pool, _ = _make_pool(fetchval=None)
        repo = VideoQueueRepository(pool)
        assert await repo.played_within("ch1", "vid", 12) is False


@pytest.mark.asyncio
class TestPruneHistory:
    async def test_returns_deleted_count(self):
        pool, conn = _make_pool(execute="DELETE 7")
        repo = VideoQueueRepository(pool)

        assert await repo.prune_history() == 7
        sql, *params = conn.execute.call_args.args
        assert "make_interval(days => $2)" in sql
        assert params == [["done", "skipped"], 30]

    async def test_zero_when_nothing_deleted(self):
        pool, _ = _make_pool(execute="DELETE 0")
        repo = VideoQueueRepository(pool)
        assert await repo.prune_history() == 0


@pytest.mark.asyncio
class TestGetCurrentAndQueued:
    async def test_single_connection_acquire(self):
        pool, conn = _make_pool(fetch=[])
        repo = VideoQueueRepository(pool)

        await repo.get_current_and_queued("ch1")

        pool.acquire.assert_called_once()
        conn.fetch.assert_called_once()

    async def test_splits_playing_and_queued_rows(self):
        playing_row = {**_ENTRY_ROW, "id": 1, "status": "playing"}
        queued_row = {**_ENTRY_ROW, "id": 2, "status": "queued"}
        pool, _ = _make_pool(fetch=[playing_row, queued_row])
        repo = VideoQueueRepository(pool)

        current, queued = await repo.get_current_and_queued("ch1")

        assert current is not None
        assert current.id == 1
        assert current.status == "playing"
        assert [e.id for e in queued] == [2]

    async def test_returns_none_current_when_nothing_playing(self):
        pool, _ = _make_pool(fetch=[{**_ENTRY_ROW, "id": 2, "status": "queued"}])
        repo = VideoQueueRepository(pool)

        current, queued = await repo.get_current_and_queued("ch1")

        assert current is None
        assert len(queued) == 1

    async def test_tolerates_stale_duplicate_playing_row(self):
        """A pre-fix duplicate 'playing' row (see advance_queue's NOT EXISTS
        guard) must not crash the stream wake path — pick the first and move on."""
        rows = [
            {**_ENTRY_ROW, "id": 1, "status": "playing"},
            {**_ENTRY_ROW, "id": 2, "status": "playing"},
        ]
        pool, _ = _make_pool(fetch=rows)
        repo = VideoQueueRepository(pool)

        current, queued = await repo.get_current_and_queued("ch1")

        assert current is not None
        assert current.id == 1
        assert queued == []


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
class TestCountActiveByUser:
    async def test_returns_count(self):
        pool, conn = _make_pool(fetchval=2)
        repo = VideoQueueRepository(pool)

        result = await repo.count_active_by_user("ch1", "viewer1")

        assert result == 2
        conn.fetchval.assert_called_once()
        sql = conn.fetchval.call_args[0][0]
        assert "queued" in sql
        assert "playing" in sql

    async def test_returns_zero_when_none(self):
        pool, _ = _make_pool(fetchval=0)
        repo = VideoQueueRepository(pool)

        result = await repo.count_active_by_user("ch1", "viewer1")

        assert result == 0


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


# ---------------------------------------------------------------------------
# VideoQueueRepository — advance_queue + skip_current_atomic (new methods)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAdvanceQueue:
    async def test_uses_transaction(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.advance_queue("ch1", done_id=42)

        conn.transaction.assert_called_once()

    async def test_calls_two_updates(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.advance_queue("ch1", done_id=42)

        assert conn.execute.call_count == 2

    async def test_first_update_marks_done(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.advance_queue("ch1", done_id=42)

        first_call_sql: str = conn.execute.call_args_list[0][0][0]
        assert "done" in first_call_sql
        assert "playing" in first_call_sql

    async def test_second_update_promotes_queued(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.advance_queue("ch1", done_id=42)

        second_call_sql: str = conn.execute.call_args_list[1][0][0]
        assert "playing" in second_call_sql
        assert "queued" in second_call_sql

    async def test_done_id_is_passed_as_parameter(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.advance_queue("ch1", done_id=99)

        first_call_args = conn.execute.call_args_list[0][0]
        assert 99 in first_call_args

    async def test_promote_guards_against_already_playing_row(self):
        """Regression: without this guard, two overlays finishing the same
        done_id concurrently (or an overlay finishing while a dashboard
        Play-Now runs) can both promote a queued entry, leaving two rows
        'playing' — a state get_current can't see and kickstart_if_idle can
        never recover from. Same guard as kickstart_if_idle."""
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.advance_queue("ch1", done_id=42)

        second_call_sql: str = conn.execute.call_args_list[1][0][0]
        assert "NOT EXISTS" in second_call_sql
        assert "status = 'playing'" in second_call_sql


@pytest.mark.asyncio
class TestSkipCurrentAtomic:
    async def test_uses_transaction(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.skip_current_atomic("ch1")

        conn.transaction.assert_called_once()

    async def test_calls_two_updates(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.skip_current_atomic("ch1")

        assert conn.execute.call_count == 2

    async def test_first_update_marks_skipped(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.skip_current_atomic("ch1")

        first_call_sql: str = conn.execute.call_args_list[0][0][0]
        assert "skipped" in first_call_sql
        assert "playing" in first_call_sql

    async def test_second_update_promotes_queued(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.skip_current_atomic("ch1")

        second_call_sql: str = conn.execute.call_args_list[1][0][0]
        assert "playing" in second_call_sql
        assert "queued" in second_call_sql

    async def test_channel_id_is_scoped(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.skip_current_atomic("ch_target")

        for call in conn.execute.call_args_list:
            assert "ch_target" in call[0]


# ---------------------------------------------------------------------------
# VideoQueueRepository — kickstart_if_idle (atomic promote-if-idle)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestKickstartIfIdle:
    async def test_executes_single_update(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.kickstart_if_idle("ch1")

        conn.execute.assert_called_once()

    async def test_sql_promotes_to_playing(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.kickstart_if_idle("ch1")

        sql: str = conn.execute.call_args[0][0]
        assert "playing" in sql
        assert "queued" in sql

    async def test_sql_has_not_exists_guard(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.kickstart_if_idle("ch1")

        sql: str = conn.execute.call_args[0][0]
        assert "NOT EXISTS" in sql.upper()

    async def test_channel_id_passed_as_parameter(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = VideoQueueRepository(pool)

        await repo.kickstart_if_idle("ch_target")

        assert "ch_target" in conn.execute.call_args[0]

    async def test_no_op_when_nothing_queued(self):
        pool, conn = _make_pool(execute="UPDATE 0")
        repo = VideoQueueRepository(pool)

        await repo.kickstart_if_idle("ch_empty")

        conn.execute.assert_called_once()


# ---------------------------------------------------------------------------
# fetch_yt_info — returns YouTubeInfo; failure paths are fail-open (playable)
# ---------------------------------------------------------------------------


def _yt_resp(payload: dict) -> MagicMock:
    from unittest.mock import AsyncMock

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=payload)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.close = AsyncMock(return_value=None)
    return mock_session


@pytest.mark.asyncio
class TestFetchYtInfo:
    async def test_no_api_key_returns_empty_playable(self):
        result = await fetch_yt_info("dQw4w9WgXcQ", api_key="")
        assert result == YouTubeInfo()
        assert result.playable is True

    async def test_bad_status_is_fail_open(self):
        from unittest.mock import AsyncMock, patch

        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.close = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await fetch_yt_info("dQw4w9WgXcQ", api_key="fake_key")

        assert result == YouTubeInfo()

    async def test_empty_items_is_fail_open(self):
        from unittest.mock import patch

        with patch("aiohttp.ClientSession", return_value=_yt_resp({"items": []})):
            result = await fetch_yt_info("dQw4w9WgXcQ", api_key="fake_key")

        assert result == YouTubeInfo()

    async def test_network_error_is_fail_open(self):
        from unittest.mock import AsyncMock, patch

        import aiohttp

        with patch("aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.get.side_effect = aiohttp.ClientError("connection refused")
            mock_session.close = AsyncMock(return_value=None)
            mock_cls.return_value = mock_session

            result = await fetch_yt_info("dQw4w9WgXcQ", api_key="fake_key")

        assert result == YouTubeInfo()

    async def test_ok_video_is_playable_with_metadata(self):
        from unittest.mock import patch

        payload = {
            "items": [
                {
                    "snippet": {"title": "Fine", "thumbnails": {}},
                    "contentDetails": {"duration": "PT3M20S", "contentRating": {}},
                    "statistics": {"viewCount": "4321"},
                    "status": {
                        "uploadStatus": "processed",
                        "privacyStatus": "public",
                        "embeddable": True,
                    },
                }
            ]
        }
        with patch("aiohttp.ClientSession", return_value=_yt_resp(payload)):
            result = await fetch_yt_info("dQw4w9WgXcQ", api_key="fake_key")

        assert result.title == "Fine"
        assert result.duration_seconds == 200
        assert result.view_count == 4321
        assert result.playable is True
        assert result.unplayable_reason is None

    @pytest.mark.parametrize(
        ("status", "content_rating", "expected"),
        [
            ({"embeddable": False, "privacyStatus": "public"}, {}, "not_embeddable"),
            ({"privacyStatus": "private"}, {}, "private"),
            ({"uploadStatus": "deleted"}, {}, "removed"),
            ({"privacyStatus": "public"}, {"ytRating": "ytAgeRestricted"}, "age_restricted"),
        ],
    )
    async def test_disqualifying_status_sets_reason(self, status, content_rating, expected):
        from unittest.mock import patch

        payload = {
            "items": [
                {
                    "snippet": {"title": "X", "thumbnails": {}},
                    "contentDetails": {"duration": "PT1M", "contentRating": content_rating},
                    "statistics": {"viewCount": "10"},
                    "status": status,
                }
            ]
        }
        with patch("aiohttp.ClientSession", return_value=_yt_resp(payload)):
            result = await fetch_yt_info("dQw4w9WgXcQ", api_key="fake_key")

        assert result.playable is False
        assert result.unplayable_reason == expected


# ---------------------------------------------------------------------------
# _get_twitch_app_token — caching behaviour
# ---------------------------------------------------------------------------


def _make_aiohttp_post_cm(status: int, json_data: dict) -> MagicMock:
    """Return an async context manager that simulates aiohttp ClientSession.post."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def _make_session(post_cm: MagicMock) -> MagicMock:
    """Return a MagicMock aiohttp session whose post() returns the given CM directly.

    Must be MagicMock (not AsyncMock) because session.post() is used as
    ``async with session.post(...) as resp:`` — calling an AsyncMock returns a
    coroutine, which does not support the async context manager protocol.
    """
    session = MagicMock()
    session.post.return_value = post_cm
    return session


@pytest.mark.asyncio
class TestGetTwitchAppToken:
    def setup_method(self):
        """Clear the module-level token cache before each test."""
        _app_token_cache.clear()

    async def test_fetches_token_on_first_call(self):
        session = _make_session(
            _make_aiohttp_post_cm(200, {"access_token": "tok_abc", "expires_in": 3600})
        )

        result = await _get_twitch_app_token("cid", "csec", session)

        assert result == "tok_abc"
        session.post.assert_called_once()

    async def test_returns_cached_token_on_second_call(self):
        session = _make_session(
            _make_aiohttp_post_cm(200, {"access_token": "tok_cached", "expires_in": 3600})
        )

        first = await _get_twitch_app_token("cid", "csec", session)
        second = await _get_twitch_app_token("cid", "csec", session)

        assert first == second == "tok_cached"
        # Token endpoint must only be called once despite two invocations
        session.post.assert_called_once()

    async def test_expired_cache_triggers_refetch(self):
        import time

        # Pre-populate cache with an already-expired token
        _app_token_cache[("cid", "csec")] = ("old_tok", time.monotonic() - 1)

        session = _make_session(
            _make_aiohttp_post_cm(200, {"access_token": "new_tok", "expires_in": 3600})
        )

        result = await _get_twitch_app_token("cid", "csec", session)

        assert result == "new_tok"
        session.post.assert_called_once()

    async def test_failed_fetch_returns_none_and_does_not_cache(self):
        session = _make_session(_make_aiohttp_post_cm(401, {}))

        result = await _get_twitch_app_token("cid", "csec", session)

        assert result is None
        assert ("cid", "csec") not in _app_token_cache

    async def test_different_credentials_use_separate_cache_entries(self):
        session = MagicMock()
        session.post.side_effect = [
            _make_aiohttp_post_cm(200, {"access_token": "tok_A", "expires_in": 3600}),
            _make_aiohttp_post_cm(200, {"access_token": "tok_B", "expires_in": 3600}),
        ]

        tok_a = await _get_twitch_app_token("cid_A", "csec_A", session)
        tok_b = await _get_twitch_app_token("cid_B", "csec_B", session)

        assert tok_a == "tok_A"
        assert tok_b == "tok_B"
        assert session.post.call_count == 2


def _clip_gql_ok(signature: str, value: str, source_url: str) -> dict:
    return {
        "data": {
            "clip": {
                "playbackAccessToken": {"signature": signature, "value": value},
                "assets": [
                    {
                        "videoQualities": [
                            {"quality": "1080", "sourceURL": source_url},
                            {"quality": "720", "sourceURL": source_url + "?q=720"},
                        ]
                    }
                ],
            }
        }
    }


@pytest.mark.asyncio
class TestFetchTwitchClipSource:
    async def test_builds_signed_url_from_top_quality(self):
        payload = [_clip_gql_ok("sig123", "tok val/+", "https://cdn.example/clip.mp4")]
        session = _make_session(_make_aiohttp_post_cm(200, payload))

        result = await fetch_twitch_clip_source("SomeSlug", session)

        assert result == "https://cdn.example/clip.mp4?sig=sig123&token=tok%20val%2F%2B"

    async def test_appends_with_ampersand_when_source_has_query(self):
        payload = [_clip_gql_ok("s", "t", "https://cdn.example/clip.mp4?x=1")]
        session = _make_session(_make_aiohttp_post_cm(200, payload))

        result = await fetch_twitch_clip_source("Slug", session)

        assert result == "https://cdn.example/clip.mp4?x=1&sig=s&token=t"

    async def test_non_200_returns_none(self):
        session = _make_session(_make_aiohttp_post_cm(400, []))
        assert await fetch_twitch_clip_source("Slug", session) is None

    async def test_null_clip_returns_none(self):
        session = _make_session(_make_aiohttp_post_cm(200, [{"data": {"clip": None}}]))
        assert await fetch_twitch_clip_source("Slug", session) is None

    async def test_missing_token_returns_none(self):
        payload = [{"data": {"clip": {"assets": [{"videoQualities": []}]}}}]
        session = _make_session(_make_aiohttp_post_cm(200, payload))
        assert await fetch_twitch_clip_source("Slug", session) is None

    async def test_network_error_returns_none(self):
        session = MagicMock()
        session.post.side_effect = RuntimeError("boom")
        assert await fetch_twitch_clip_source("Slug", session) is None


class TestParseHms:
    def test_full(self):
        assert _parse_hms("1h2m3s") == 3723

    def test_partial(self):
        assert _parse_hms("90m") == 5400
        assert _parse_hms("45s") == 45

    def test_bare_seconds(self):
        assert _parse_hms("3600") == 3600

    def test_garbage(self):
        assert _parse_hms("") == 0
        assert _parse_hms("abc") == 0


class TestExtractTwitchVodInfo:
    def test_plain_url(self):
        assert extract_twitch_vod_info("https://www.twitch.tv/videos/123456789") == (
            "123456789",
            0,
        )

    def test_with_timestamp(self):
        assert extract_twitch_vod_info("https://www.twitch.tv/videos/42?t=1h30m") == ("42", 5400)

    def test_mobile_host(self):
        assert extract_twitch_vod_info("https://m.twitch.tv/videos/7") == ("7", 0)

    def test_not_a_vod(self):
        assert extract_twitch_vod_info("https://www.twitch.tv/somechannel") == (None, 0)
        assert extract_twitch_vod_info("https://clips.twitch.tv/Slug") == (None, 0)


@pytest.mark.asyncio
class TestFetchTwitchVodInfo:
    def setup_method(self):
        _app_token_cache.clear()

    async def _session(self, videos_payload):
        from unittest.mock import AsyncMock

        get_resp = MagicMock()
        get_resp.status = 200
        get_resp.json = AsyncMock(return_value={"data": videos_payload})
        get_cm = MagicMock()
        get_cm.__aenter__ = AsyncMock(return_value=get_resp)
        get_cm.__aexit__ = AsyncMock(return_value=None)

        session = MagicMock()
        session.post.return_value = _make_aiohttp_post_cm(
            200, {"access_token": "tok", "expires_in": 3600}
        )
        session.get.return_value = get_cm
        return session

    async def test_parses_helix_duration(self):
        session = await self._session(
            [{"title": "Stream", "duration": "3h20m5s", "view_count": 42}]
        )
        assert await fetch_twitch_vod_info("v1", "cid", "csec", session) == ("Stream", 12005, 42)

    async def test_empty_data_returns_none(self):
        session = await self._session([])
        assert await fetch_twitch_vod_info("v1", "cid", "csec", session) == (None, None, None)

    async def test_missing_creds_returns_none(self):
        assert await fetch_twitch_vod_info("v1", "", "", MagicMock()) == (None, None, None)
