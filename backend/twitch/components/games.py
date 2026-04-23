"""Twitch interactive game commands: !roll, !choose."""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING

from twitchio.ext import commands

from core.guards import check_command
from shared.repositories.command_config import CommandConfigRepository

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)

_MAX_SIDES = 10_000
_MAX_OPTIONS = 20


class GamesComponent(commands.Component):
    COMMANDS: list[dict] = [
        {"command_name": "roll", "cooldown": 3, "aliases": "骰子"},
        {"command_name": "choose", "cooldown": 3, "aliases": "選擇"},
    ]

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.cmd_repo = CommandConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.channel_repo = self.bot.channels  # type: ignore[attr-defined]

    def refresh_pool(self, pool) -> None:
        self.cmd_repo.pool = pool

    @commands.command(name="roll", aliases=["骰子"])
    async def roll(self, ctx: commands.Context[Bot], *, args: str | None = None) -> None:
        """擲骰子。

        用法:
            !roll        — 擲 1d6
            !roll 20     — 擲 1d20
            !骰子 100    — 擲 1d100
        """
        config = await check_command(self.cmd_repo, ctx, "roll", self.channel_repo)
        if not config:
            return

        sides = 6
        if args:
            token = args.strip().split()[0]
            if token.isdigit():
                sides = int(token)
                if sides < 2:
                    await ctx.reply("面數至少要 2 喔！")
                    return
                if sides > _MAX_SIDES:
                    await ctx.reply(f"面數最多 {_MAX_SIDES}，別玩太大 KEKW")
                    return

        result = random.randint(1, sides)
        user = ctx.chatter.display_name or ctx.chatter.name
        await ctx.reply(f"🎲 {user} 擲出 d{sides}，結果：{result}")

    @commands.command(name="choose", aliases=["選擇"])
    async def choose(self, ctx: commands.Context[Bot], *, args: str | None = None) -> None:
        """從選項中隨機選一個。

        用法:
            !choose 紅 藍 綠
            !選擇 pizza hamburger sushi
        """
        config = await check_command(self.cmd_repo, ctx, "choose", self.channel_repo)
        if not config:
            return

        if not args or not args.strip():
            await ctx.reply("用法: !choose 選項1 選項2 ...")
            return

        options = [o for o in args.split() if o]
        if len(options) < 2:
            await ctx.reply("至少給我兩個選項！")
            return
        if len(options) > _MAX_OPTIONS:
            await ctx.reply(f"選項最多 {_MAX_OPTIONS} 個")
            return

        picked = random.choice(options)
        user = ctx.chatter.display_name or ctx.chatter.name
        await ctx.reply(f"🎯 {user} 的選擇：{picked}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(GamesComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
