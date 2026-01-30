"""Birthday feature module."""

from discord.ext import commands

from .cog import BirthdayCog

__all__ = ["BirthdayCog", "setup"]


async def setup(bot: commands.Bot) -> None:
    """Extension entry point."""
    await bot.add_cog(BirthdayCog(bot))
