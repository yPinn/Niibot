"""Tests for Discord AI command orchestration through the shared harness."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord.cogs.ai import AICog

from shared.assistant.contracts import (
    AssistantOutcome,
    AssistantResult,
    FailureKind,
    InputSectionKind,
    ProviderCompletion,
    ProviderFailure,
)
from shared.assistant.harness import HarnessResponse
from shared.assistant.output import ProcessedOutput
from shared.assistant.providers.registry import ProviderKind


def _response(
    outcome: AssistantOutcome = AssistantOutcome.OK,
    *,
    failure_kind: FailureKind | None = None,
) -> HarnessResponse:
    if outcome is AssistantOutcome.OK:
        generation = AssistantResult.from_completion(
            ProviderCompletion(provider="fake", model="fake-1", content="answer"),
            attempts=(),
        )
        return HarnessResponse(generation, ProcessedOutput(outcome, content="answer"))

    kind = (
        failure_kind
        or {
            AssistantOutcome.EMPTY: FailureKind.EMPTY,
            AssistantOutcome.BLOCKED: FailureKind.SAFETY,
            AssistantOutcome.UNAVAILABLE: FailureKind.UNKNOWN,
            AssistantOutcome.MISCONFIGURED: FailureKind.AUTHENTICATION,
        }[outcome]
    )
    failure = ProviderFailure(provider="fake", model="fake-1", kind=kind)
    return HarnessResponse(
        AssistantResult.from_failure(failure, attempts=()),
        ProcessedOutput(outcome),
    )


def _cog(response: HarnessResponse | None = None) -> AICog:
    cog = object.__new__(AICog)
    cog.bot = MagicMock()
    cog.harness = MagicMock()
    cog.harness.respond = AsyncMock(return_value=response or _response())
    cog._embed = MagicMock()
    cog._embed.build.return_value = MagicMock()
    return cog


def _interaction() -> MagicMock:
    interaction = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.user.name = "viewer"
    interaction.user.display_avatar.url = "https://example.invalid/avatar.png"
    interaction.guild_id = 12345
    return interaction


async def _ask(cog: AICog, interaction: MagicMock, question: str) -> None:
    await AICog.ai_command.callback(cog, interaction, question=question)  # type: ignore[attr-defined]


def test_provider_order_prioritizes_groq_over_gemini() -> None:
    settings = MagicMock(
        groq_api_key="groq-key",
        groq_model="openai/gpt-oss-120b",
        gemini_api_key="gemini-key",
        gemini_model="gemini-3.5-flash",
        openrouter_api_key="openrouter-key",
        openrouter_model="inclusionai/ling-3.0-flash-vl:free",
    )

    with (
        patch("discord.cogs.ai.get_settings", return_value=settings),
        patch("discord.cogs.ai.build_assistant_harness") as build_harness,
        patch("discord.cogs.ai.EmbedFactory.default"),
    ):
        AICog(MagicMock())

    assert build_harness.call_args.kwargs["provider_order"] == (
        ProviderKind.GROQ,
        ProviderKind.GEMINI,
        ProviderKind.OPENROUTER,
    )


@pytest.mark.asyncio
async def test_question_is_compiled_as_final_user_input() -> None:
    cog = _cog()
    interaction = _interaction()

    await _ask(cog, interaction, "hello")

    request = cog.harness.respond.await_args.args[0]
    assert [section.kind for section in request.sections] == [
        InputSectionKind.CORE_POLICY,
        InputSectionKind.PRODUCT_CONTRACT,
        InputSectionKind.USER_INPUT,
    ]
    assert request.sections[-1].content == "hello"
    assert request.max_output_tokens == 800
    assert request.scheduling_scope == "discord:12345"


@pytest.mark.asyncio
async def test_success_sends_existing_embed_shape() -> None:
    cog = _cog()
    interaction = _interaction()

    await _ask(cog, interaction, "hello")

    interaction.response.defer.assert_awaited_once()
    cog._embed.build.return_value.add_field.assert_any_call(
        name="**回應**",
        value="answer",
        inline=False,
    )
    interaction.followup.send.assert_awaited_once_with(embed=cog._embed.build.return_value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (_response(AssistantOutcome.EMPTY), "AI 回應為空"),
        (_response(AssistantOutcome.BLOCKED), "無法協助"),
        (_response(AssistantOutcome.MISCONFIGURED), "設定異常"),
        (
            _response(
                AssistantOutcome.UNAVAILABLE,
                failure_kind=FailureKind.RATE_LIMITED,
            ),
            "使用人數過多",
        ),
        (
            _response(
                AssistantOutcome.UNAVAILABLE,
                failure_kind=FailureKind.TIMEOUT,
            ),
            "回應逾時",
        ),
    ],
)
async def test_structured_outcome_maps_to_discord_message(
    response: HarnessResponse,
    expected: str,
) -> None:
    cog = _cog(response)
    interaction = _interaction()

    await _ask(cog, interaction, "hello")

    sent = interaction.followup.send.await_args.args[0]
    assert expected in sent
