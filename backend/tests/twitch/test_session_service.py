"""Unit tests for SessionService — lifecycle, hot path, watch-time token flow."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.session_service import SessionService, parse_twitch_duration


@pytest.mark.parametrize(
    "s, expected",
    [
        ("3h21m15s", timedelta(hours=3, minutes=21, seconds=15)),
        ("1h0m0s", timedelta(hours=1)),
        ("45m30s", timedelta(minutes=45, seconds=30)),
        ("30s", timedelta(seconds=30)),
        ("2h", timedelta(hours=2)),
        ("10m", timedelta(minutes=10)),
        ("0h0m0s", timedelta()),
        ("", timedelta()),
    ],
)
def test_parse_twitch_duration(s: str, expected: timedelta) -> None:
    assert parse_twitch_duration(s) == expected


def _analytics() -> MagicMock:
    a = MagicMock()
    a.get_active_session = AsyncMock(return_value=None)
    a.create_session = AsyncMock(return_value=42)
    a.flush_chatter_stats = AsyncMock()
    a.end_session = AsyncMock()
    a.close_stale_sessions = AsyncMock(return_value=0)
    a.increment_watch_seconds = AsyncMock()
    a.record_attendance_snapshot = AsyncMock(return_value=True)
    a.refresh_overlap = AsyncMock()
    return a


def _make_service(*, analytics=None, channels=None, client=None) -> SessionService:
    subs = MagicMock()
    subs.ch = lambda cid: cid
    return SessionService(
        analytics=analytics or _analytics(),
        channels=channels or MagicMock(),
        subs=subs,
        client=client or MagicMock(),
        bot_id="bot-001",
        client_id="client-abc",
    )


def _stream(channel_id="ch1", started_at=None, title="T", game_name="G", game_id="1"):
    return SimpleNamespace(
        user=SimpleNamespace(id=channel_id),
        started_at=started_at,
        title=title,
        game_name=game_name,
        game_id=game_id,
    )


class TestEnsureSession:
    pytestmark = pytest.mark.asyncio

    async def test_returns_existing_active_without_creating(self):
        svc = _make_service()
        svc._active["ch1"] = 7
        assert await svc.ensure_session("ch1") == 7
        svc._analytics.create_session.assert_not_awaited()

    async def test_in_flight_returns_none(self):
        svc = _make_service()
        svc._creating.add("ch1")
        assert await svc.ensure_session("ch1") is None

    async def test_resumes_db_session(self):
        a = _analytics()
        a.get_active_session = AsyncMock(return_value={"id": 99})
        svc = _make_service(analytics=a)
        assert await svc.ensure_session("ch1", stream=_stream()) == 99
        assert svc._active["ch1"] == 99
        a.create_session.assert_not_awaited()

    async def test_offline_without_flag_does_not_create(self):
        svc = _make_service()
        assert await svc.ensure_session("ch1", stream=None, create_if_offline=False) is None
        svc._analytics.create_session.assert_not_awaited()

    async def test_offline_with_flag_creates(self):
        svc = _make_service()
        sid = await svc.ensure_session("ch1", stream=None, create_if_offline=True)
        assert sid == 42
        assert svc._active["ch1"] == 42

    async def test_creates_from_stream_fields(self):
        svc = _make_service()
        await svc.ensure_session("ch1", stream=_stream(title="Live", game_name="Chess"))
        kwargs = svc._analytics.create_session.await_args.kwargs
        assert kwargs["title"] == "Live"
        assert kwargs["game_name"] == "Chess"
        assert kwargs["game_id"] == "1"


class TestEndSession:
    pytestmark = pytest.mark.asyncio

    async def test_no_session_clears_buffers_only(self):
        svc = _make_service()
        svc._buffers["ch1"] = {"u": {"count": 1}}
        svc._line_counts["ch1"] = 5
        await svc.end_session("ch1")
        assert "ch1" not in svc._buffers
        assert "ch1" not in svc._line_counts
        svc._analytics.end_session.assert_not_awaited()

    async def test_flush_then_end_then_overlap(self):
        svc = _make_service()
        svc._active["ch1"] = 42
        svc._buffers["ch1"] = {"u1": {"count": 3}}
        await svc.end_session("ch1")
        svc._analytics.flush_chatter_stats.assert_awaited_once()
        svc._analytics.end_session.assert_awaited_once()
        assert "ch1" not in svc._active
        await asyncio.sleep(0)  # let the fire-and-forget overlap task run
        svc._analytics.refresh_overlap.assert_awaited_once_with("ch1")

    async def test_end_session_retries(self):
        a = _analytics()
        a.end_session = AsyncMock(side_effect=[RuntimeError("x"), RuntimeError("y"), None])
        svc = _make_service(analytics=a)
        svc._active["ch1"] = 42
        with patch("core.session_service.asyncio.sleep", new=AsyncMock()):
            await svc.end_session("ch1")
        assert a.end_session.await_count == 3


class TestRecordLine:
    def test_noop_when_not_live(self):
        svc = _make_service()
        svc.record_line("ch1", "u1", "user", "User")
        assert svc.line_count("ch1") == 0
        assert "ch1" not in svc._buffers

    def test_accumulates_when_live(self):
        svc = _make_service()
        svc._active["ch1"] = 1
        svc.record_line("ch1", "u1", "user", "User")
        svc.record_line("ch1", "u1", "user", "User")
        svc.record_line("ch1", "u2", "two", "Two")
        assert svc.line_count("ch1") == 3
        assert svc._buffers["ch1"]["u1"]["count"] == 2
        assert svc._buffers["ch1"]["u2"]["count"] == 1


class TestStreamEvents:
    pytestmark = pytest.mark.asyncio

    async def test_on_stream_offline_ends_when_live(self):
        svc = _make_service()
        svc._active["ch1"] = 42
        svc.end_session = AsyncMock()
        await svc.on_stream_offline("ch1")
        svc.end_session.assert_awaited_once_with("ch1")

    async def test_on_stream_offline_noop_when_nothing(self):
        svc = _make_service()
        svc.end_session = AsyncMock()
        await svc.on_stream_offline("ch1")
        svc.end_session.assert_not_awaited()


class TestWatchTimeTokenFlow:
    pytestmark = pytest.mark.asyncio

    async def _run_one_iteration(self, svc):
        calls = 0

        async def _one_shot(_):
            nonlocal calls
            calls += 1
            if calls >= 2:
                raise asyncio.CancelledError()

        with patch("core.session_service.asyncio.sleep", new=_one_shot):
            with pytest.raises(asyncio.CancelledError):
                await svc._watch_time_loop()

    async def test_calls_fetch_chatters_per_active_channel(self):
        svc = _make_service()
        svc._active = {"ch1": 1}
        svc._fetch_chatters = AsyncMock(return_value=SimpleNamespace(viewers=[], complete=False))
        await self._run_one_iteration(svc)
        svc._fetch_chatters.assert_awaited_once_with("ch1")

    async def test_records_a_successful_empty_snapshot(self):
        analytics = _analytics()
        svc = _make_service(analytics=analytics)
        svc._active = {"ch1": 1}
        svc._fetch_chatters = AsyncMock(return_value=SimpleNamespace(viewers=[], complete=True))

        await self._run_one_iteration(svc)

        analytics.record_attendance_snapshot.assert_awaited_once_with(
            session_id=1,
            channel_id="ch1",
            viewers=[],
            seconds=svc._WATCH_INTERVAL,
        )

    async def test_does_not_record_an_incomplete_snapshot(self):
        analytics = _analytics()
        svc = _make_service(analytics=analytics)
        svc._active = {"ch1": 1}
        svc._fetch_chatters = AsyncMock(return_value=SimpleNamespace(viewers=[], complete=False))

        await self._run_one_iteration(svc)

        analytics.record_attendance_snapshot.assert_not_awaited()

    async def test_fetch_chatters_uses_bot_token_and_moderator_id(self):
        from shared.models.channel import Token

        channels = MagicMock()
        channels.get_token = AsyncMock(
            return_value=Token(user_id="bot-001", token="BOT_TOK", refresh="ref")
        )
        svc = _make_service(channels=channels)

        resp = MagicMock(status_code=200)
        resp.json.return_value = {"data": [], "pagination": {}}
        client = MagicMock()
        client.get = AsyncMock(return_value=resp)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("core.session_service.httpx.AsyncClient", return_value=ctx):
            snapshot = await svc._fetch_chatters("ch1")

        channels.get_token.assert_awaited_once_with("bot-001", "bot")
        assert snapshot.complete is True
        assert snapshot.viewers == []
        _, kwargs = client.get.call_args
        assert kwargs["params"]["moderator_id"] == "bot-001"
        assert kwargs["params"]["broadcaster_id"] == "ch1"
        assert kwargs["headers"]["Authorization"] == "Bearer BOT_TOK"

    async def test_fetch_chatters_empty_without_bot_token(self):
        channels = MagicMock()
        channels.get_token = AsyncMock(return_value=None)
        svc = _make_service(channels=channels)
        with patch("core.session_service.httpx.AsyncClient") as mock_client:
            snapshot = await svc._fetch_chatters("ch1")
        assert snapshot.complete is False
        assert snapshot.viewers == []
        mock_client.assert_not_called()

    async def test_fetch_chatters_discards_partial_pages_after_api_failure(self):
        from shared.models.channel import Token

        channels = MagicMock()
        channels.get_token = AsyncMock(
            return_value=Token(user_id="bot-001", token="BOT_TOK", refresh="ref")
        )
        svc = _make_service(channels=channels)

        first = MagicMock(status_code=200)
        first.json.return_value = {
            "data": [{"user_id": "u1", "user_login": "alice", "user_name": "Alice"}],
            "pagination": {"cursor": "next"},
        }
        second = MagicMock(status_code=503, text="unavailable")
        client = MagicMock()
        client.get = AsyncMock(side_effect=[first, second])
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("core.session_service.httpx.AsyncClient", return_value=ctx):
            snapshot = await svc._fetch_chatters("ch1")

        assert snapshot.complete is False
        assert snapshot.viewers == []
