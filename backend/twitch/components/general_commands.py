import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import twitchio
from twitchio.ext import commands

from core.component import BotComponent
from core.config import get_settings
from core.guards import check_command
from shared.repositories.command_config import CommandConfigRepository
from utils.substitution import substitute_variables

LOGGER: logging.Logger = logging.getLogger(__name__)

FRONTEND_URL = get_settings().frontend_url.rstrip("/")

# 依語氣由輕到重排列，slot = min(int(rank / total * 5), 4)
_RANK_TEMPLATES = [
    "每當點名你都在！能在 {total} 人中排到【第 {rank} 名】，這 {watch} 的陪伴加上 {messages} 則留言，絕對是真愛 GivePLZ ",  # 前 20%
    "不是吧，這也能卷？在 {total} 人中你硬是衝到【第 {rank} 名】！待了 {watch}、說了 {messages} 句話，我就問，你不用睡覺嗎？",  # 20–40%
    "這是真的嗎？從 {total} 人中殺出重圍奪下【第 {rank} 名】，坐了 {watch}、聊了 {messages} 句，你其實是機器人吧 MrDestructoid ",  # 40–60%
    "何意味？在 {total} 人中才排【第 {rank} 名】喔？才看 {watch} 加上這 {messages} 則留言，就繼續愛看不看吧，我沒關係啦真的😍",  # 60–80%
    "666 還有高手！你在 {total} 人中位居【第 {rank} 名】呢！累計待了 {watch}、貢獻 {messages} 則訊息，這數據想低調都難 MingLee",  # 後 20%
]

if TYPE_CHECKING:
    from core.bot import Bot


