"""Integration tests for compiler → router → output orchestration."""

from __future__ import annotations

import pytest

from shared.assistant.contracts import (
    AssistantOutcome,
    AssistantRequest,
    InputSection,
    InputSectionKind,
    MessageRole,
    ProviderCompletion,
    ProviderRequest,
)
from shared.assistant.harness import AssistantHarness, build_assistant_harness
from shared.assistant.output import OutputPolicy, OutputProcessor
from shared.assistant.prompt import PromptBudget, PromptCompiler
from shared.assistant.providers.registry import ProviderConfig, ProviderKind
from shared.assistant.router import BoundedAssistantRouter, RouterPolicy


def _request() -> AssistantRequest:
    return AssistantRequest(
        sections=(
            InputSection(InputSectionKind.CORE_POLICY, "core"),
            InputSection(InputSectionKind.PRODUCT_CONTRACT, "product"),
            InputSection(InputSectionKind.CHANNEL_PERSONA, "persona"),
            InputSection(InputSectionKind.USER_INPUT, "hello"),
        ),
        max_output_tokens=128,
        request_id="req-test",
    )


def _prompt_budget() -> PromptBudget:
    return PromptBudget(
        max_total_chars=4_000,
        max_persona_chars=300,
        max_context_chars=1_000,
        max_history_chars=800,
        max_user_chars=500,
    )


class CapturingProvider:
    name = "fake"
    model = "fake-1"

    def __init__(self, content: str = "first\nsecond") -> None:
        self.content = content
        self.request: ProviderRequest | None = None

    async def complete(self, request: ProviderRequest) -> ProviderCompletion:
        self.request = request
        return ProviderCompletion(provider=self.name, model=self.model, content=self.content)


@pytest.mark.asyncio
async def test_harness_compiles_routes_and_processes_output() -> None:
    provider = CapturingProvider()
    harness = AssistantHarness(
        compiler=PromptCompiler(_prompt_budget()),
        router=BoundedAssistantRouter(
            (provider,),
            policy=RouterPolicy(
                total_timeout_seconds=1.0,
                per_attempt_timeout_seconds=0.5,
            ),
        ),
        output=OutputProcessor(OutputPolicy(max_chars=100)),
        registry=None,
    )

    response = await harness.respond(_request())

    assert response.generation.outcome is AssistantOutcome.OK
    assert response.output.outcome is AssistantOutcome.OK
    assert response.output.content == "first second"
    assert provider.request is not None
    assert provider.request.messages[0].role is MessageRole.DEVELOPER
    assert provider.request.messages[-1].role is MessageRole.USER


@pytest.mark.asyncio
async def test_harness_keeps_generation_metadata_when_output_is_blocked() -> None:
    provider = CapturingProvider("blocked output")
    harness = AssistantHarness(
        compiler=PromptCompiler(_prompt_budget()),
        router=BoundedAssistantRouter(
            (provider,),
            policy=RouterPolicy(
                total_timeout_seconds=1.0,
                per_attempt_timeout_seconds=0.5,
            ),
        ),
        output=OutputProcessor(
            OutputPolicy(max_chars=100),
            scanner=lambda content: "match" if "blocked" in content else None,
        ),
        registry=None,
    )

    response = await harness.respond(_request())

    assert response.generation.provider == "fake"
    assert response.generation.attempts[0].succeeded is True
    assert response.output.outcome is AssistantOutcome.BLOCKED
    assert response.output.block_reason == "match"


def test_factory_builds_secret_safe_registry_without_network_calls() -> None:
    harness = build_assistant_harness(
        configs={
            ProviderKind.GROQ: ProviderConfig("groq-secret", "openai/gpt-oss-120b"),
            ProviderKind.OPENROUTER: ProviderConfig(
                "openrouter-secret", "inclusionai/ling-3.0-flash-vl:free"
            ),
        },
        provider_order=(ProviderKind.GROQ, ProviderKind.OPENROUTER),
        provider_timeout_seconds=4.0,
        router_policy=RouterPolicy(
            total_timeout_seconds=8.0,
            per_attempt_timeout_seconds=4.0,
            max_attempts=2,
        ),
        prompt_budget=_prompt_budget(),
        output_policy=OutputPolicy(max_chars=500),
    )

    assert harness.registry is not None
    assert [spec.kind for spec in harness.registry.specs] == [
        ProviderKind.GROQ,
        ProviderKind.OPENROUTER,
    ]
    assert "groq-secret" not in repr(harness.registry)
    assert "openrouter-secret" not in repr(harness.registry)
