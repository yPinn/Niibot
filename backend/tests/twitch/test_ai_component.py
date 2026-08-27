"""Unit tests for twitch.components.ai — AIComponent.ai command.

Covers the cooldown-ordering fix: the shared per-channel cooldown must only
be recorded for a valid (non-empty) invocation, otherwise a bare `!ai` spam
locks the whole channel's AI command indefinitely.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitch.components.ai import AIComponent

PATCH_ON_COOLDOWN = "twitch.components.ai.is_on_cooldown"
PATCH_RECORD_COOLDOWN = "twitch.components.ai.record_cooldown"
PATCH_PROVIDER_CHAIN = "twitch.components.ai.call_provider_chain"
PATCH_MATCH_PACKS = "twitch.components.ai.match_pack_entries"


def _make_component(*, ai_settings: dict | None = None) -> AIComponent:
    comp = object.__new__(AIComponent)
    comp.bot = MagicMock()
    comp.ai_settings_repo = MagicMock()
    comp.ai_settings_repo.get = AsyncMock(
        return_value=ai_settings
        or {"enabled": True, "min_role": "everyone", "cooldown": 15, "max_tokens": 200}
    )
    comp.module_config_repo = MagicMock()
    comp.module_config_repo.get_enabled_packs = AsyncMock(return_value=[])
    comp.provider_chain = []
    comp._ctx_reply = AsyncMock()
    return comp


def _make_ctx(*, channel_id: str = "ch_test") -> MagicMock:
    ctx = MagicMock()
    ctx.channel.id = channel_id
    ctx.channel.name = "streamer"
    ctx.chatter.name = "viewer"
    return ctx


async def _ai(component: AIComponent, ctx: MagicMock, message: str | None = None) -> None:
    await AIComponent.ai.callback(component, ctx, message=message)  # type: ignore[attr-defined]


class TestCooldownOrdering:
    @pytest.mark.asyncio
    async def test_empty_message_does_not_record_cooldown(self) -> None:
        comp = _make_component()
        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN) as mock_record,
        ):
            await _ai(comp, _make_ctx(), message=None)

        mock_record.assert_not_called()
        comp._ctx_reply.assert_awaited_once()
        assert "用法" in comp._ctx_reply.call_args[0][1]

    @pytest.mark.asyncio
    async def test_whitespace_only_message_does_not_record_cooldown(self) -> None:
        comp = _make_component()
        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN) as mock_record,
        ):
            await _ai(comp, _make_ctx(), message="   ")

        mock_record.assert_not_called()

    @pytest.mark.asyncio
    async def test_repeated_empty_invocations_never_lock_the_cooldown(self) -> None:
        """The original bug: spamming a bare !ai kept the cooldown perpetually
        hot, blocking every other viewer's real request forever."""
        comp = _make_component()
        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN) as mock_record,
        ):
            for _ in range(5):
                await _ai(comp, _make_ctx(), message=None)

        mock_record.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_message_records_cooldown(self) -> None:
        comp = _make_component()
        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN) as mock_record,
            patch(PATCH_PROVIDER_CHAIN, AsyncMock(return_value=("answer", None))),
            patch(PATCH_MATCH_PACKS, return_value=[]),
        ):
            ctx = _make_ctx()
            await _ai(comp, ctx, message="hello")

        mock_record.assert_called_once_with(ctx.channel.id, "ai")

    @pytest.mark.asyncio
    async def test_on_cooldown_skips_before_validation_or_recording(self) -> None:
        comp = _make_component()
        with (
            patch(PATCH_ON_COOLDOWN, return_value=True),
            patch(PATCH_RECORD_COOLDOWN) as mock_record,
        ):
            await _ai(comp, _make_ctx(), message=None)

        mock_record.assert_not_called()
        comp._ctx_reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_ai_does_not_record_cooldown(self) -> None:
        comp = _make_component(ai_settings={"enabled": False})
        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN) as mock_record,
        ):
            await _ai(comp, _make_ctx(), message="hello")

        mock_record.assert_not_called()
        comp._ctx_reply.assert_not_called()
