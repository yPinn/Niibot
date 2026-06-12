"""Events cog package — server event logging."""

from discord.ext import commands

from .cog import EventsCog

__all__ = ["EventsCog"]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventsCog(bot))
