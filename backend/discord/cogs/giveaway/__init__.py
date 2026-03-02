"""Giveaway cog package."""

from discord.ext import commands

from .cog import GiveawayCog

__all__ = ["GiveawayCog"]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GiveawayCog(bot))
