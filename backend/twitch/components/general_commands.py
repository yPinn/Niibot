import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from twitchio.ext import commands

from core.component import BotComponent
from core.config import get_settings
from core.guards import check_command
from shared.repositories.command_config import CommandConfigRepository
from utils.substitution import substitute_variables

LOGGER: logging.Logger = logging.getLogger(__name__)

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

    async def _record_command(self, ctx: commands.Context, command_name: str) -> None:
        # Session analytics gate is intentional — always increments usage_count but
        # only records to session when a stream is live. Do NOT remove the gate.
        try:
            channel_id = ctx.channel.id
            # Always increment all-time usage_count regardless of stream status
            await self.cmd_repo.increment_usage_count(channel_id, command_name)
            # Also record to session analytics if a stream is live (intentional gate)
            session_id = self.bot.sessions.session_id(channel_id)
            if session_id:
                await self.bot.analytics.record_command_usage(
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
                config.custom_response,
                ctx.chatter,
                ctx.channel.name or "",
                "",
                count=config.usage_count + 1,
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
        frontend_url = get_settings().frontend_url.rstrip("/")
        await self._ctx_reply(ctx, f"指令列表： {frontend_url}/{channel_name}/commands")
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

    @commands.command(name="del", aliases=["刪除", "vanish"])
    async def delete_own_messages(self, ctx: commands.Context) -> None:
        """清除自己最近的聊天室留言（等同自我 timeout 1 秒）。用法: !del

        Uses the bot token (moderator:manage:banned_users) — the bot must be a
        mod. Silent on failure (bot not mod, or Twitch rejects the call):
        this is viewer-triggered, so a visible error on every miss would spam
        chat for a problem only the broadcaster can fix.
        """
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="del"
        )
        if not config:
            return

        channel_id = ctx.channel.id
        if ctx.chatter.broadcaster:
            await self._ctx_reply(ctx, "實況主不能對自己這麼做啦")
            return

        if channel_id not in self.bot._bot_is_mod:  # type: ignore[attr-defined]
            LOGGER.warning(f"[{ctx.channel.name}] !del: bot is not mod, cannot timeout")
            return

        try:
            await ctx.broadcaster.timeout_user(
                moderator=ctx.bot.sender_for(channel_id),
                user=ctx.chatter.id,
                duration=1,
                reason="!del 自助清除留言",
            )
        except Exception as e:
            LOGGER.warning(f"[{ctx.channel.name}] !del failed: {e}")
            return
        await self._record_command(ctx, "del")

    @commands.command(name="so", aliases=["推薦"])
    async def shoutout(self, ctx: commands.Context, *, target: str | None = None) -> None:
        """版主指令：推薦另一個頻道。用法: !so <頻道名>

        Uses the bot token (moderator:manage:shoutouts) — the bot must be a mod.
        Twitch rate-limits shoutouts to one per 2 min / one per target per 60 min.
        """
        # Gated by min_role="moderator" (BUILTIN_DEFS); check_command enforces it.
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="so"
        )
        if not config:
            return

        login = (target or "").strip().lstrip("@").lower()
        if not login:
            await self._ctx_reply(ctx, "用法： !so <頻道名>")
            return

        channel_id = ctx.channel.id
        try:
            users = await ctx.bot.fetch_users(logins=[login])
        except Exception as e:
            LOGGER.warning(f"[{ctx.channel.name}] !so fetch_users failed: {e}")
            await self._ctx_reply(ctx, "查詢頻道失敗，請稍後再試")
            return

        if not users:
            await self._ctx_reply(ctx, f"找不到頻道 {login}")
            return
        target_user = users[0]

        if target_user.id == channel_id:
            await self._ctx_reply(ctx, "不能推薦自己啦 KappaPride")
            return

        try:
            await ctx.broadcaster.send_shoutout(
                to_broadcaster=target_user,
                moderator=ctx.bot.sender_for(channel_id),
            )
            LOGGER.info(f"[{ctx.channel.name}] !so → {login} by {ctx.chatter.name}")
            await self._record_command(ctx, "so")
        except Exception as e:
            status = getattr(e, "status", None) or getattr(e, "status_code", None)
            if status == 429:
                await self._ctx_reply(ctx, "推薦太頻繁了，請稍後再試（每 2 分鐘一次）")
            else:
                LOGGER.error(f"[{ctx.channel.name}] !so failed: {e}")
                await self._ctx_reply(ctx, "推薦失敗，請確認機器人是否為版主")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(GeneralCommandsComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
