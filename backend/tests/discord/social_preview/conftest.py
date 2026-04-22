"""Shared fixtures for social_preview tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.cogs.social_preview.cog import SocialPreviewCog
from discord.ext import commands

from core import EmbedFactory


@pytest.fixture
def embed_factory() -> EmbedFactory:
    """Minimal EmbedFactory with no chrome (empty config) for unit tests."""
    return EmbedFactory({})


@pytest.fixture
def cog(embed_factory: EmbedFactory) -> SocialPreviewCog:
    bot = MagicMock(spec=commands.Bot)
    c = SocialPreviewCog.__new__(SocialPreviewCog)
    c.bot = bot
    c._embed = embed_factory
    c._http = AsyncMock()
    c._twitch_token = None
    c._twitch_token_exp = 0.0
    return c
