"""Provider-neutral data contracts for the bounded assistant harness.

The contracts intentionally carry no credentials, raw prompts, or provider
exceptions. Adapters normalize third-party responses into these immutable
values before the router makes fallback decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class InputSectionKind(StrEnum):
    """Prompt sections in descending authority order."""

    CORE_POLICY = "core_policy"
    PRODUCT_CONTRACT = "product_contract"
    CHANNEL_PERSONA = "channel_persona"
    RETRIEVED_CONTEXT = "retrieved_context"
    CONVERSATION_HISTORY = "conversation_history"
    USER_INPUT = "user_input"


_SECTION_AUTHORITY: dict[InputSectionKind, int] = {
    kind: index for index, kind in enumerate(InputSectionKind)
}
_TRUSTED_SECTION_KINDS = frozenset(
    {InputSectionKind.CORE_POLICY, InputSectionKind.PRODUCT_CONTRACT}
)


@dataclass(frozen=True, slots=True)
class InputSection:
    """One typed prompt input; trust is derived rather than caller supplied."""

    kind: InputSectionKind
    content: str

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("input section content must not be blank")

    @property
    def trusted(self) -> bool:
        return self.kind in _TRUSTED_SECTION_KINDS


@dataclass(frozen=True, slots=True)
class AssistantRequest:
    """A provider-neutral assistant request before prompt compilation."""

    sections: tuple[InputSection, ...]
    max_output_tokens: int
    request_id: str | None = None
    scheduling_scope: str = "default"

    def __post_init__(self) -> None:
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")

        user_input_count = sum(
            section.kind is InputSectionKind.USER_INPUT for section in self.sections
        )
        if user_input_count != 1:
            raise ValueError("request must contain exactly one user input section")

        ranks = [_SECTION_AUTHORITY[section.kind] for section in self.sections]
        if ranks != sorted(ranks):
            raise ValueError("request sections must follow authority order")

        if self.request_id is not None and not self.request_id.strip():
            raise ValueError("request_id must not be blank")
        if not self.scheduling_scope.strip():
            raise ValueError("scheduling_scope must not be blank")
        if len(self.scheduling_scope) > 128:
            raise ValueError("scheduling_scope must not exceed 128 characters")


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Normalized token accounting when a provider reports it."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    def __post_init__(self) -> None:
        counts = (self.input_tokens, self.output_tokens, self.total_tokens)
        if any(count is not None and count < 0 for count in counts):
            raise ValueError("token counts must not be negative")


class MessageRole(StrEnum):
    """Provider-neutral chat roles produced by the prompt compiler."""

    DEVELOPER = "developer"
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ProviderMessage:
    """One compiled message before provider-specific role mapping."""

    role: MessageRole
    content: str

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("provider message content must not be blank")


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """Compiled request consumed by a provider adapter."""

    messages: tuple[ProviderMessage, ...]
    max_output_tokens: int
    request_id: str | None = None
    scheduling_scope: str = "default"

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("provider request requires at least one message")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if self.request_id is not None and not self.request_id.strip():
            raise ValueError("request_id must not be blank")
        if not self.scheduling_scope.strip():
            raise ValueError("scheduling_scope must not be blank")
        if len(self.scheduling_scope) > 128:
            raise ValueError("scheduling_scope must not exceed 128 characters")


class FailureKind(StrEnum):
    """Normalized failure classes used for bounded fallback decisions."""

    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    NETWORK = "network"
    SERVER_ERROR = "server_error"
    MODEL_UNAVAILABLE = "model_unavailable"
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    VALIDATION = "validation"
    SAFETY = "safety"
    EMPTY = "empty"
    UNKNOWN = "unknown"


_RETRYABLE_FAILURES = frozenset(
    {
        FailureKind.TIMEOUT,
        FailureKind.RATE_LIMITED,
        FailureKind.NETWORK,
        FailureKind.SERVER_ERROR,
        FailureKind.MODEL_UNAVAILABLE,
    }
)


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    """Sanitized provider failure safe to retain in attempt metadata."""

    provider: str
    model: str
    kind: FailureKind
    status_code: int | None = None
    retry_after_seconds: float | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider must not be blank")
        if not self.model.strip():
            raise ValueError("model must not be blank")
        if self.status_code is not None and not 100 <= self.status_code <= 599:
            raise ValueError("status_code must be a valid HTTP status")
        if self.retry_after_seconds is not None and self.retry_after_seconds < 0:
            raise ValueError("retry_after_seconds must not be negative")

    @property
    def retryable(self) -> bool:
        return self.kind in _RETRYABLE_FAILURES


@dataclass(frozen=True, slots=True)
class ProviderCompletion:
    """Normalized successful completion returned by a provider adapter."""

    provider: str
    model: str
    content: str
    usage: TokenUsage | None = None
    finish_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider must not be blank")
        if not self.model.strip():
            raise ValueError("model must not be blank")
        if not self.content.strip():
            raise ValueError("completion content must not be blank")


type ProviderResponse = ProviderCompletion | ProviderFailure


@runtime_checkable
class AssistantProvider(Protocol):
    """Minimal async provider boundary used by fake and real adapters."""

    name: str
    model: str

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Return one normalized completion or failure without leaking secrets."""
        ...


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    """Secret-free metadata for one provider attempt."""

    provider: str
    model: str
    latency_ms: int
    failure: ProviderFailure | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider must not be blank")
        if not self.model.strip():
            raise ValueError("model must not be blank")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must not be negative")
        if self.failure is not None and (
            self.failure.provider != self.provider or self.failure.model != self.model
        ):
            raise ValueError("attempt and failure provider metadata must match")

    @property
    def succeeded(self) -> bool:
        return self.failure is None


