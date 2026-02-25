"""Giveaway cog package."""

from .cog import Giveaway

__all__ = ["Giveaway"]


async def setup(bot) -> None:
    await bot.add_cog(Giveaway(bot))
