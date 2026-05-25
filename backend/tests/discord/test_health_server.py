"""Unit tests for discord.core.health_server."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_bot(*, is_ready: bool, latency: float) -> MagicMock:
    bot = MagicMock()
    bot.is_ready.return_value = is_ready
    bot.latency = latency
    bot.user = MagicMock()
    bot.user.id = "bot-001"
    bot.guilds = []
    bot.cogs = {}
    return bot


@pytest.fixture(autouse=True)
def _patch_settings_and_ai():
    with (
        patch(
            "discord.core.health_server.get_settings",
            return_value=MagicMock(
                port=8080,
                groq_api_key="",
                groq_model="",
                gemini_api_key="",
                gemini_model="",
                openrouter_api_key="",
                openrouter_model="",
            ),
        ),
        patch("discord.core.health_server.get_primary_model_label", return_value="none"),
    ):
        yield


@pytest.mark.asyncio
class TestGetMetrics:
    async def test_ready_bot_returns_latency(self):
        from discord.core.health_server import HealthCheckServer

        bot = _make_bot(is_ready=True, latency=0.042)
        server = HealthCheckServer.__new__(HealthCheckServer)
        server.bot = bot

        metrics = await server.get_metrics()

        assert metrics["ws_latency_ms"] == 42

    async def test_not_ready_returns_null_latency(self):
        """When the bot is not connected, latency is NaN → ws_latency_ms must be None."""
        from discord.core.health_server import HealthCheckServer

        bot = _make_bot(is_ready=False, latency=float("nan"))
        server = HealthCheckServer.__new__(HealthCheckServer)
        server.bot = bot

        metrics = await server.get_metrics()

        assert metrics["ws_latency_ms"] is None

    async def test_nan_latency_does_not_raise(self):
        """math.isfinite guard prevents ValueError from round(nan)."""
        import math

        from discord.core.health_server import HealthCheckServer

        bot = _make_bot(is_ready=False, latency=float("nan"))
        server = HealthCheckServer.__new__(HealthCheckServer)
        server.bot = bot

        # Must not raise even though round(float("nan")) would raise ValueError
        metrics = await server.get_metrics()
        assert metrics["ws_latency_ms"] is None
        assert math.isnan(bot.latency)