class GeneralCommandsComponent(BotComponent):
    """General user commands for the bot."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.cmd_repo = CommandConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.channel_repo = self.bot.channels  # type: ignore[attr-defined]

    def refresh_pool(self, pool) -> None:
        self.cmd_repo.pool = pool

    @property
    def _has_analytics(self) -> bool:
        return hasattr(self.bot, "_active_sessions") and hasattr(self.bot, "analytics")

    async def _record_command(self, ctx: commands.Context, command_name: str) -> None:
        # Session analytics gate is intentional — always increments usage_count but
        # only records to session when a stream is live. Do NOT remove the gate.
        try:
            channel_id = ctx.channel.id
            # Always increment all-time usage_count regardless of stream status
            await self.cmd_repo.increment_usage_count(channel_id, command_name)
            # Also record to session analytics if a stream is live (intentional gate)
            if self._has_analytics:
                session_id = self.bot._active_sessions.get(channel_id)
                if session_id:
                    analytics = self.bot.analytics
                    await analytics.record_command_usage(
                        session_id=session_id,
                        channel_id=channel_id,
                        command_name=f"!{command_name}",
                    )
        except Exception as e:
            LOGGER.error(f"Failed to record command usage: {e}")

    @commands.command(aliases=["alive"])
    async def ping(self, ctx: commands.Context) -> None:
        """Confirm the bot is alive.

        Usage: !ping, !alive
        """
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="ping"
        )
        if not config:
            return

        if config.custom_response:
            response = substitute_variables(
                config.custom_response, ctx.chatter, ctx.channel.name or "", ""
            )
            await self._ctx_reply(ctx, response)
        else:
            await self._ctx_reply(ctx, f"Pong! @{ctx.chatter.display_name}")
        await self._record_command(ctx, "ping")

    @commands.command(aliases=["commands", "指令"])
    async def help(self, ctx: commands.Context) -> None:
        """Show available commands.

        Usage: !help, !commands, !指令
        """
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="help"
        )
        if not config:
            return

        channel_name = ctx.channel.name
        await self._ctx_reply(ctx, f"指令列表： {FRONTEND_URL}/{channel_name}/commands")
        await self._record_command(ctx, "help")

    @commands.command(aliases=["開播時間"])
    async def uptime(self, ctx: commands.Context) -> None:
        """Show stream uptime.

        Usage: !uptime, !開播時間
        """
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="uptime"
        )
        if not config:
            return

        stream = None
        async for s in ctx.bot.fetch_streams(user_ids=[ctx.channel.id]):
            stream = s
            break

        if stream and stream.started_at:
            now = datetime.now(UTC)
            uptime = now - stream.started_at
            hours, remainder = divmod(int(uptime.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            await self._ctx_reply(ctx, f"已開播 {hours} 小時 {minutes} 分 {seconds} 秒")
        else:
            await self._ctx_reply(ctx, "目前未開播")

        await self._record_command(ctx, "uptime")

    @commands.command(name="condemn", aliases=["斥責"])
    async def condemn(self, ctx: commands.Context) -> None:
        """頻道反惡意言論聲明。

        Usage: !condemn, !斥責
        """
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="condemn"
        )
        if not config:
            return

        await self._ctx_reply(
            ctx,
            "本頻道實況主不認可並嚴厲斥責聊天室與斗內的任何惡意言論，"
            "包含且不限於種族歧視、性騷擾、色情暴力、涉及親屬等不當內容。",
        )
        await self._record_command(ctx, "condemn")

    @commands.command(aliases=["排名"])
    async def rank(self, ctx: commands.Context) -> None:
        """查詢本月個人活躍度排名。

        Usage: !rank, !排名
        """
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="rank"
        )
        if not config:
            return

        if not self._has_analytics:
            await self._ctx_reply(ctx, "排名資料暫時無法取得")
            return

        user_id = ctx.chatter.id
        channel_id = ctx.channel.id

        if user_id == channel_id:
            await self._ctx_reply(ctx, "你才是這裡的主人，哪有排名可言 👑")
            await self._record_command(ctx, "rank")
            return

        try:
            data = await self.bot.analytics.get_viewer_rank(channel_id, user_id)
        except Exception as e:
            LOGGER.error(f"Failed to get viewer rank for {user_id}: {e}")
            await self._ctx_reply(ctx, "排名查詢失敗，請稍後再試")
            return

        if data is None:
            await self._ctx_reply(ctx, "本月尚無活躍紀錄")
            await self._record_command(ctx, "rank")
            return

        total_mins = data["watch_seconds"] // 60
        hours, mins = divmod(total_mins, 60)
        days, hours = divmod(hours, 24)
        if days > 0:
            watch_str = f"{days}天{hours}小時{mins}分鐘"
        elif hours > 0:
            watch_str = f"{hours}小時{mins}分鐘"
        else:
            watch_str = f"{mins}分鐘"

        total = data["total_viewers"]
        slot = min(int(data["rank"] / total * 5), 4) if total > 0 else 2
        template = _RANK_TEMPLATES[slot]

        await self._ctx_reply(
            ctx,
            template.format(
                rank=data["rank"],
                total=data["total_viewers"],
                messages=data["total_messages"],
                watch=watch_str,
            ),
        )
        await self._record_command(ctx, "rank")

    @commands.Component.listener()
    async def event_stream_online(self, payload: twitchio.StreamOnline) -> None:
        LOGGER.info(f"[{payload.broadcaster.name}] Stream online")

        try:
            if not self._has_analytics:
                return

            channel_id = payload.broadcaster.id
            active_sessions = self.bot._active_sessions

            existing_session = active_sessions.get(channel_id)
            if existing_session:
                LOGGER.debug(
                    f"[{payload.broadcaster.name}] Stream online: session {existing_session} already active, skipping"
                )
                return

            if channel_id in self.bot._session_creating:
                LOGGER.debug(f"[{payload.broadcaster.name}] Session creation in-flight, skipping")
                return
            self.bot._session_creating.add(channel_id)
            try:
                stream = None
                for attempt in range(4):
                    async for s in self.bot.fetch_streams(user_ids=[channel_id]):
                        stream = s
                        break
                    if stream is not None:
                        break
                    if attempt < 3:
                        await asyncio.sleep(3)

                title = stream.title if stream else None
                game_name = stream.game_name if stream else None
                game_id = str(stream.game_id) if stream and stream.game_id else None
                started_at = (
                    stream.started_at if stream and stream.started_at else None
                ) or datetime.now(UTC)

                analytics = self.bot.analytics
                session_id = await analytics.create_session(
                    channel_id=channel_id,
                    started_at=started_at,
                    title=title,
                    game_name=game_name,
                    game_id=game_id,
                )
                active_sessions[channel_id] = session_id
                LOGGER.info(f"[{payload.broadcaster.name}] Session {session_id} created")
            finally:
                self.bot._session_creating.discard(channel_id)
        except Exception as e:
            LOGGER.error(f"[{payload.broadcaster.name}] Failed to create analytics session: {e}")

    @commands.Component.listener()
    async def event_stream_offline(self, payload: twitchio.StreamOffline) -> None:
        LOGGER.info(f"[{payload.broadcaster.name}] Stream offline")

        try:
            if not self._has_analytics:
                return

            channel_id = payload.broadcaster.id
            active_sessions = self.bot._active_sessions
            session_id = active_sessions.get(channel_id)

            if session_id:
                analytics = self.bot.analytics

                # Flush chatter stats buffer to database
                if hasattr(self.bot, "_channel_line_counts"):
                    self.bot._channel_line_counts.pop(channel_id, None)
                if hasattr(self.bot, "_chatter_buffers"):
                    chatter_data = self.bot._chatter_buffers.pop(channel_id, {})
                    if chatter_data:
                        try:
                            await analytics.flush_chatter_stats(
                                session_id=session_id,
                                channel_id=channel_id,
                                chatters=chatter_data,
                            )
                            LOGGER.info(
                                f"[{payload.broadcaster.name}] Flushed {len(chatter_data)} chatters for session {session_id}"
                            )
                        except Exception as e:
                            LOGGER.error(
                                f"[{payload.broadcaster.name}] Failed to flush chatter stats: {e}"
                            )

                ended_at = datetime.now(UTC)
                for attempt in range(3):
                    try:
                        await analytics.end_session(session_id, ended_at)
                        break
                    except Exception as e:
                        LOGGER.warning(
                            f"[{payload.broadcaster.name}] end_session attempt {attempt + 1}/3 failed: {e}"
                        )
                        if attempt < 2:
                            await asyncio.sleep(2)
                else:
                    LOGGER.error(
                        f"[{payload.broadcaster.name}] Failed to end session {session_id} after 3 attempts"
                    )
                del active_sessions[channel_id]
                LOGGER.info(f"[{payload.broadcaster.name}] Session {session_id} ended")
            else:
                LOGGER.warning(f"[{payload.broadcaster.name}] Stream offline: no active session")
        except Exception as e:
            LOGGER.error(f"[{payload.broadcaster.name}] Failed to end analytics session: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(GeneralCommandsComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
