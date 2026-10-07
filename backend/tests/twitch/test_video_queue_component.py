"""Unit tests for the chat `!vq` / `!np` component.

Covers `VideoQueueComponent` (backend/twitch/components/video_queue.py):

- who may do what — requesting is fixed to moderator+, viewers are ignored
  silently; mods skip audience-fairness gates but not safety gates;
- `!vq remove [N]`, `!vq skip` (incl. a requester skipping their own video and
  the conditional-skip race), `!vq list`, `!vq rules`, the usage hint;
- the per-viewer throttle that keeps one viewer from draining the bot's chat
  budget.

Safety gates that need fetched metadata (global length cap and its best-effort
handling) must match the redemption and dashboard paths (see
test_channel_points_video_queue.py and test_video_queue_router.py).

Commands are invoked via `VideoQueueComponent.<command>.callback(component, ctx)`
to bypass the TwitchIO Command descriptor.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitch.components.video_queue import VideoQueueComponent

from core import guards
from shared.models.command_config import RedemptionConfig
from shared.models.video_queue import VideoQueueEntry, VideoQueueInsert, VideoQueueSettings
from shared.repositories.video_queue import SkipResult
from shared.video_sources import ResolvedVideo, TwitchLiveStream, VideoMetadata

CHANNEL_ID = "channel-1"


@pytest.fixture(autouse=True)
def _clear_throttles():
    guards._cooldown_tracker.clear()
    yield
    guards._cooldown_tracker.clear()


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.token_database = MagicMock()
    return bot


def _ctx(role: str = "moderator", *, user_id: str = "u-1", name: str = "Someone") -> MagicMock:
    ctx = MagicMock()
    ctx.channel.id = CHANNEL_ID
    ctx.chatter.broadcaster = role == "broadcaster"
    ctx.chatter.moderator = role == "moderator"
    ctx.chatter.vip = False
    ctx.chatter.subscriber = False
    ctx.chatter.display_name = name
    ctx.chatter.name = name.lower()
    ctx.chatter.id = user_id
    ctx.message.text = "!vq"
    ctx.invoked_subcommand = None
    return ctx


def _settings(**kw) -> VideoQueueSettings:
    return VideoQueueSettings(
        channel_id=CHANNEL_ID,
        enabled=kw.get("enabled", True),
        redemption_enabled=kw.get("redemption_enabled", True),
        max_duration_redemption=kw.get("max_duration_redemption", 600),
        min_view_count=kw.get("min_view_count", 0),
        max_duration_seconds=kw.get("max_duration_seconds", 0),
        max_queue_size=kw.get("max_queue_size", 20),
        max_per_user=kw.get("max_per_user", 0),
        user_cooldown_seconds=kw.get("user_cooldown_seconds", 0),
        replay_cooldown_hours=kw.get("replay_cooldown_hours", 0),
    )


def _entry(**kw) -> VideoQueueEntry:
    base = {
        "id": 1,
        "channel_id": CHANNEL_ID,
        "video_id": "vid123",
        "requested_by": "Someone",
        "requested_by_id": "u-1",
        "source": "chat",
        "status": "queued",
        "video_type": "youtube",
        "title": "T",
        "duration_seconds": None,
        "created_at": datetime.now(UTC),
    }
    return VideoQueueEntry(**{**base, **kw})


def _component(*, settings: VideoQueueSettings | None = None) -> VideoQueueComponent:
    component = VideoQueueComponent(_bot())
    component.vq_settings_repo.get_or_create = AsyncMock(return_value=settings or _settings())
    component.vq_repo.video_is_active = AsyncMock(return_value=False)
    component.vq_repo.get_queue_size = AsyncMock(return_value=1)
    component.vq_repo.count_active_by_user = AsyncMock(return_value=0)
    component.vq_repo.find_last_entry_by_user = AsyncMock(return_value=None)
    component.vq_repo.played_within = AsyncMock(return_value=False)
    component.vq_repo.add_if_within_limits = AsyncMock(return_value=_entry())
    component.vq_repo.add = AsyncMock(return_value=_entry(priority=30))
    component.vq_repo.get_queue_position = AsyncMock(return_value=2)
    component.vq_blocklist_repo.check = AsyncMock(return_value=None)
    component.redemption_repo.find_enabled_by_action = AsyncMock(return_value=None)
    component.vq_insert_repo.get_active = AsyncMock(return_value=None)
    component.vq_repo.get_stream_snapshot = AsyncMock(return_value=(None, [], None))
    component._ctx_reply = AsyncMock()  # type: ignore[method-assign]
    return component


def _patches(resolved: ResolvedVideo, metadata: VideoMetadata):
    return (
        patch("twitch.components.video_queue.resolve_video_url", AsyncMock(return_value=resolved)),
        patch(
            "twitch.components.video_queue.fetch_video_metadata",
            AsyncMock(return_value=metadata),
        ),
    )


def _reply(component: VideoQueueComponent) -> str:
    return component._ctx_reply.await_args.args[1]


def _reward(name: str = "點歌") -> RedemptionConfig:
    return RedemptionConfig(
        id=1, channel_id=CHANNEL_ID, action_type="video_queue", reward_name=name
    )


_YT = ResolvedVideo("youtube", "vid123", False)


@pytest.mark.asyncio
class TestChatAddSafetyGates:
    async def test_missing_duration_rejected_for_authoritative_source(self):
        component = _component(settings=_settings(max_duration_seconds=600))
        p1, p2 = _patches(_YT, VideoMetadata("YT", None, 5000, False))
        with p1, p2:
            await component._handle_add_inner(_ctx(), "https://youtube.com/watch?v=vid123")
        component.vq_repo.add_if_within_limits.assert_not_awaited()
        assert _reply(component) == "暫時無法點播，請稍後再試"

    async def test_missing_duration_allowed_for_best_effort_platform(self):
        component = _component(settings=_settings(max_duration_seconds=600))
        p1, p2 = _patches(
            ResolvedVideo("bilibili", "BV1FjxHzGEkQ", False),
            VideoMetadata("BV", None, None, False, metadata_best_effort=True),
        )
        with p1, p2:
            await component._handle_add_inner(_ctx(), "https://bilibili.com/video/BV1FjxHzGEkQ")
        component.vq_repo.add_if_within_limits.assert_awaited_once()

    async def test_known_duration_still_capped_for_best_effort_platform(self):
        component = _component(settings=_settings(max_duration_seconds=600))
        p1, p2 = _patches(
            ResolvedVideo("bilibili", "BV1x", False),
            VideoMetadata("BV", 9999, 5000, False, metadata_best_effort=True),
        )
        with p1, p2:
            await component._handle_add_inner(_ctx(), "https://bilibili.com/video/BV1x")
        component.vq_repo.add_if_within_limits.assert_not_awaited()
        assert _reply(component) == "影片長度請在 10 分鐘內，可指定片段，例：1:30-11:30"

    async def test_content_blocklist_still_applies_to_mods(self):
        component = _component()
        component.vq_blocklist_repo.check = AsyncMock(return_value=MagicMock())
        p1, p2 = _patches(_YT, VideoMetadata("YT", 90, 5000, False))
        with p1, p2:
            await component._handle_add_inner(_ctx(), "https://youtu.be/vid123")
        component.vq_repo.add_if_within_limits.assert_not_awaited()
        assert _reply(component) == "抱歉，這部影片無法點播"


@pytest.mark.asyncio
class TestChatAddRoles:
    async def test_viewer_request_is_ignored_silently(self):
        component = _component()
        p1, p2 = _patches(_YT, VideoMetadata("YT", 90, 5000, False))
        with p1, p2:
            await component._handle_add_inner(_ctx("viewer"), "https://youtu.be/vid123")
        component.vq_repo.add_if_within_limits.assert_not_awaited()
        component._ctx_reply.assert_not_awaited()

    async def test_mod_skips_fairness_gates(self):
        component = _component(
            settings=_settings(min_view_count=1_000_000, max_per_user=1, user_cooldown_seconds=600)
        )
        component.vq_repo.count_active_by_user = AsyncMock(return_value=5)
        component.vq_repo.played_within = AsyncMock(return_value=True)
        p1, p2 = _patches(_YT, VideoMetadata("YT", 90, 10, False))
        with p1, p2:
            await component._handle_add_inner(_ctx(), "https://youtu.be/vid123")
        component.vq_repo.add_if_within_limits.assert_awaited_once()
        kwargs = component.vq_repo.add_if_within_limits.await_args.kwargs
        assert kwargs["priority"] == 0  # no queue jumping
        assert kwargs["max_per_user"] == 0
        assert _reply(component) == "「YT」已加入待播，第 2 首 SeemsGood"

    async def test_mod_still_respects_queue_capacity(self):
        component = _component(settings=_settings(max_queue_size=1))
        component.vq_repo.get_queue_size = AsyncMock(return_value=1)
        p1, p2 = _patches(_YT, VideoMetadata("YT", 90, 5000, False))
        with p1, p2:
            await component._handle_add_inner(_ctx(), "https://youtu.be/vid123")
        component.vq_repo.add_if_within_limits.assert_not_awaited()
        assert _reply(component) == "待播已滿，請稍後再試"

    async def test_broadcaster_bypasses_capacity_and_queues_like_dashboard(self):
        component = _component(settings=_settings(max_queue_size=1))
        component.vq_repo.get_queue_size = AsyncMock(return_value=1)
        p1, p2 = _patches(_YT, VideoMetadata("YT", 90, 5000, False))
        with p1, p2:
            await component._handle_add_inner(_ctx("broadcaster"), "https://youtu.be/vid123")
        component.vq_repo.add.assert_awaited_once()
        assert component.vq_repo.add.await_args.kwargs["priority"] == 30
        assert component.vq_repo.add.await_args.kwargs["source"] == "chat"

    async def test_live_stream_is_rejected_with_its_own_message(self):
        component = _component()
        p1, p2 = _patches(
            _YT, VideoMetadata("Live", None, None, False, playable=False, unplayable_reason="live")
        )
        with p1, p2:
            await component._handle_add_inner(_ctx(), "https://youtube.com/live/vid123")
        component.vq_repo.add_if_within_limits.assert_not_awaited()
        assert _reply(component) == "直播進行中無法點播，結束後可點播重播"


@pytest.mark.asyncio
class TestUsageAndRules:
    async def test_viewer_usage_points_to_the_reward(self):
        component = _component()
        component.redemption_repo.find_enabled_by_action = AsyncMock(return_value=_reward())
        await VideoQueueComponent.vq.callback(component, _ctx("viewer"))  # type: ignore[attr-defined]
        assert _reply(component) == "點播請兌換「點歌」 | !vq list | !vq remove | !vq rules | !np"

    async def test_viewer_usage_without_reward_hides_the_guidance(self):
        component = _component(settings=_settings(redemption_enabled=False))
        await VideoQueueComponent.vq.callback(component, _ctx("viewer"))  # type: ignore[attr-defined]
        assert _reply(component) == "用法：!vq list | !vq remove | !vq rules | !np"
        component.redemption_repo.find_enabled_by_action.assert_not_awaited()

    async def test_mod_usage_lists_management_commands(self):
        component = _component()
        await VideoQueueComponent.vq.callback(component, _ctx())  # type: ignore[attr-defined]
        assert _reply(component) == "用法：!vq <網址> | list | remove | skip | clear | rules"

    async def test_rules_list_only_enabled_limits(self):
        component = _component(
            settings=_settings(max_duration_seconds=0, max_duration_redemption=600, max_per_user=3)
        )
        component.redemption_repo.find_enabled_by_action = AsyncMock(return_value=_reward())
        await VideoQueueComponent.vq_rules.callback(component, _ctx("viewer"))  # type: ignore[attr-defined]
        assert _reply(component) == (
            "兌換「點歌」點播 | 可指定片段：網址 1:30-4:00 | 長度 10 分鐘內 | 每人 3 首"
        )

    async def test_rules_without_reward(self):
        component = _component()
        await VideoQueueComponent.vq_rules.callback(component, _ctx("viewer"))  # type: ignore[attr-defined]
        assert _reply(component) == "目前不開放觀眾點播"


@pytest.mark.asyncio
class TestThrottles:
    async def test_viewer_repeat_is_silent(self):
        component = _component()
        ctx = _ctx("viewer")
        await VideoQueueComponent.vq.callback(component, ctx)  # type: ignore[attr-defined]
        await VideoQueueComponent.vq.callback(component, ctx)  # type: ignore[attr-defined]
        assert component._ctx_reply.await_count == 1

    async def test_throttle_is_per_viewer(self):
        component = _component()
        await VideoQueueComponent.vq.callback(component, _ctx("viewer", user_id="a"))  # type: ignore[attr-defined]
        await VideoQueueComponent.vq.callback(component, _ctx("viewer", user_id="b"))  # type: ignore[attr-defined]
        assert component._ctx_reply.await_count == 2

    async def test_list_is_shared_across_viewers(self):
        component = _component()
        await VideoQueueComponent.vq_list.callback(component, _ctx("viewer", user_id="a"))  # type: ignore[attr-defined]
        await VideoQueueComponent.vq_list.callback(component, _ctx("viewer", user_id="b"))  # type: ignore[attr-defined]
        assert component._ctx_reply.await_count == 1

    async def test_mods_are_never_throttled(self):
        component = _component()
        for _ in range(3):
            await VideoQueueComponent.vq_list.callback(component, _ctx())  # type: ignore[attr-defined]
        assert component._ctx_reply.await_count == 3


@pytest.mark.asyncio
class TestRemove:
    async def test_without_argument_cancels_own_latest(self):
        component = _component()
        component.vq_repo.find_last_queued_by_user = AsyncMock(return_value=_entry(title="Mine"))
        component.vq_repo.cancel_queued = AsyncMock(return_value=True)
        await VideoQueueComponent.vq_remove.callback(component, _ctx("viewer"))  # type: ignore[attr-defined]
        assert _reply(component) == "已取消「Mine」"

    async def test_without_request(self):
        component = _component()
        component.vq_repo.find_last_queued_by_user = AsyncMock(return_value=None)
        await VideoQueueComponent.vq_remove.callback(component, _ctx("viewer"))  # type: ignore[attr-defined]
        assert _reply(component) == "你目前沒有待播中的點播"

    async def test_viewer_can_cancel_own_entry_by_position(self):
        component = _component()
        queued = [_entry(id=1, requested_by_id="x"), _entry(id=2, title="Mine")]
        component.vq_repo.get_queued = AsyncMock(return_value=queued)
        component.vq_repo.cancel_queued = AsyncMock(return_value=True)
        await VideoQueueComponent.vq_remove.callback(component, _ctx("viewer"), args="2")  # type: ignore[attr-defined]
        component.vq_repo.cancel_queued.assert_awaited_once_with(2, CHANNEL_ID)
        assert _reply(component) == "已取消「Mine」"

    async def test_viewer_cannot_cancel_someone_elses_entry(self):
        component = _component()
        component.vq_repo.get_queued = AsyncMock(return_value=[_entry(requested_by_id="x")])
        component.vq_repo.cancel_queued = AsyncMock()
        await VideoQueueComponent.vq_remove.callback(component, _ctx("viewer"), args="1")  # type: ignore[attr-defined]
        component.vq_repo.cancel_queued.assert_not_awaited()
        assert _reply(component) == "只能取消自己點的影片"

    async def test_mod_can_cancel_any_entry(self):
        component = _component()
        component.vq_repo.get_queued = AsyncMock(return_value=[_entry(requested_by_id="x")])
        component.vq_repo.cancel_queued = AsyncMock(return_value=True)
        await VideoQueueComponent.vq_remove.callback(component, _ctx(), args="1")  # type: ignore[attr-defined]
        component.vq_repo.cancel_queued.assert_awaited_once()

    async def test_position_out_of_range(self):
        component = _component()
        component.vq_repo.get_queued = AsyncMock(return_value=[_entry()])
        await VideoQueueComponent.vq_remove.callback(component, _ctx(), args="5")  # type: ignore[attr-defined]
        assert _reply(component) == "沒有第 5 首"

    async def test_entry_that_started_playing_is_not_cancelled(self):
        component = _component()
        component.vq_repo.get_queued = AsyncMock(return_value=[_entry()])
        component.vq_repo.cancel_queued = AsyncMock(return_value=False)
        await VideoQueueComponent.vq_remove.callback(component, _ctx(), args="1")  # type: ignore[attr-defined]
        assert _reply(component) == "沒有第 1 首"

    async def test_free_text_is_ignored(self):
        component = _component()
        component.vq_repo.get_queued = AsyncMock()
        await VideoQueueComponent.vq_remove.callback(component, _ctx(), args="please")  # type: ignore[attr-defined]
        component.vq_repo.get_queued.assert_not_awaited()
        component._ctx_reply.assert_not_awaited()


@pytest.mark.asyncio
class TestSkip:
    async def test_mod_skip_is_conditional_on_the_entry_looked_up(self):
        component = _component()
        component.vq_repo.get_current = AsyncMock(return_value=_entry(id=7, status="playing"))
        component.vq_repo.skip_current_atomic = AsyncMock(
            return_value=SkipResult(True, _entry(id=8, title="Next"))
        )
        await VideoQueueComponent.vq_skip.callback(component, _ctx())  # type: ignore[attr-defined]
        component.vq_repo.skip_current_atomic.assert_awaited_once_with(
            CHANNEL_ID, expected_entry_id=7, end_reason="chat_skip"
        )
        assert _reply(component) == "已跳過，下一首「Next」"

    async def test_skip_with_empty_queue(self):
        component = _component()
        component.vq_repo.get_current = AsyncMock(return_value=_entry(status="playing"))
        component.vq_repo.skip_current_atomic = AsyncMock(return_value=SkipResult(True, None))
        await VideoQueueComponent.vq_skip.callback(component, _ctx())  # type: ignore[attr-defined]
        assert _reply(component) == "已跳過，待播已空"

    async def test_skip_raced_with_overlay_advance(self):
        component = _component()
        component.vq_repo.get_current = AsyncMock(return_value=_entry(status="playing"))
        component.vq_repo.skip_current_atomic = AsyncMock(return_value=SkipResult(False))
        await VideoQueueComponent.vq_skip.callback(component, _ctx())  # type: ignore[attr-defined]
        assert _reply(component) == "影片已換，未跳過"

    async def test_mod_skip_with_nothing_playing(self):
        component = _component()
        component.vq_repo.get_current = AsyncMock(return_value=None)
        await VideoQueueComponent.vq_skip.callback(component, _ctx())  # type: ignore[attr-defined]
        assert _reply(component) == "目前沒有播放中的影片"

    async def test_requester_can_skip_own_playing_video(self):
        component = _component()
        component.vq_repo.get_current = AsyncMock(
            return_value=_entry(status="playing", source="redemption", requested_by_id="u-1")
        )
        component.vq_repo.skip_current_atomic = AsyncMock(return_value=SkipResult(True, None))
        await VideoQueueComponent.vq_skip.callback(component, _ctx("viewer", user_id="u-1"))  # type: ignore[attr-defined]
        component.vq_repo.skip_current_atomic.assert_awaited_once()

    @pytest.mark.parametrize(
        "entry_kw",
        [
            {"requested_by_id": "someone-else"},
            {"requested_by_id": None},  # legacy row: never attributed by name
            {"source": "dashboard"},
            {"source": "donation"},
        ],
    )
    async def test_viewer_cannot_skip_other_videos(self, entry_kw):
        component = _component()
        component.vq_repo.get_current = AsyncMock(
            return_value=_entry(**{"status": "playing", "requested_by_id": "u-1", **entry_kw})
        )
        component.vq_repo.skip_current_atomic = AsyncMock()
        await VideoQueueComponent.vq_skip.callback(component, _ctx("viewer", user_id="u-1"))  # type: ignore[attr-defined]
        component.vq_repo.skip_current_atomic.assert_not_awaited()
        component._ctx_reply.assert_not_awaited()


@pytest.mark.asyncio
class TestClearAndNowPlaying:
    async def test_viewer_clear_is_silent(self):
        component = _component()
        component.vq_repo.clear_all_atomic = AsyncMock()
        await VideoQueueComponent.vq_clear.callback(component, _ctx("viewer"))  # type: ignore[attr-defined]
        component.vq_repo.clear_all_atomic.assert_not_awaited()
        component._ctx_reply.assert_not_awaited()

    async def test_clear_reports_count(self):
        component = _component()
        component.vq_repo.clear_all_atomic = AsyncMock(return_value=4)
        await VideoQueueComponent.vq_clear.callback(component, _ctx())  # type: ignore[attr-defined]
        assert _reply(component) == "已清空 4 首"

    async def test_np_respects_the_builtin_config(self):
        component = _component()
        with patch("twitch.components.video_queue.check_command", AsyncMock(return_value=None)):
            await VideoQueueComponent.cmd_np.callback(component, _ctx("viewer"))  # type: ignore[attr-defined]
        component.vq_repo.get_stream_snapshot.assert_not_awaited()
        component._ctx_reply.assert_not_awaited()

    async def test_np_replies_with_now_playing(self):
        component = _component()
        component.vq_repo.get_stream_snapshot = AsyncMock(
            return_value=(_entry(status="playing", title="Song", requested_by="Bob"), [], None)
        )
        component.cmd_repo.increment_usage_count = AsyncMock()
        with patch(
            "twitch.components.video_queue.check_command", AsyncMock(return_value=MagicMock())
        ):
            await VideoQueueComponent.cmd_np.callback(component, _ctx("viewer"))  # type: ignore[attr-defined]
        assert _reply(component) == "▶「Song」 https://youtu.be/vid123 | 點播：Bob"


def _insert(**kw) -> VideoQueueInsert:
    base = {
        "id": 5,
        "channel_id": CHANNEL_ID,
        "source_type": "twitch_live",
        "source_id": "lofistreamer",
        "volume_percent": 30,
        "title": "beats to relax to",
        "creator_name": "LofiStreamer",
    }
    return VideoQueueInsert(**{**base, **kw})


@pytest.mark.asyncio
class TestLiveInsert:
    async def test_only_the_broadcaster_can_insert(self):
        component = _component()
        component.vq_insert_repo.start = AsyncMock()
        for role in ("viewer", "moderator"):
            await VideoQueueComponent.vq_live.callback(  # type: ignore[attr-defined]
                component, _ctx(role), args="https://www.twitch.tv/lofistreamer"
            )
        component.vq_insert_repo.start.assert_not_awaited()
        component._ctx_reply.assert_not_awaited()

    async def test_broadcaster_starts_a_twitch_insert(self):
        component = _component(settings=_settings())
        component.vq_insert_repo.start = AsyncMock(return_value=_insert())
        live = TwitchLiveStream("u-9", "lofistreamer", "LofiStreamer", "beats")
        with patch(
            "twitch.components.video_queue.fetch_twitch_live_stream",
            AsyncMock(return_value=live),
        ):
            await VideoQueueComponent.vq_live.callback(  # type: ignore[attr-defined]
                component, _ctx("broadcaster"), args="https://www.twitch.tv/LofiStreamer"
            )
        kwargs = component.vq_insert_repo.start.await_args.kwargs
        assert (kwargs["source_type"], kwargs["source_id"]) == ("twitch_live", "lofistreamer")
        assert kwargs["volume_percent"] == 50  # the shared volume (default)
        assert _reply(component) == "開始播放 LofiStreamer 的直播，佇列暫停"

    async def test_offline_channel_is_rejected(self):
        component = _component()
        component.vq_insert_repo.start = AsyncMock()
        with patch(
            "twitch.components.video_queue.fetch_twitch_live_stream",
            AsyncMock(return_value=None),
        ):
            await VideoQueueComponent.vq_live.callback(  # type: ignore[attr-defined]
                component, _ctx("broadcaster"), args="https://www.twitch.tv/someone"
            )
        component.vq_insert_repo.start.assert_not_awaited()
        assert _reply(component) == "目前沒有進行中的直播"

    async def test_stop(self):
        component = _component()
        component.vq_insert_repo.stop = AsyncMock(return_value=True)
        await VideoQueueComponent.vq_live.callback(component, _ctx("broadcaster"), args="STOP")  # type: ignore[attr-defined]
        assert _reply(component) == "已結束直播，恢復播放佇列"
        component.vq_insert_repo.stop = AsyncMock(return_value=False)
        await VideoQueueComponent.vq_live.callback(component, _ctx("broadcaster"), args="stop")  # type: ignore[attr-defined]
        assert _reply(component) == "目前沒有播放直播"

    async def test_np_shows_the_insert(self):
        component = _component()
        component.vq_repo.get_stream_snapshot = AsyncMock(return_value=(None, [], _insert()))
        component.cmd_repo.increment_usage_count = AsyncMock()
        with patch(
            "twitch.components.video_queue.check_command", AsyncMock(return_value=MagicMock())
        ):
            await VideoQueueComponent.cmd_np.callback(component, _ctx("viewer"))  # type: ignore[attr-defined]
        assert _reply(component) == (
            "直播中：LofiStreamer「beats to relax to」 https://www.twitch.tv/lofistreamer"
        )

    async def test_requests_during_an_insert_say_when_they_play(self):
        component = _component()
        component.vq_insert_repo.get_active = AsyncMock(return_value=_insert())
        p1, p2 = _patches(_YT, VideoMetadata("YT", 90, 5000, False))
        with p1, p2:
            await component._handle_add_inner(_ctx(), "https://youtu.be/vid123")
        assert "（直播結束後播放）" in _reply(component)


@pytest.mark.asyncio
async def test_live_url_as_a_request_tells_the_broadcaster_about_vq_live():
    component = _component()
    live = VideoMetadata("Live", None, 10, False, playable=False, unplayable_reason="live")
    p1, p2 = _patches(_YT, live)
    with p1, p2:
        await component._handle_add_inner(_ctx("broadcaster"), "https://youtu.be/vid123")
    assert _reply(component) == "這是進行中的直播，請用 !vq live <網址> 播放"

    # A mod can't play live streams, so the plain rejection stays.
    with p1, p2:
        await component._handle_add_inner(_ctx("moderator"), "https://youtu.be/vid123")
    assert _reply(component) == "直播進行中無法點播，結束後可點播重播"
