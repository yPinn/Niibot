"""Composition root for the bounded assistant pipeline."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from shared.assistant.contracts import AssistantRequest, AssistantResult
from shared.assistant.output import OutputPolicy, OutputProcessor, ProcessedOutput
from shared.assistant.prompt import PromptBudget, PromptCompiler
from shared.assistant.providers.openai_compatible import OpenAICompatibleProvider
from shared.assistant.providers.registry import (
    ProviderConfig,
    ProviderKind,
    ProviderRegistry,
    build_provider_registry,
)
from shared.assistant.router import (
    BoundedAssistantRouter,
    ProviderCircuitSnapshot,
    RouterPolicy,
)


@dataclass(frozen=True, slots=True)
class HarnessResponse:
    """Keep generation metadata separate from display-safe output."""

    generation: AssistantResult
    output: ProcessedOutput


class AssistantHarness:
    """Compile, route, and normalize one bounded assistant request."""

    def __init__(
        self,
        *,
        compiler: PromptCompiler,
        router: BoundedAssistantRouter,
        output: OutputProcessor,
        registry: ProviderRegistry | None,
    ) -> None:
        self._compiler = compiler
        self._router = router
        self._output = output
        self.registry = registry

    async def respond(self, request: AssistantRequest) -> HarnessResponse:
        provider_request = self._compiler.compile(request)
        generation = await self._router.route(provider_request)
        output = self._output.process(generation)
        return HarnessResponse(generation=generation, output=output)

    def provider_health(self) -> tuple[ProviderCircuitSnapshot, ...]:
        return self._router.provider_health()


def build_assistant_harness(
    *,
    configs: Mapping[ProviderKind, ProviderConfig],
    provider_order: tuple[ProviderKind, ...],
    provider_timeout_seconds: float,
    router_policy: RouterPolicy,
    prompt_budget: PromptBudget,
    output_policy: OutputPolicy,
    scanner: Callable[[str], str | None] | None = None,
) -> AssistantHarness:
    """Build a harness without issuing network requests."""

    registry = build_provider_registry(
        configs,
        provider_order=provider_order,
        timeout_seconds=provider_timeout_seconds,
    )
    providers = tuple(OpenAICompatibleProvider(spec) for spec in registry.specs)
    return AssistantHarness(
        compiler=PromptCompiler(prompt_budget),
        router=BoundedAssistantRouter(providers, policy=router_policy),
        output=OutputProcessor(output_policy, scanner=scanner),
        registry=registry,
    )
