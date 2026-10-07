"""Video Queue component: !vq, !np

Everyone:
    !vq              Usage hint (viewers are also told how to request with points)
    !vq list         Now playing + next 3 queued titles
    !vq remove [N]   Cancel your latest queued request, or your own entry #N
    !vq rules        The limits a viewer's request is held to
    !vq skip         Skip your own video while it is playing
    !np / !影片       Now playing — a catalog builtin (toggle/cooldown/role in dashboard)

Moderator+ (fixed, not configurable):
    !vq <URL>        Request a video (YouTube, Twitch Clip/VOD, Instagram Reel, Bilibili)
    !vq remove N     Cancel any entry #N
    !vq skip         Skip whatever is playing
    !vq clear        Clear entire queue (current + all queued)

Broadcaster only:
    !vq live <URL>   Live insert: play an ongoing Twitch / YouTube live stream
                     open-ended (background music, watch-along); pauses the queue
    !vq live stop    End the live insert and resume the queue

Chat requests stay moderator+ on purpose: viewers request through channel points
— the paid ladder is donation > channel points > free. Anything a viewer isn't
allowed to do is ignored silently, and every viewer `!vq` is throttled per user
so one person can't spend the bot's chat budget for the whole channel.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiohttp
import twitchio.ext.commands as commands

from core.component import BotComponent
from core.config import get_settings
from core.guards import check_command, has_role, try_acquire_cooldown
from shared.models.video_queue import VideoQueueEntry, VideoQueueSettings
from shared.repositories.command_config import (
    CommandConfigRepository,
    RedemptionConfigRepository,
)
from shared.repositories.video_queue import (
    VideoQueueBlocklistRepository,
    VideoQueueInsertRepository,
    VideoQueueRepository,
    VideoQueueSettingsRepository,
)
from shared.services.video_queue_admission import (
    AdmissionActor,
    AdmissionRejected,
    VideoQueueAdmissionService,
)
from shared.services.video_queue_insert import InsertRejected, VideoQueueInsertService
from shared.video_queue_messages import (
    INSERT_NONE,
    INSERT_STOPPED,
    INSERT_USAGE,
    IS_LIVE_HINT,
    NO_OWN_REQUEST,
    NOT_OWN_REQUEST,
    NOTHING_PLAYING,
    SKIP_RACED,
    UNAVAILABLE,
    accepted_message,
    cleared_message,
    insert_now_playing_message,
    insert_rejection_message,
    insert_started_message,
    no_such_position_message,
    now_playing_message,
    queue_list_message,
    rejection_message,
    removed_message,
    rules_message,
    skipped_message,
    usage_message,
)
from shared.video_sources import (
    UNPLAYABLE_LIVE,
    fetch_twitch_live_stream,
    fetch_video_metadata,
    fetch_yt_info,
    resolve_video_url,
)
from utils.command_input import parse_number

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)

# Per viewer, across every !vq subcommand: replies cost the bot's per-channel
# chat budget, so one viewer repeating a command must not drain it.
VIEWER_COOLDOWN_SECONDS = 5
# Per channel, for the read-only replies everyone sees the same answer to.
SHARED_REPLY_COOLDOWN_SECONDS = 10

# Sources whose requester is a real, identified viewer. Donation rows have no
# stable identity and dashboard rows are the broadcaster's own.
_SELF_SKIPPABLE_SOURCES = ("chat", "redemption")


class VideoQueueComponent(BotComponent):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self._settings = get_settings()
        self.vq_repo = VideoQueueRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.vq_settings_repo = VideoQueueSettingsRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.vq_blocklist_repo = VideoQueueBlocklistRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.cmd_repo = CommandConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.redemption_repo = RedemptionConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.vq_insert_repo = VideoQueueInsertRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.channel_repo = self.bot.channels  # type: ignore[attr-defined]
        self._session: aiohttp.ClientSession | None = None

    async def component_load(self) -> None:
        self._session = aiohttp.ClientSession()
        LOGGER.info("VideoQueue component loaded")

    async def component_teardown(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def refresh_pool(self, pool) -> None:
        self.vq_repo.pool = pool
        self.vq_settings_repo.pool = pool
        self.vq_blocklist_repo.pool = pool
        self.cmd_repo.pool = pool
        self.redemption_repo.pool = pool
        self.vq_insert_repo.pool = pool

    # ------------------------------------------------------------------
    # Roles and throttles
    # ------------------------------------------------------------------

    @staticmethod
    def _actor(ctx: commands.Context[Bot]) -> AdmissionActor:
        if ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            return "broadcaster"
        if has_role(ctx.chatter, "moderator"):
            return "moderator"
        return "viewer"

    @staticmethod
    def _is_moderator(ctx: commands.Context[Bot]) -> bool:
        return has_role(ctx.chatter, "moderator")

    def _viewer_throttled(self, ctx: commands.Context[Bot]) -> bool:
        """True when a viewer must be ignored for now; mods are never throttled."""
        if self._is_moderator(ctx):
            return False
        key = f"{ctx.channel.id}:vq:user:{ctx.chatter.id}"
        return not try_acquire_cooldown(key, VIEWER_COOLDOWN_SECONDS)

    def _shared_reply_throttled(self, ctx: commands.Context[Bot], name: str) -> bool:
        if self._is_moderator(ctx):
            return False
        key = f"{ctx.channel.id}:vq {name}"
        return not try_acquire_cooldown(key, SHARED_REPLY_COOLDOWN_SECONDS)

    @staticmethod
    def _is_requester(ctx: commands.Context[Bot], entry: VideoQueueEntry) -> bool:
        """Same identity rule as find_last_queued_by_user: id first, name for legacy rows."""
        user_id = str(ctx.chatter.id or "")
        if entry.requested_by_id is not None:
            return bool(user_id) and entry.requested_by_id == user_id
        user_name = ctx.chatter.display_name or ctx.chatter.name or ""
        return entry.requested_by == user_name

    @staticmethod
    def _can_self_skip(ctx: commands.Context[Bot], entry: VideoQueueEntry) -> bool:
        # Strictly by Twitch user id: display names change, and legacy rows
        # without an id can't be attributed safely.
        return (
            entry.source in _SELF_SKIPPABLE_SOURCES
            and entry.requested_by_id is not None
            and entry.requested_by_id == str(ctx.chatter.id or "")
        )

    async def _viewer_reward_name(
        self, channel_id: str, settings: VideoQueueSettings
    ) -> str | None:
        """Name of the channel-points reward viewers request with, if one is live."""
        if not (settings.enabled and settings.redemption_enabled):
            return None
        config = await self.redemption_repo.find_enabled_by_action(channel_id, "video_queue")
        return config.reward_name if config else None

    # ------------------------------------------------------------------
    # Request (moderator+)
    # ------------------------------------------------------------------

    async def _handle_add(self, ctx: commands.Context[Bot], url_str: str) -> None:
        """Core logic for adding a video to the queue."""
        try:
            await self._handle_add_inner(ctx, url_str)
        except Exception:
            # Do not copy a submitted URL into logs: query strings may contain
            # short-lived tokens or other user-provided data.
            LOGGER.exception("VideoQueue add failed", extra={"channel_id": ctx.channel.id})
            await self._ctx_reply(ctx, UNAVAILABLE)

    async def _handle_add_inner(self, ctx: commands.Context[Bot], url_str: str) -> None:
        """Inner implementation — separated so exceptions surface as a reply."""
        actor = self._actor(ctx)
        if actor == "viewer":
            return  # silent: viewers request through channel points

        channel_id = ctx.channel.id
        admission = VideoQueueAdmissionService(
            self.vq_repo, self.vq_settings_repo, self.vq_blocklist_repo
        )
        try:
            result = await admission.admit(
                channel_id=channel_id,
                url=url_str,
                requested_by=ctx.chatter.display_name or ctx.chatter.name or "",
                requested_by_id=ctx.chatter.id or None,
                source="chat",
                actor=actor,
                resolve=lambda url: resolve_video_url(url, session=self._session),
                fetch_metadata=lambda resolved: fetch_video_metadata(
                    resolved,
                    youtube_api_key=self._settings.youtube_api_key,
                    twitch_client_id=self._settings.twitch_client_id,
                    twitch_client_secret=self._settings.twitch_client_secret,
                    instafix_host=self._settings.instafix_host,
                    session=self._session,
                ),
            )
        except AdmissionRejected as error:
            message = rejection_message(error.reason, error.details)
            # Only the broadcaster can play a live stream — tell them how.
            if actor == "broadcaster" and error.details.get("unplayable_reason") == UNPLAYABLE_LIVE:
                message = IS_LIVE_HINT["chat"]
            await self._ctx_reply(ctx, message)
            return

        inserting = await self.vq_insert_repo.get_active(channel_id) is not None
        await self._ctx_reply(
            ctx,
            accepted_message(
                result.metadata.title,
                result.resolved.video_id,
                result.position,
                inserting=inserting,
            ),
        )

    # ------------------------------------------------------------------
    # !np
    # ------------------------------------------------------------------

    @commands.command(name="np", aliases=["影片"])
    async def cmd_np(self, ctx: commands.Context[Bot]) -> None:
        """!np / !影片 — 顯示當前播放影片資訊"""
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="np"
        )
        if not config:
            return
        current, _, insert = await self.vq_repo.get_stream_snapshot(ctx.channel.id)
        if insert is not None:
            message = insert_now_playing_message(insert)
        else:
            message = now_playing_message(current) if current else NOTHING_PLAYING
        await self._ctx_reply(ctx, message)
        try:
            await self.cmd_repo.increment_usage_count(ctx.channel.id, "np")
        except Exception as e:
            LOGGER.debug("usage count failed for np: %s", e)

    # ------------------------------------------------------------------
    # !vq — subcommand group
    # ------------------------------------------------------------------

    @commands.group(name="vq", invoke_fallback=True, case_insensitive=True)
    async def vq(self, ctx: commands.Context[Bot]) -> None:
        """!vq <URL> 投遞影片（Mod 以上）| !vq list/remove/rules/skip/clear"""
        if ctx.invoked_subcommand is not None:
            return
        args = (ctx.message.text if ctx.message else "").split(maxsplit=1)
        if len(args) > 1:
            await self._handle_add(ctx, args[1].strip())
            return

        if self._viewer_throttled(ctx):
            return
        is_moderator = self._is_moderator(ctx)
        reward_name = None
        if not is_moderator:
            settings = await self.vq_settings_repo.get_or_create(ctx.channel.id)
            reward_name = await self._viewer_reward_name(ctx.channel.id, settings)
        await self._ctx_reply(
            ctx, usage_message(is_moderator=is_moderator, reward_name=reward_name)
        )

    @vq.command(name="skip")
    async def vq_skip(self, ctx: commands.Context[Bot]) -> None:
        """!vq skip — Mod 以上跳過任何影片；點播者可跳過自己正在播放的影片"""
        if self._viewer_throttled(ctx):
            return
        channel_id = ctx.channel.id
        current = await self.vq_repo.get_current(channel_id)
        if not self._is_moderator(ctx) and (
            current is None or not self._can_self_skip(ctx, current)
        ):
            return  # silent
        if current is None:
            await self._ctx_reply(ctx, NOTHING_PLAYING)
            return

        # Conditional on the entry we just looked at: if the overlay advanced
        # meanwhile, skipping "whatever is playing" would end someone else's video.
        result = await self.vq_repo.skip_current_atomic(
            channel_id, expected_entry_id=current.id, end_reason="chat_skip"
        )
        await self._ctx_reply(
            ctx, skipped_message(result.next_entry) if result.skipped else SKIP_RACED
        )

    @vq.command(name="clear")
    async def vq_clear(self, ctx: commands.Context[Bot]) -> None:
        """!vq clear — 清空整個佇列（Mod 以上）"""
        if not self._is_moderator(ctx):
            return
        total = await self.vq_repo.clear_all_atomic(ctx.channel.id)
        await self._ctx_reply(ctx, cleared_message(total))

    @vq.command(name="list")
    async def vq_list(self, ctx: commands.Context[Bot]) -> None:
        """!vq list — 顯示現正播放與待播前 3 首（標題，不含投遞者；查投遞者用 !np）"""
        if self._viewer_throttled(ctx) or self._shared_reply_throttled(ctx, "list"):
            return
        current, queued, insert = await self.vq_repo.get_stream_snapshot(ctx.channel.id)
        await self._ctx_reply(ctx, queue_list_message(current, queued, insert))

    @vq.command(name="live")
    async def vq_live(self, ctx: commands.Context[Bot], *, args: str | None = None) -> None:
        """!vq live <URL> 播放直播 | !vq live stop 結束直播（限實況主）"""
        if not ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            return  # silent, like every other command a role can't use
        channel_id = ctx.channel.id
        raw = (args or "").strip()
        if not raw:
            insert = await self.vq_insert_repo.get_active(channel_id)
            await self._ctx_reply(
                ctx, insert_now_playing_message(insert) if insert else INSERT_USAGE
            )
            return
        if raw.lower() == "stop":
            stopped = await self.vq_insert_repo.stop(channel_id)
            await self._ctx_reply(ctx, INSERT_STOPPED if stopped else INSERT_NONE)
            return
        try:
            insert = await VideoQueueInsertService(
                self.vq_insert_repo, self.vq_settings_repo
            ).start(
                channel_id=channel_id,
                url=raw,
                fetch_youtube=lambda video_id: fetch_yt_info(
                    video_id, self._settings.youtube_api_key, self._session
                ),
                fetch_twitch_live=lambda login: fetch_twitch_live_stream(
                    login,
                    self._settings.twitch_client_id,
                    self._settings.twitch_client_secret,
                    self._session,
                ),
            )
        except InsertRejected as error:
            await self._ctx_reply(ctx, insert_rejection_message(error.reason))
            return
        except Exception:
            LOGGER.exception("VideoQueue live insert failed", extra={"channel_id": channel_id})
            await self._ctx_reply(ctx, UNAVAILABLE)
            return
        await self._ctx_reply(ctx, insert_started_message(insert))

    @vq.command(name="rules")
    async def vq_rules(self, ctx: commands.Context[Bot]) -> None:
        """!vq rules — 觀眾點播的方式與限制"""
        if self._viewer_throttled(ctx) or self._shared_reply_throttled(ctx, "rules"):
            return
        settings = await self.vq_settings_repo.get_or_create(ctx.channel.id)
        reward_name = await self._viewer_reward_name(ctx.channel.id, settings)
        await self._ctx_reply(ctx, rules_message(settings, reward_name))

    @vq.command(name="remove")
    async def vq_remove(self, ctx: commands.Context[Bot], *, args: str | None = None) -> None:
        """!vq remove [N] — 取消自己最後一首，或第 N 首（觀眾限自己點的；Mod 以上不限）"""
        if self._viewer_throttled(ctx):
            return
        channel_id = ctx.channel.id
        raw = (args or "").strip()

        if not raw:
            entry = await self.vq_repo.find_last_queued_by_user(
                channel_id,
                ctx.chatter.display_name or ctx.chatter.name or "",
                ctx.chatter.id or None,
            )
            if entry is None or not await self.vq_repo.cancel_queued(entry.id, channel_id):
                await self._ctx_reply(ctx, NO_OWN_REQUEST)
                return
            await self._ctx_reply(ctx, removed_message(entry))
            return

        # Same numbering as !vq list and the "第 N 首" in a request reply.
        position = parse_number(raw)
        if position is None or position < 1:
            return  # not a position; never echo free text back into chat
        queued = await self.vq_repo.get_queued(channel_id)
        if position > len(queued):
            await self._ctx_reply(ctx, no_such_position_message(position))
            return
        entry = queued[position - 1]
        if not self._is_moderator(ctx) and not self._is_requester(ctx, entry):
            await self._ctx_reply(ctx, NOT_OWN_REQUEST)
            return
        # Conditional on still being queued: if it started playing meanwhile,
        # cancelling must not end it (that's what skip is for).
        if not await self.vq_repo.cancel_queued(entry.id, channel_id):
            await self._ctx_reply(ctx, no_such_position_message(position))
            return
        await self._ctx_reply(ctx, removed_message(entry))


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(VideoQueueComponent(bot))


async def teardown(bot: commands.Bot) -> None:
    LOGGER.info("VideoQueue component unloaded")
