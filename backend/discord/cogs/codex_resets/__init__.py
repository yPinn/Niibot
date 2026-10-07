"""Codex Resets cog package — Discord notifications for codex-resets.com."""

from discord.ext import commands

from .cog import CodexResetsCog

__all__ = ["CodexResetsCog"]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CodexResetsCog(bot))
