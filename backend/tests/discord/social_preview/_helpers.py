"""Test helpers shared across social_preview test modules."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord


async def aiter_bytes(chunks: list[bytes]):
    for chunk in chunks:
        yield chunk


SENDER_AVATAR_URL = "https://cdn.discordapp.com/avatars/1/test_avatar.png"


def _make_message(content: str, author_id: int = 1) -> AsyncMock:
    msg = AsyncMock(spec=discord.Message)
    msg.content = content
    msg.author = MagicMock()
    msg.author.bot = False
    msg.author.id = author_id
    msg.author.display_avatar = MagicMock()
    msg.author.display_avatar.url = SENDER_AVATAR_URL
    msg.guild = MagicMock()
    msg.channel = AsyncMock()
    msg.channel.send = AsyncMock(return_value=AsyncMock(spec=discord.Message))
    msg.channel.send.return_value.channel = msg.channel
    msg.delete = AsyncMock()
    return msg