class AssistantOutcome(StrEnum):
    """Small set of platform-safe final outcomes."""

    OK = "ok"
    EMPTY = "empty"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    MISCONFIGURED = "misconfigured"


_FAILURE_OUTCOMES: dict[FailureKind, AssistantOutcome] = {
    FailureKind.AUTHENTICATION: AssistantOutcome.MISCONFIGURED,
    FailureKind.PERMISSION: AssistantOutcome.MISCONFIGURED,
    FailureKind.VALIDATION: AssistantOutcome.MISCONFIGURED,
    FailureKind.SAFETY: AssistantOutcome.BLOCKED,
    FailureKind.EMPTY: AssistantOutcome.EMPTY,
}


@dataclass(frozen=True, slots=True)
class AssistantResult:
    """Normalized final result consumed by Twitch and Discord renderers."""

    outcome: AssistantOutcome
    content: str = ""
    provider: str | None = None
    model: str | None = None
    usage: TokenUsage | None = None
    finish_reason: str | None = None
    attempts: tuple[AttemptRecord, ...] = ()
    failure: ProviderFailure | None = None

    def __post_init__(self) -> None:
        if self.outcome is AssistantOutcome.OK:
            if not self.content.strip():
                raise ValueError("successful result content must not be blank")
            if self.provider is None or self.model is None:
                raise ValueError("successful result requires provider and model")
            if self.failure is not None:
                raise ValueError("successful result cannot contain a failure")
            return

        if self.content:
            raise ValueError("failed result content must be empty")
        if self.failure is None:
            raise ValueError("failed result requires normalized failure metadata")

    @classmethod
    def from_completion(
        cls,
        completion: ProviderCompletion,
        *,
        attempts: tuple[AttemptRecord, ...],
    ) -> AssistantResult:
        return cls(
            outcome=AssistantOutcome.OK,
            content=completion.content,
            provider=completion.provider,
            model=completion.model,
            usage=completion.usage,
            finish_reason=completion.finish_reason,
            attempts=attempts,
        )

    @classmethod
    def from_failure(
        cls,
        failure: ProviderFailure,
        *,
        attempts: tuple[AttemptRecord, ...],
    ) -> AssistantResult:
        return cls(
            outcome=_FAILURE_OUTCOMES.get(failure.kind, AssistantOutcome.UNAVAILABLE),
            provider=failure.provider,
            model=failure.model,
            attempts=attempts,
            failure=failure,
        )
