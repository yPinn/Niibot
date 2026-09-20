"""Repository contracts for AI persona v2 fields."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.assistant import AssistantMode, AssistantScope
from shared.repositories.ai_settings import AISettingsRepository, _ai_settings_cache


def _make_pool(*, fetchrow=None) -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    conn.fetchrow.return_value = fetchrow
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


@pytest.mark.asyncio
async def test_missing_row_returns_conservative_persona_v2_defaults() -> None:
    _ai_settings_cache.clear()
    pool, _ = _make_pool(fetchrow=None)

    settings = await AISettingsRepository(pool).get("channel-1")

    assert settings["audience_reference"] == "大家"
    assert settings["tone_preset"] == "neutral"
    assert settings["catchphrase_frequency"] == "off"
    assert settings["example_replies"] == []
    assert settings["refusal_style"] == "polite"
    assert settings["memory_enabled"] is False
    assert settings["cooldown"] == 30
    assert settings["assistant_mode"] == "persona"
    assert settings["active_roleplay_revision_id"] is None


@pytest.mark.asyncio
async def test_upsert_persists_all_persona_v2_fields() -> None:
    _ai_settings_cache.clear()
    returned = {
        "bot_name": "妮寶",
        "persona": "簡短",
        "self_pronoun": "我",
        "audience_reference": "各位",
        "tone_preset": "witty",
        "catchphrase": "好耶",
        "catchphrase_frequency": "occasional",
        "example_replies": ["收到", "交給我"],
        "response_lang": "zh-tw",
        "refusal_style": "humorous",
        "max_tokens": 250,
        "enabled_emotes": [],
        "enabled": True,
        "memory_enabled": True,
        "cooldown": 15,
        "min_role": "everyone",
        "assistant_mode": "persona",
        "active_roleplay_revision_id": None,
    }
    pool, conn = _make_pool(fetchrow=None)
    conn.fetchrow.side_effect = [None, returned]
    repo = AISettingsRepository(pool)

    result = await repo.upsert(
        "channel-1",
        audience_reference="各位",
        tone_preset="witty",
        catchphrase_frequency="occasional",
        example_replies=["收到", "交給我"],
        memory_enabled=True,
    )

    sql, *args = conn.fetchrow.call_args_list[-1].args
    assert "audience_reference" in sql
    assert "tone_preset" in sql
    assert "catchphrase_frequency" in sql
    assert "example_replies" in sql
    assert "memory_enabled" in sql
    assert "assistant_mode" in sql
    assert "active_roleplay_revision_id" in sql
    assert "各位" in args
    assert "witty" in args
    assert "occasional" in args
    assert ["收到", "交給我"] in args
    assert True in args
    assert result["example_replies"] == ["收到", "交給我"]


@pytest.mark.asyncio
async def test_scope_read_bypasses_cached_authoring_settings() -> None:
    pool, conn = _make_pool(
        fetchrow={
            "assistant_mode": "roleplay",
            "active_roleplay_revision_id": 41,
        }
    )

    scope = await AISettingsRepository(pool).get_scope("channel-1")

    assert scope == AssistantScope(AssistantMode.ROLEPLAY, 41)
    sql, channel_id = conn.fetchrow.await_args.args
    assert "assistant_mode" in sql
    assert "active_roleplay_revision_id" in sql
    assert channel_id == "channel-1"


@pytest.mark.asyncio
async def test_missing_scope_row_is_conservative_persona() -> None:
    pool, _ = _make_pool(fetchrow=None)

    scope = await AISettingsRepository(pool).get_scope("channel-1")

    assert scope == AssistantScope(AssistantMode.PERSONA, None)
