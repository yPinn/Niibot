"""Tests for Twitch health reporting from the live AI harness registry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_ai_status_comes_from_loaded_component_registry() -> None:
    from twitch.core.health_server import HealthCheckServer

    ai_status = {
        "providers": [
            {
                "provider": "groq",
                "state": "ready",
                "model": "openai/gpt-oss-120b",
                "reason": None,
            }
        ],
        "circuits": [
            {
                "provider": "groq",
                "model": "openai/gpt-oss-120b",
                "state": "closed",
                "consecutive_failures": 0,
            }
        ],
    }
    component = MagicMock()
    component.ai_health.return_value = ai_status
    bot = MagicMock()
    bot.bot_id = "bot-001"
    bot.subs.subscribed = set()
    bot._components = {"AIComponent": component}
    bot.memory_gauges.return_value = {}
    server = HealthCheckServer.__new__(HealthCheckServer)
    server.bot = bot

    with patch(
        "twitch.core.health_server.collect_runtime_gauges",
        return_value={"db_pool": None, "caches": {}},
    ):
        metrics = await server.get_metrics()

    assert metrics["ai_model"] == "groq/openai/gpt-oss-120b"
    assert metrics["ai_status"] == ai_status
