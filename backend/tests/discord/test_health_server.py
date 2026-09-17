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
    with patch(
        "discord.core.health_server.get_settings",
        return_value=MagicMock(port=8080),
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

    async def test_ai_status_comes_from_loaded_cog_registry(self):
        from discord.core.health_server import HealthCheckServer

        bot = _make_bot(is_ready=True, latency=0.01)
        ai_status = {
            "providers": [
                {
                    "provider": "groq",
                    "state": "ready",
                    "model": "openai/gpt-oss-120b",
                    "reason": None,
                }
            ],
            "circuits": [],
        }
        cog = MagicMock()
        cog.ai_health.return_value = ai_status
        bot.get_cog.return_value = cog
        server = HealthCheckServer.__new__(HealthCheckServer)
        server.bot = bot

        metrics = await server.get_metrics()

        assert metrics["ai_model"] == "groq/openai/gpt-oss-120b"
        assert metrics["ai_status"] == ai_status
