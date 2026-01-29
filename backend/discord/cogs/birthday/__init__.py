"""Birthday feature module."""

from .cog import BirthdayCog

__all__ = ["BirthdayCog", "setup"]


async def setup(bot):
    """Extension entry point."""
    await bot.add_cog(BirthdayCog(bot))
