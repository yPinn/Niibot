"""Shared base component with reply helper."""

from __future__ import annotations

from typing import TYPE_CHECKING

from twitchio.ext import commands

if TYPE_CHECKING:
    from core.bot import Bot


class BotComponent(commands.Component):
    """Base component that provides _ctx_reply() with reply-to threading.

    Uses the app access token (no token_for) so Twitch can display the bot badge.
    The bot badge requires the app token + user:bot scope on the bot account +
    channel:bot scope on the broadcaster's account.
    """

    bot: Bot

    async def _ctx_reply(self, ctx: commands.Context, message: str) -> None:
        await ctx.channel.send_message(
            message=message,
            sender=self.bot.bot_id,
            reply_to_message_id=str(ctx.message.id) if ctx.message else None,
        )
