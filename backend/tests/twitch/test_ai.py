"""Unit tests for twitch.components.ai — AIComponent.ai command.

Covers the cooldown-ordering fix: the shared per-channel cooldown must only
be recorded for a valid (non-empty) invocation, otherwise a bare `!ai` spam
locks the whole channel's AI command indefinitely.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

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
from shared.assistant.scope import AssistantMode, AssistantScope
from shared.models.roleplay import RoleplayRevision
from shared.roleplay import compile_roleplay_package
from tests.shared.roleplay.factories import sample_roleplay_package

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


def _revision(*, revision_id: int = 41) -> RoleplayRevision:
    package = sample_roleplay_package()
    return RoleplayRevision(
        id=revision_id,
        channel_id="ch_test",
        roleplay_set_id=UUID("11111111-1111-4111-8111-111111111111"),
        revision_number=1,
        package=package,
        compiled=compile_roleplay_package(package),
        published_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
    )


def _make_component(
    *,
    ai_settings: dict | None = None,
    current_scope: AssistantScope | None = None,
) -> AIComponent:
    comp = object.__new__(AIComponent)
    comp.bot = MagicMock()
    comp.ai_settings_repo = MagicMock()
    settings = ai_settings or {
        "enabled": True,
        "min_role": "everyone",
        "cooldown": 15,
        "max_tokens": 200,
    }
    comp.ai_settings_repo.get = AsyncMock(return_value=settings)
    comp.ai_settings_repo.get_scope = AsyncMock(
        return_value=current_scope or AssistantScope(AssistantMode.PERSONA, None)
    )
    comp.roleplay_repo = MagicMock()
    comp.roleplay_repo.get_active_revision = AsyncMock(return_value=None)
    comp.module_config_repo = MagicMock()
    comp.module_config_repo.get_enabled_packs = AsyncMock(return_value=[])
    comp.harness = MagicMock()
    comp.harness.respond = AsyncMock(return_value=_harness_response())
    comp.memory_store = MagicMock()
    comp.memory_store.get.return_value = ()
    comp.memory_store.append.return_value = True
    comp.memory_store.clear_channel.return_value = 0
    comp.memory_store.clear_channel_except_scope.return_value = 0
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


@pytest.mark.asyncio
async def test_sync_emotes_uses_shared_helix_coordinator() -> None:
    comp = _make_component(ai_settings={"enabled_emotes": ["Kappa"]})
    comp.bot.sender_for = MagicMock(return_value="bot-1")
    comp.bot.channels = MagicMock()
    comp.bot.channels.get_token = AsyncMock(return_value=MagicMock(token="TOK"))
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "data": [{"name": "Kappa", "emote_type": "globals"}],
    }
    comp.bot._coordinated_helix_get = AsyncMock(return_value=response)

    with patch("twitch.components.ai.get_settings") as settings:
        settings.return_value.twitch_client_id = "cid"
        await comp.sync_emotes("channel-1")

    comp.bot._coordinated_helix_get.assert_awaited_once_with(
        "chat/emotes/user",
        token="TOK",
        token_for="bot-1",
        params={"user_id": "bot-1", "broadcaster_id": "channel-1"},
    )


def test_scope_change_preserves_only_sessions_for_the_announced_scope() -> None:
    comp = _make_component()

    comp.clear_channel_memory_except_scope("ch_test", "roleplay:41")

    comp.memory_store.clear_channel_except_scope.assert_called_once_with(
        "twitch",
        "ch_test",
        "roleplay:41",
    )


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
    async def test_missing_cooldown_uses_conservative_default(self) -> None:
        comp = _make_component(ai_settings={"enabled": True})
        with (
            patch(PATCH_ON_COOLDOWN, return_value=True) as mock_on_cooldown,
            patch(PATCH_RECORD_COOLDOWN),
        ):
            await _ai(comp, _make_ctx(), message="hello")

        cooldown = mock_on_cooldown.call_args.args[2]
        assert cooldown.cooldown == 30

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
        assert request.scheduling_scope == "twitch:ch_test"

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
            ConversationKey("twitch", "ch_test", "viewer-id", "persona")
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
            ConversationKey("twitch", "ch_test", "viewer-id", "persona"),
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
        assert health["capacity_guard"] == {
            "mode": "partitioned-local",
            "runtime": "twitch",
            "max_replicas": 1,
            "distributed": False,
            "shared_provider_accounts": True,
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


class TestRoleplayRuntime:
    def test_pool_refresh_updates_roleplay_repository_too(self) -> None:
        comp = _make_component()
        new_pool = MagicMock()

        comp.refresh_pool(new_pool)

        assert comp.ai_settings_repo.pool is new_pool
        assert comp.roleplay_repo.pool is new_pool
        assert comp.module_config_repo.pool is new_pool

    @pytest.mark.asyncio
    async def test_persona_mode_never_loads_roleplay_revision(self) -> None:
        comp = _make_component(
            ai_settings={
                "enabled": True,
                "min_role": "everyone",
                "cooldown": 15,
                "max_tokens": 200,
                "assistant_mode": "persona",
                "active_roleplay_revision_id": None,
            }
        )
        comp.roleplay_repo.get_active_revision.return_value = _revision()

        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN),
            patch(PATCH_MATCH_PACKS, return_value=[]),
        ):
            await _ai(comp, _make_ctx(), message="hello")

        request = comp.harness.respond.await_args.args[0]
        persona_payload = json.loads(
            next(
                section.content
                for section in request.sections
                if section.kind is InputSectionKind.CHANNEL_PERSONA
            )
        )
        assert "identity" in persona_payload
        assert persona_payload.get("source") != "roleplay_compiled_revision"
        comp.roleplay_repo.get_active_revision.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_active_roleplay_uses_compact_capsule_and_one_matching_lore(self) -> None:
        scope = AssistantScope(AssistantMode.ROLEPLAY, 41)
        comp = _make_component(
            ai_settings={
                "enabled": True,
                "memory_enabled": True,
                "min_role": "everyone",
                "cooldown": 15,
                "max_tokens": 200,
                "assistant_mode": "roleplay",
                "active_roleplay_revision_id": 41,
            },
            current_scope=scope,
        )
        comp.roleplay_repo.get_active_revision.return_value = _revision()

        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN),
            patch(PATCH_MATCH_PACKS) as match_packs,
        ):
            await _ai(comp, _make_ctx(), message="月港現在怎麼生活？")

        request = comp.harness.respond.await_args.args[0]
        assert request.max_output_tokens == 200
        assert request.sections[-1].kind is InputSectionKind.USER_INPUT
        persona_payload = json.loads(
            next(
                section.content
                for section in request.sections
                if section.kind is InputSectionKind.CHANNEL_PERSONA
            )
        )
        lore_payloads = [
            json.loads(section.content)
            for section in request.sections
            if section.kind is InputSectionKind.RETRIEVED_CONTEXT
        ]
        assert persona_payload["source"] == "roleplay_compiled_revision"
        assert persona_payload["profile"] == "compact"
        assert persona_payload["performance_capsule"] == _revision().compiled.compact_capsule
        assert lore_payloads == [
            {
                "source": "roleplay_lore",
                "subject": "月港",
                "content": "依靠潮汐鐘協調作息的海港。",
            }
        ]
        assert len(lore_payloads[0]["content"]) <= 600
        comp.module_config_repo.get_enabled_packs.assert_awaited_once()
        match_packs.assert_not_called()
        comp.memory_store.get.assert_called_once_with(
            ConversationKey("twitch", "ch_test", "viewer-id", "roleplay:41")
        )
        comp.harness.respond.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_active_roleplay_also_uses_channel_knowledge_and_emotes(self) -> None:
        scope = AssistantScope(AssistantMode.ROLEPLAY, 41)
        comp = _make_component(
            ai_settings={
                "enabled": True,
                "memory_enabled": False,
                "min_role": "everyone",
                "cooldown": 15,
                "max_tokens": 200,
                "enabled_emotes": ["Kappa"],
                "assistant_mode": "roleplay",
                "active_roleplay_revision_id": 41,
            },
            current_scope=scope,
        )
        comp.roleplay_repo.get_active_revision.return_value = _revision()
        comp.module_config_repo.get_enabled_packs.return_value = ["xd_ent"]

        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN),
            patch(
                PATCH_MATCH_PACKS,
                return_value=[("叉滴娛樂 / people / roger", "Roger 是實況主。")],
            ) as match_packs,
        ):
            await _ai(comp, _make_ctx(), message="誰是Roger？")

        request = comp.harness.respond.await_args.args[0]
        payloads = [
            json.loads(section.content)
            for section in request.sections
            if section.kind is InputSectionKind.RETRIEVED_CONTEXT
        ]
        contract = next(
            section.content
            for section in request.sections
            if section.kind is InputSectionKind.PRODUCT_CONTRACT
        )

        assert payloads == [
            {"source": "twitch_emotes", "items": ["Kappa"]},
            {
                "source": "knowledge_pack",
                "label": "叉滴娛樂 / people / roger",
                "content": "Roger 是實況主。",
            },
        ]
        assert "角色演繹不是可選裝飾" in contract
        assert "knowledge_pack" in contract
        comp.module_config_repo.get_enabled_packs.assert_awaited_once()
        match_packs.assert_called_once()
        assert match_packs.call_args.args[1:] == (["xd_ent"], "誰是Roger？")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("active_revision", [None, _revision(revision_id=42)])
    async def test_roleplay_mode_without_matching_active_revision_fails_closed(
        self,
        active_revision: RoleplayRevision | None,
    ) -> None:
        comp = _make_component(
            ai_settings={
                "enabled": True,
                "min_role": "everyone",
                "cooldown": 15,
                "max_tokens": 200,
                "assistant_mode": "roleplay",
                "active_roleplay_revision_id": 41,
            }
        )
        comp.roleplay_repo.get_active_revision.return_value = active_revision

        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN),
        ):
            await _ai(comp, _make_ctx(), message="hello")

        comp.harness.respond.assert_not_awaited()
        assert "角色設定暫時無法使用" in comp._ctx_reply.await_args.args[1]

    @pytest.mark.asyncio
    async def test_invalid_stored_mode_fails_closed_before_provider_call(self) -> None:
        comp = _make_component(
            ai_settings={
                "enabled": True,
                "min_role": "everyone",
                "cooldown": 15,
                "max_tokens": 200,
                "assistant_mode": "injected-mode",
                "active_roleplay_revision_id": None,
            }
        )

        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN),
        ):
            await _ai(comp, _make_ctx(), message="hello")

        comp.harness.respond.assert_not_awaited()
        assert "角色設定暫時無法使用" in comp._ctx_reply.await_args.args[1]

    @pytest.mark.asyncio
    async def test_scope_change_during_generation_discards_old_reply_and_memory(self) -> None:
        comp = _make_component(
            ai_settings={
                "enabled": True,
                "memory_enabled": True,
                "min_role": "everyone",
                "cooldown": 15,
                "max_tokens": 200,
                "assistant_mode": "persona",
                "active_roleplay_revision_id": None,
            },
            current_scope=AssistantScope(AssistantMode.ROLEPLAY, 42),
        )

        with (
            patch(PATCH_ON_COOLDOWN, return_value=False),
            patch(PATCH_RECORD_COOLDOWN),
            patch(PATCH_MATCH_PACKS, return_value=[]),
        ):
            await _ai(comp, _make_ctx(), message="hello")

        comp.harness.respond.assert_awaited_once()
        assert comp._ctx_reply.await_args.args[1] == "角色設定剛更新，請再問一次"
        comp.memory_store.append.assert_not_called()
