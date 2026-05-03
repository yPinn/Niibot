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

    @commands.command(aliases=["hello", "hey"])
    async def hi(self, ctx: commands.Context) -> None:
        """Greet the user.

        Usage: !hi, !hello, !hey
        """
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="hi"
        )
        if not config:
            return

        if config.custom_response:
            response = substitute_variables(
                config.custom_response, ctx.chatter, ctx.channel.name or "", ""
            )
            await self._ctx_reply(ctx, response)
        else:
            await self._ctx_reply(ctx, f"你好，{ctx.chatter.display_name}！")
        await self._record_command(ctx, "hi")

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
        await self._ctx_reply(ctx, f"此頻道的指令列表： {FRONTEND_URL}/{channel_name}/commands")
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
            await self._ctx_reply(ctx, "目前無法查詢排名資料")
            return

        user_id = ctx.chatter.id
        channel_id = ctx.channel.id

        try:
            data = await self.bot.analytics.get_viewer_rank(channel_id, user_id)
        except Exception as e:
            LOGGER.error(f"Failed to get viewer rank for {user_id}: {e}")
            await self._ctx_reply(ctx, "查詢排名時發生錯誤，請稍後再試")
            return

        if data is None:
            await self._ctx_reply(ctx, f"@{ctx.chatter.display_name} 本月尚無活躍紀錄")
            await self._record_command(ctx, "rank")
            return

        hours, mins = divmod(data["watch_seconds"] // 60, 60)
        watch_str = f"{hours:02d}:{mins:02d}"
        streak_str = f"{data['streak_count']} 場" if data["streak_count"] > 0 else "—"

        await self._ctx_reply(
            ctx,
            f"@{ctx.chatter.display_name} 本月活躍排名：第 {data['rank']} 名 / {data['total_viewers']} 人"
            f" | 分數 {data['engagement_score']}"
            f" | 留言 {data['total_messages']}"
            f" | 觀看 {watch_str}"
            f" | 連續 {streak_str}",
        )
        await self._record_command(ctx, "rank")

    @commands.Component.listener()
    async def event_stream_online(self, payload: twitchio.StreamOnline) -> None:
        LOGGER.info(f"Stream online: {payload.broadcaster.name}")

        try:
            if not self._has_analytics:
                return

            channel_id = payload.broadcaster.id
            active_sessions = self.bot._active_sessions

            existing_session = active_sessions.get(channel_id)
            if existing_session:
                LOGGER.warning(
                    f"Channel {payload.broadcaster.name} already has active session {existing_session}, skipping"
                )
                return

            stream = None
            async for s in self.bot.fetch_streams(user_ids=[channel_id]):
                stream = s
                break

            title = stream.title if stream else None
            game_name = stream.game_name if stream else None
            game_id = str(stream.game_id) if stream and stream.game_id else None

            analytics = self.bot.analytics
            session_id = await analytics.create_session(
                channel_id=channel_id,
                started_at=datetime.now(UTC),
                title=title,
                game_name=game_name,
                game_id=game_id,
            )
            active_sessions[channel_id] = session_id
            LOGGER.info(
                f"Created analytics session {session_id} for channel {payload.broadcaster.name}"
            )
        except Exception as e:
            LOGGER.error(f"Failed to create analytics session: {e}")

    @commands.Component.listener()
    async def event_stream_offline(self, payload: twitchio.StreamOffline) -> None:
        LOGGER.info(f"Stream offline: {payload.broadcaster.name}")

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
                                f"Flushed {len(chatter_data)} chatters for session {session_id}"
                            )
                        except Exception as e:
                            LOGGER.error(f"Failed to flush chatter stats: {e}")

                ended_at = datetime.now(UTC)
                for attempt in range(3):
                    try:
                        await analytics.end_session(session_id, ended_at)
                        break
                    except Exception as e:
                        LOGGER.warning(f"end_session attempt {attempt + 1}/3 failed: {e}")
                        if attempt < 2:
                            await asyncio.sleep(2)
                else:
                    LOGGER.error(
                        f"Failed to end session {session_id} after 3 attempts, "
                        "stale session cleanup will handle it"
                    )
                del active_sessions[channel_id]
                LOGGER.info(
                    f"Ended analytics session {session_id} for channel {payload.broadcaster.name}"
                )
            else:
                LOGGER.warning(f"No active session found for channel {payload.broadcaster.name}")
        except Exception as e:
            LOGGER.error(f"Failed to end analytics session: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(GeneralCommandsComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
