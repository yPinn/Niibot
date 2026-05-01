"""Shared base component that ensures messages are sent with the bot's user token."""

from __future__ import annotations

from typing import TYPE_CHECKING

from twitchio.ext import commands

if TYPE_CHECKING:
    from core.bot import Bot


class BotComponent(commands.Component):
    """Base component that provides _ctx_reply() with explicit token_for=bot_id.

    ctx.reply() in TwitchIO 3.x does not forward token_for, causing the request to
    use the app access token instead of the bot's user token. Twitch resolves chat
    badges from the user token, so without it the bot badge is absent. This helper
    always uses the bot's stored user token.
    """

    bot: Bot

    async def _ctx_reply(self, ctx: commands.Context, message: str) -> None:
        await ctx.channel.send_message(
            message=message,
            sender=self.bot.bot_id,
            token_for=self.bot.bot_id,
            reply_to_message_id=str(ctx.message.id) if ctx.message else None,
        )
