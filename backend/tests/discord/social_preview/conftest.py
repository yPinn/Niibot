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
    # httpx.AsyncClient.stream is synchronous (returns an async CM, not a coroutine).
    # Using MagicMock avoids "coroutine never awaited" warnings in tests that call
    # _download_cdn_bytes without an explicit stream mock.
    stream_cm = MagicMock()
    stream_cm.__aenter__ = AsyncMock(return_value=stream_cm)
    stream_cm.__aexit__ = AsyncMock(return_value=False)
    c._http.stream = MagicMock(return_value=stream_cm)
    c._twitch_egress = MagicMock()
    c._twitch_egress.acquire_helix = AsyncMock()
    c._twitch_egress.observe_helix = MagicMock()
    c._twitch_egress.close = AsyncMock()
    c._twitch_token = None
    c._twitch_token_exp = 0.0
    return c
