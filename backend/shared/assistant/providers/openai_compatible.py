"""OpenAI-compatible adapter with normalized, secret-free outcomes."""

from __future__ import annotations

from typing import Any, cast

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    ContentFilterFinishReasonError,
    InternalServerError,
    NotFoundError,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from openai.types.chat import ChatCompletionMessageParam

from shared.assistant.contracts import (
    FailureKind,
    MessageRole,
    ProviderCompletion,
    ProviderFailure,
    ProviderRequest,
    ProviderResponse,
    TokenUsage,
)
from shared.assistant.providers.registry import ProviderSpec


class OpenAICompatibleProvider:
    """Adapter for Groq, Gemini, and OpenRouter chat completion endpoints."""

    def __init__(self, spec: ProviderSpec, *, client: Any | None = None) -> None:
        self.spec = spec
        self.name = spec.kind.value
        self.model = spec.model
        self._client = client or AsyncOpenAI(
            base_url=spec.base_url,
            api_key=spec.api_key,
            timeout=spec.timeout_seconds,
            max_retries=0,
        )

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": cast(
                list[ChatCompletionMessageParam],
                [
                    {
                        "role": (
                            self.spec.options.developer_role.value
                            if message.role is MessageRole.DEVELOPER
                            else message.role.value
                        ),
                        "content": message.content,
                    }
                    for message in request.messages
                ],
            ),
            "max_completion_tokens": request.max_output_tokens,
            "temperature": self.spec.options.temperature,
        }
        if self.spec.options.reasoning_effort is not None:
            kwargs["reasoning_effort"] = self.spec.options.reasoning_effort

        extra_body = self._extra_body()
        if extra_body:
            kwargs["extra_body"] = extra_body

        try:
            completion = await self._client.chat.completions.create(**kwargs)
        except Exception as error:
            return self._normalize_error(error)

        choices = getattr(completion, "choices", None) or []
        if not choices:
            return ProviderFailure(self.name, self.model, FailureKind.EMPTY)

        choice = choices[0]
        message = choice.message
        finish_reason = getattr(choice, "finish_reason", None)
        refusal = getattr(message, "refusal", None)
        if refusal or finish_reason == "content_filter":
            return ProviderFailure(self.name, self.model, FailureKind.SAFETY)

        content = getattr(message, "content", None) or ""
        if not isinstance(content, str) or not content.strip():
            return ProviderFailure(self.name, self.model, FailureKind.EMPTY)

        return ProviderCompletion(
            provider=self.name,
            model=getattr(completion, "model", None) or self.model,
            content=content,
            usage=self._normalize_usage(getattr(completion, "usage", None)),
            finish_reason=finish_reason,
        )

    def _extra_body(self) -> dict[str, Any]:
        extra_body: dict[str, Any] = {}
        options = self.spec.options
        if options.reasoning_format is not None:
            extra_body["reasoning_format"] = options.reasoning_format
        if options.include_reasoning is not None:
            extra_body["include_reasoning"] = options.include_reasoning
        if options.disable_reasoning:
            extra_body["reasoning"] = {"enabled": False}
        if options.require_zero_price:
            extra_body["provider"] = {"max_price": {"prompt": 0, "completion": 0}}
        return extra_body

    def _normalize_error(self, error: Exception) -> ProviderFailure:
        kind = self._classify_error(error)
        status_code = error.status_code if isinstance(error, APIStatusError) else None
        return ProviderFailure(
            provider=self.name,
            model=self.model,
            kind=kind,
            status_code=status_code,
        )

    @staticmethod
    def _classify_error(error: Exception) -> FailureKind:
        if isinstance(error, APITimeoutError):
            return FailureKind.TIMEOUT
        if isinstance(error, RateLimitError):
            return FailureKind.RATE_LIMITED
        if isinstance(error, AuthenticationError):
            return FailureKind.AUTHENTICATION
        if isinstance(error, PermissionDeniedError):
            return FailureKind.PERMISSION
        if isinstance(error, (BadRequestError, UnprocessableEntityError)):
            return FailureKind.VALIDATION
        if isinstance(error, NotFoundError):
            return FailureKind.MODEL_UNAVAILABLE
        if isinstance(error, APIConnectionError):
            return FailureKind.NETWORK
        if isinstance(error, InternalServerError):
            return FailureKind.SERVER_ERROR
        if isinstance(error, ContentFilterFinishReasonError):
            return FailureKind.SAFETY
        if isinstance(error, APIStatusError):
            if error.status_code >= 500:
                return FailureKind.SERVER_ERROR
            return FailureKind.UNKNOWN
        if isinstance(error, OpenAIError):
            return FailureKind.UNKNOWN
        return FailureKind.UNKNOWN

    @staticmethod
    def _normalize_usage(usage: Any | None) -> TokenUsage | None:
        if usage is None:
            return None
        return TokenUsage(
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
        )
