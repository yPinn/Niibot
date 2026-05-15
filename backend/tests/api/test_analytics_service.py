"""Unit tests for api.services.analytics_service — AnalyticsService."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.analytics_service import AnalyticsService

CHANNEL_ID = "ch-123"
USER_ID = "u-456"
_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


def _make_svc() -> tuple[AnalyticsService, MagicMock]:
    pool = MagicMock()
    repo = MagicMock()
    with patch("services.analytics_service.AnalyticsRepository", return_value=repo):
        svc = AnalyticsService(pool)
    return svc, repo


# ---------------------------------------------------------------------------
# Delegation tests — each method must forward args and return repo result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_summary_delegates():
    svc, repo = _make_svc()
    repo.get_summary = AsyncMock(return_value={"sessions": 5})
    result = await svc.get_summary(CHANNEL_ID, days=7)
    repo.get_summary.assert_awaited_once_with(CHANNEL_ID, 7)
    assert result == {"sessions": 5}


@pytest.mark.asyncio
async def test_get_session_commands_delegates():
    svc, repo = _make_svc()
    repo.get_session_commands = AsyncMock(return_value=[{"name": "!hi"}])
    result = await svc.get_session_commands(1, CHANNEL_ID)
    repo.get_session_commands.assert_awaited_once_with(1, CHANNEL_ID)
    assert result == [{"name": "!hi"}]


@pytest.mark.asyncio
async def test_get_session_events_delegates():
    svc, repo = _make_svc()
    repo.get_session_events = AsyncMock(return_value=[])
    result = await svc.get_session_events(1, CHANNEL_ID)
    repo.get_session_events.assert_awaited_once_with(1, CHANNEL_ID)
    assert result == []


@pytest.mark.asyncio
async def test_get_top_commands_delegates():
    svc, repo = _make_svc()
    repo.list_top_commands = AsyncMock(return_value=[{"command_name": "!hi", "count": 10}])
    result = await svc.get_top_commands(CHANNEL_ID, days=14, limit=5)
    repo.list_top_commands.assert_awaited_once_with(CHANNEL_ID, 14, 5)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_get_insights_delegates():
    svc, repo = _make_svc()
    repo.get_insights = AsyncMock(return_value={"peak_hour": 20})
    result = await svc.get_insights(CHANNEL_ID)
    repo.get_insights.assert_awaited_once_with(CHANNEL_ID, 30)
    assert result["peak_hour"] == 20


@pytest.mark.asyncio
async def test_list_viewers_delegates():
    svc, repo = _make_svc()
    repo.list_viewers = AsyncMock(return_value=[{"user_id": USER_ID}])
    result = await svc.list_viewers(CHANNEL_ID, days=30, limit=10)
    repo.list_viewers.assert_awaited_once_with(CHANNEL_ID, 30, 10)
    assert result[0]["user_id"] == USER_ID


@pytest.mark.asyncio
async def test_get_viewer_profile_delegates():
    svc, repo = _make_svc()
    repo.get_viewer_profile = AsyncMock(return_value={"user_id": USER_ID})
    result = await svc.get_viewer_profile(CHANNEL_ID, USER_ID)
    repo.get_viewer_profile.assert_awaited_once_with(CHANNEL_ID, USER_ID, 30)
    assert result["user_id"] == USER_ID


@pytest.mark.asyncio
async def test_get_viewer_session_attendance_delegates():
    svc, repo = _make_svc()
    repo.get_viewer_session_attendance = AsyncMock(return_value=[])
    result = await svc.get_viewer_session_attendance(CHANNEL_ID, USER_ID)
    repo.get_viewer_session_attendance.assert_awaited_once_with(CHANNEL_ID, USER_ID, 30)
    assert result == []


@pytest.mark.asyncio
async def test_get_viewer_channel_status_delegates():
    svc, repo = _make_svc()
    repo.get_viewer_channel_status = AsyncMock(return_value={"subscribed": True})
    result = await svc.get_viewer_channel_status(CHANNEL_ID, USER_ID)
    repo.get_viewer_channel_status.assert_awaited_once_with(CHANNEL_ID, USER_ID)
    assert result["subscribed"] is True


@pytest.mark.asyncio
async def test_bulk_upsert_follow_dates_delegates():
    svc, repo = _make_svc()
    repo.bulk_upsert_follow_dates = AsyncMock(return_value=3)
    result = await svc.bulk_upsert_follow_dates(CHANNEL_ID, [{}])
    repo.bulk_upsert_follow_dates.assert_awaited_once_with(CHANNEL_ID, [{}])
    assert result == 3


@pytest.mark.asyncio
async def test_bulk_upsert_mod_status_delegates():
    svc, repo = _make_svc()
    repo.bulk_upsert_mod_status = AsyncMock(return_value=2)
    result = await svc.bulk_upsert_mod_status(CHANNEL_ID, [{}])
    repo.bulk_upsert_mod_status.assert_awaited_once_with(CHANNEL_ID, [{}])
    assert result == 2


@pytest.mark.asyncio
async def test_bulk_upsert_vip_status_delegates():
    svc, repo = _make_svc()
    repo.bulk_upsert_vip_status = AsyncMock(return_value=1)
    result = await svc.bulk_upsert_vip_status(CHANNEL_ID, [{}])
    repo.bulk_upsert_vip_status.assert_awaited_once_with(CHANNEL_ID, [{}])
    assert result == 1


@pytest.mark.asyncio
async def test_bulk_upsert_subscribers_delegates():
    svc, repo = _make_svc()
    repo.bulk_upsert_subscribers = AsyncMock(return_value=5)
    result = await svc.bulk_upsert_subscribers(CHANNEL_ID, [{}])
    repo.bulk_upsert_subscribers.assert_awaited_once_with(CHANNEL_ID, [{}])
    assert result == 5


@pytest.mark.asyncio
async def test_upsert_viewer_profile_cache_delegates():
    svc, repo = _make_svc()
    repo.upsert_viewer_profile_cache = AsyncMock(return_value=None)
    await svc.upsert_viewer_profile_cache(
        CHANNEL_ID, USER_ID, "alice", "Alice", None, None, _NOW, "partner"
    )
    repo.upsert_viewer_profile_cache.assert_awaited_once()
    kw = repo.upsert_viewer_profile_cache.await_args.kwargs
    assert kw["channel_id"] == CHANNEL_ID
    assert kw["broadcaster_type"] == "partner"
