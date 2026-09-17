"""Unit tests for twitch.components.ai — AIComponent.ai command.

Covers the cooldown-ordering fix: the shared per-channel cooldown must only
be recorded for a valid (non-empty) invocation, otherwise a bare `!ai` spam
locks the whole channel's AI command indefinitely.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitch.components.ai import AIComponent

from shared.assistant.contracts import (
    AssistantOutcome,
    AssistantResult,
    FailureKind,
    InputSectionKind,
    ProviderCompletion,
    ProviderFailure,
)
from shared.assistant.harness import HarnessResponse
from shared.assistant.memory import ConversationKey, ConversationTurn
from shared.assistant.output import ProcessedOutput

PATCH_ON_COOLDOWN = "twitch.components.ai.is_on_cooldown"
PATCH_RECORD_COOLDOWN = "twitch.components.ai.record_cooldown"
PATCH_MATCH_PACKS = "twitch.components.ai.match_pack_entries"


def _harness_response(
    outcome: AssistantOutcome = AssistantOutcome.OK,
    *,
    failure_kind: FailureKind | None = None,
) -> HarnessResponse:
    if outcome in {AssistantOutcome.OK, AssistantOutcome.BLOCKED}:
        generation = AssistantResult.from_completion(
            ProviderCompletion(provider="fake", model="fake-1", content="answer"),
            attempts=(),
        )
        output = ProcessedOutput(
            outcome,
            content="answer" if outcome is AssistantOutcome.OK else "",
            block_reason="synthetic" if outcome is AssistantOutcome.BLOCKED else None,
        )
        return HarnessResponse(generation, output)

    kind = (
        failure_kind
        or {
            AssistantOutcome.EMPTY: FailureKind.EMPTY,
            AssistantOutcome.UNAVAILABLE: FailureKind.UNKNOWN,
            AssistantOutcome.MISCONFIGURED: FailureKind.AUTHENTICATION,
        }[outcome]
    )
    failure = ProviderFailure(provider="fake", model="fake-1", kind=kind)
    return HarnessResponse(
        AssistantResult.from_failure(failure, attempts=()),
        ProcessedOutput(outcome),
    )


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
    comp.harness = MagicMock()
    comp.harness.respond = AsyncMock(return_value=_harness_response())
    comp.memory_store = MagicMock()
    comp.memory_store.get.return_value = ()
    comp.memory_store.append.return_value = True
    comp.memory_store.clear_channel.return_value = 0
    comp.memory_store.stats.return_value = MagicMock(
        active_sessions=0,
        total_chars=0,
        ttl_evictions=0,
        lru_evictions=0,
        budget_evictions=0,
        oversized_turn_rejections=0,
    )
    comp._ctx_reply = AsyncMock()
    return comp


def _make_ctx(*, channel_id: str = "ch_test") -> MagicMock:
    ctx = MagicMock()
    ctx.channel.id = channel_id
    ctx.channel.name = "streamer"
    ctx.chatter.name = "viewer"
    ctx.chatter.id = "viewer-id"
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
            patch(PATCH_MATCH_PACKS, return_value=[]),
        ):
            ctx = _make_ctx()
            await _ai(comp, ctx, message="hello")

        mock_record.assert_called_once_with(ctx.channel.id, "ai")
        comp.harness.respond.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_valid_message_is_final_untrusted_user_section(self) -> None:
        comp = _make_component()
        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN),
            patch(PATCH_MATCH_PACKS, return_value=[]),
        ):
            await _ai(comp, _make_ctx(), message="hello")

        request = comp.harness.respond.await_args.args[0]
        assert request.sections[-1].kind is InputSectionKind.USER_INPUT
        assert request.sections[-1].content == "hello"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("response", "expected"),
        [
            (_harness_response(AssistantOutcome.BLOCKED), "宇宙射線"),
            (_harness_response(AssistantOutcome.EMPTY), "回應為空"),
            (_harness_response(AssistantOutcome.MISCONFIGURED), "設定異常"),
            (
                _harness_response(
                    AssistantOutcome.UNAVAILABLE,
                    failure_kind=FailureKind.RATE_LIMITED,
                ),
                "服務繁忙",
            ),
            (
                _harness_response(
                    AssistantOutcome.UNAVAILABLE,
                    failure_kind=FailureKind.TIMEOUT,
                ),
                "回應逾時",
            ),
        ],
    )
    async def test_structured_outcome_maps_to_existing_user_message(
        self,
        response: HarnessResponse,
        expected: str,
    ) -> None:
        comp = _make_component()
        comp.harness.respond = AsyncMock(return_value=response)
        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN),
            patch(PATCH_MATCH_PACKS, return_value=[]),
        ):
            await _ai(comp, _make_ctx(), message="hello")

        assert expected in comp._ctx_reply.await_args.args[1]

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


class TestShortTermMemory:
    @pytest.mark.asyncio
    async def test_existing_history_is_inserted_before_current_user_input(self) -> None:
        comp = _make_component(
            ai_settings={
                "enabled": True,
                "memory_enabled": True,
                "min_role": "everyone",
                "cooldown": 15,
                "max_tokens": 200,
            }
        )
        comp.memory_store.get.return_value = (ConversationTurn("earlier", "answer"),)
        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN),
            patch(PATCH_MATCH_PACKS, return_value=[]),
        ):
            await _ai(comp, _make_ctx(), message="follow-up")

        request = comp.harness.respond.await_args.args[0]
        assert request.sections[-2].kind is InputSectionKind.CONVERSATION_HISTORY
        assert '"source":"ephemeral_conversation"' in request.sections[-2].content
        assert '"user":"earlier"' in request.sections[-2].content
        assert "viewer-id" not in request.sections[-2].content
        assert request.sections[-1].kind is InputSectionKind.USER_INPUT
        comp.memory_store.get.assert_called_once_with(
            ConversationKey("twitch", "ch_test", "viewer-id")
        )

    @pytest.mark.asyncio
    async def test_successful_exchange_is_appended_after_reply(self) -> None:
        comp = _make_component(
            ai_settings={
                "enabled": True,
                "memory_enabled": True,
                "min_role": "everyone",
                "cooldown": 15,
                "max_tokens": 200,
            }
        )
        ctx = _make_ctx()
        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN),
            patch(PATCH_MATCH_PACKS, return_value=[]),
        ):
            await _ai(comp, ctx, message="hello")

        comp.memory_store.append.assert_called_once_with(
            ConversationKey("twitch", "ch_test", "viewer-id"),
            ConversationTurn("hello", "answer"),
        )
        assert comp._ctx_reply.await_count == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "outcome",
        [
            AssistantOutcome.BLOCKED,
            AssistantOutcome.EMPTY,
            AssistantOutcome.UNAVAILABLE,
            AssistantOutcome.MISCONFIGURED,
        ],
    )
    async def test_non_success_outcomes_are_never_stored(self, outcome: AssistantOutcome) -> None:
        comp = _make_component(
            ai_settings={
                "enabled": True,
                "memory_enabled": True,
                "min_role": "everyone",
                "cooldown": 15,
                "max_tokens": 200,
            }
        )
        comp.harness.respond = AsyncMock(return_value=_harness_response(outcome))
        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN),
            patch(PATCH_MATCH_PACKS, return_value=[]),
        ):
            await _ai(comp, _make_ctx(), message="hello")

        comp.memory_store.append.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_memory_clears_channel_and_does_not_read_or_append(self) -> None:
        comp = _make_component()
        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN),
            patch(PATCH_MATCH_PACKS, return_value=[]),
        ):
            await _ai(comp, _make_ctx(), message="hello")

        comp.memory_store.clear_channel.assert_called_once_with("twitch", "ch_test")
        comp.memory_store.get.assert_not_called()
        comp.memory_store.append.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_stable_participant_id_skips_memory(self) -> None:
        comp = _make_component(
            ai_settings={
                "enabled": True,
                "memory_enabled": True,
                "min_role": "everyone",
                "cooldown": 15,
                "max_tokens": 200,
            }
        )
        ctx = _make_ctx()
        ctx.chatter.id = ""
        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN),
            patch(PATCH_MATCH_PACKS, return_value=[]),
        ):
            await _ai(comp, ctx, message="hello")

        comp.memory_store.get.assert_not_called()
        comp.memory_store.append.assert_not_called()

    def test_health_and_memory_gauges_expose_counts_only(self) -> None:
        comp = _make_component()
        comp.harness.registry = None
        comp.harness.provider_health.return_value = ()
        comp.memory_store.stats.return_value = MagicMock(
            active_sessions=3,
            total_chars=500,
            ttl_evictions=2,
            lru_evictions=1,
            budget_evictions=4,
            oversized_turn_rejections=5,
        )

        health = comp.ai_health()
        gauges = comp.memory_gauges()

        assert health["memory"] == {
            "active_sessions": 3,
            "total_chars": 500,
            "ttl_evictions": 2,
            "lru_evictions": 1,
            "budget_evictions": 4,
            "oversized_turn_rejections": 5,
        }
        assert gauges == {"sessions": 3, "chars": 500}

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
