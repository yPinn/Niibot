"""Game queue management commands: !gq

Public:
    !gq         Show queue overview (next match + total)
    !gq me      Show personal queue position and teammates

Moderator+:
    !gq next    Advance to next batch
    !gq kick @user  Remove a user from the queue
    !gq clear   Clear entire queue
    !gq open    Enable queue
    !gq close   Disable queue
    !gq size N  Change group size
"""

import logging
from typing import TYPE_CHECKING

from twitchio.ext import commands

from shared.repositories.game_queue import GameQueueRepository, GameQueueSettingsRepository

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)


class GameQueueComponent(commands.Component):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.gq_repo = GameQueueRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.gq_settings_repo = GameQueueSettingsRepository(self.bot.token_database)  # type: ignore[attr-defined]

    def refresh_pool(self, pool) -> None:
        self.gq_repo.pool = pool
        self.gq_settings_repo.pool = pool

    def _compute_batches(self, entries: list, group_size: int) -> list[list]:
        """Split entries into batches.

        group_size is the total team size including the broadcaster.
        The queue contributes pull_size = max(1, group_size - 1) players per batch.
        """
        pull_size = max(1, group_size - 1)
        return [entries[i : i + pull_size] for i in range(0, len(entries), pull_size)]

    @commands.group(name="gq")
    async def gq(self, ctx: commands.Context["Bot"]) -> None:
        """Game queue commands."""
        if ctx.invoked_subcommand is not None:
            return

        # !gq — show queue overview (available to everyone)
        channel_id = ctx.channel.id
        settings = await self.gq_settings_repo.get_or_create(channel_id)
        entries = await self.gq_repo.get_active_entries(channel_id)

        status = "開" if settings.enabled else "關"
        total = len(entries)

        if total == 0:
            await ctx.reply(f"[{status}] 無人排隊 | !gq me 查詢自己")
            return

        batches = self._compute_batches(entries, settings.group_size)
        next_names = ", ".join(e.user_name for e in batches[0])
        await ctx.reply(f"[{status}] 下一場: {next_names} | 共{total}人排隊 | !gq me 查詢自己")

    @gq.command(name="me", aliases=["pos", "status"])
    async def gq_me(self, ctx: commands.Context["Bot"]) -> None:
        """Check personal queue position."""
        channel_id = ctx.channel.id
        user_id = ctx.chatter.id

        entries = await self.gq_repo.get_active_entries(channel_id)
        settings = await self.gq_settings_repo.get_or_create(channel_id)

        user_index = next((i for i, e in enumerate(entries) if e.user_id == user_id), None)

        if user_index is None:
            await ctx.reply("未排隊 | !gq 查看隊列")
            return

        pull_size = max(1, settings.group_size - 1)
        batch_num = (user_index // pull_size) + 1
        batch_start = (batch_num - 1) * pull_size
        batch_end = batch_start + pull_size
        teammates = [
            e.user_name
            for i, e in enumerate(entries[batch_start:batch_end])
            if (batch_start + i) != user_index
        ]
        teammates_str = ", ".join(teammates) if teammates else "無"
        ahead = batch_num - 1

        msg = f"第{batch_num}場 | 同場: {teammates_str}"
        if ahead > 0:
            msg += f" | 前方{ahead}場"
        await ctx.reply(msg)

    @gq.command(name="next")
    async def gq_next(self, ctx: commands.Context["Bot"]) -> None:
        """Advance to next batch (mod+)."""
        if not (ctx.chatter.moderator or ctx.chatter.broadcaster):  # type: ignore[attr-defined]
            return

        channel_id = ctx.channel.id
        settings = await self.gq_settings_repo.get_or_create(channel_id)
        entries = await self.gq_repo.get_active_entries(channel_id)

        pull_size = max(1, settings.group_size - 1)
        to_complete = entries[:pull_size]
        if not to_complete:
            await ctx.reply("隊列為空")
            return

        entry_ids = [e.id for e in to_complete]
        await self.gq_repo.complete_batch(channel_id, entry_ids)

        remaining = entries[pull_size:]
        if remaining:
            next_batch = remaining[:pull_size]
            next_names = ", ".join(e.user_name for e in next_batch)
            await ctx.reply(f"已結算 | 下一場: {next_names}")
        else:
            await ctx.reply("已結算 | 隊列清空")

    @gq.command(name="kick")
    async def gq_kick(self, ctx: commands.Context["Bot"], *, args: str | None = None) -> None:
        """Kick a user from queue (mod+)."""
        if not (ctx.chatter.moderator or ctx.chatter.broadcaster):  # type: ignore[attr-defined]
            return

        if not args or not args.strip():
            await ctx.reply("!gq kick @username")
            return

        target_name = args.strip().lstrip("@").lower()
        channel_id = ctx.channel.id

        # Find user by name in active entries
        entries = await self.gq_repo.get_active_entries(channel_id)
        target = next((e for e in entries if e.user_name.lower() == target_name), None)

        if not target:
            await ctx.reply(f"找不到 {target_name}")
            return

        await self.gq_repo.remove_entry(target.id, channel_id, "kicked")
        await ctx.reply(f"已移除 {target.user_name}")

    @gq.command(name="clear")
    async def gq_clear(self, ctx: commands.Context["Bot"]) -> None:
        """Clear entire queue (mod+)."""
        if not (ctx.chatter.moderator or ctx.chatter.broadcaster):  # type: ignore[attr-defined]
            return

        channel_id = ctx.channel.id
        cleared = await self.gq_repo.clear_queue(channel_id)
        await ctx.reply(f"已清空（{cleared} 人）")

    @gq.command(name="open")
    async def gq_open(self, ctx: commands.Context["Bot"]) -> None:
        """Enable queue (mod+)."""
        if not (ctx.chatter.moderator or ctx.chatter.broadcaster):  # type: ignore[attr-defined]
            return

        channel_id = ctx.channel.id
        await self.gq_settings_repo.update_settings(channel_id, enabled=True)
        await ctx.reply("隊列已開啟")

    @gq.command(name="close")
    async def gq_close(self, ctx: commands.Context["Bot"]) -> None:
        """Disable queue (mod+)."""
        if not (ctx.chatter.moderator or ctx.chatter.broadcaster):  # type: ignore[attr-defined]
            return

        channel_id = ctx.channel.id
        await self.gq_settings_repo.update_settings(channel_id, enabled=False)
        await ctx.reply("隊列已關閉")

    @gq.command(name="size")
    async def gq_size(self, ctx: commands.Context["Bot"], *, args: str | None = None) -> None:
        """Change group size (mod+)."""
        if not (ctx.chatter.moderator or ctx.chatter.broadcaster):  # type: ignore[attr-defined]
            return

        channel_id = ctx.channel.id

        if not args or not args.strip().isdigit():
            settings = await self.gq_settings_repo.get_or_create(channel_id)
            await ctx.reply(f"!gq size <人數> | 目前: {settings.group_size}人/場")
            return

        size = int(args.strip())
        if size < 1 or size > 20:
            await ctx.reply("範圍: 1-20")
            return

        await self.gq_settings_repo.update_settings(channel_id, group_size=size)
        await ctx.reply(f"已調整為 {size}人/場")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(GameQueueComponent(bot))
    LOGGER.info("GameQueue component loaded")


async def teardown(bot: commands.Bot) -> None:
    LOGGER.info("GameQueue component unloaded")
