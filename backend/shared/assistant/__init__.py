"""Bounded assistant harness shared by chat platforms."""

from shared.assistant.contracts import (
    AssistantOutcome,
    AssistantProvider,
    AssistantRequest,
    AssistantResult,
    AttemptRecord,
    FailureKind,
    InputSection,
    InputSectionKind,
    MessageRole,
    ProviderCompletion,
    ProviderFailure,
    ProviderMessage,
    ProviderRequest,
    ProviderResponse,
    TokenUsage,
)
from shared.assistant.harness import (
    AssistantHarness,
    HarnessResponse,
    build_assistant_harness,
)
from shared.assistant.health import primary_model_label
from shared.assistant.memory import (
    BoundedConversationMemoryStore,
    ConversationKey,
    ConversationMemoryStats,
    ConversationMemoryStore,
    ConversationTurn,
    NullConversationMemoryStore,
)
from shared.assistant.output import OutputPolicy, OutputProcessor, ProcessedOutput
from shared.assistant.prompt import PromptBudget, PromptCompiler
from shared.assistant.router import (
    BoundedAssistantRouter,
    CircuitState,
    ProviderCircuitSnapshot,
    RouterPolicy,
)

__all__ = [
    "AssistantOutcome",
    "AssistantHarness",
    "AssistantProvider",
    "AssistantRequest",
    "AssistantResult",
    "AttemptRecord",
    "BoundedAssistantRouter",
    "BoundedConversationMemoryStore",
    "CircuitState",
    "ConversationKey",
    "ConversationMemoryStats",
    "ConversationMemoryStore",
    "ConversationTurn",
    "FailureKind",
    "HarnessResponse",
    "InputSection",
    "InputSectionKind",
    "MessageRole",
    "NullConversationMemoryStore",
    "OutputPolicy",
    "OutputProcessor",
    "ProviderCompletion",
    "ProviderFailure",
    "ProviderMessage",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderCircuitSnapshot",
    "ProcessedOutput",
    "PromptBudget",
    "PromptCompiler",
    "RouterPolicy",
    "TokenUsage",
    "build_assistant_harness",
    "primary_model_label",
]
