"""Giveaway cog package."""

from discord.ext import commands

from .cog import Giveaway

__all__ = ["Giveaway"]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Giveaway(bot))
