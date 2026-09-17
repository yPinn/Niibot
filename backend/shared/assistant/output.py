"""Deterministic output normalization before platform-specific rendering."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from shared.assistant.contracts import AssistantOutcome, AssistantResult

_THINK_CLOSED = re.compile(r"<think\b[^>]*>[\s\S]*?</think\s*>", re.IGNORECASE)
_THINK_OPEN = re.compile(r"<think\b[^>]*>[\s\S]*$", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")
_SENTENCE_PUNCTUATION = ("。", "！", "？", "!", "?", ".")


@dataclass(frozen=True, slots=True)
class OutputPolicy:
    max_chars: int
    single_line: bool = True

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be positive")


@dataclass(frozen=True, slots=True)
class ProcessedOutput:
    outcome: AssistantOutcome
    content: str = ""
    block_reason: str | None = None


class OutputProcessor:
    """Clean a successful model result or pass through a router failure."""

    def __init__(
        self,
        policy: OutputPolicy,
        *,
        scanner: Callable[[str], str | None] | None = None,
    ) -> None:
        self._policy = policy
        self._scanner = scanner

    def process(self, result: AssistantResult) -> ProcessedOutput:
        if result.outcome is not AssistantOutcome.OK:
            return ProcessedOutput(result.outcome)

        content = self._remove_reasoning(result.content)
        if self._policy.single_line:
            content = _WHITESPACE.sub(" ", content).strip()
        else:
            content = content.strip()

        if not content:
            return ProcessedOutput(AssistantOutcome.EMPTY)

        content = self._truncate(content)
        if self._scanner is not None:
            block_reason = self._scanner(content)
            if block_reason is not None:
                return ProcessedOutput(
                    AssistantOutcome.BLOCKED,
                    block_reason=block_reason,
                )

        return ProcessedOutput(AssistantOutcome.OK, content=content)

    @staticmethod
    def _remove_reasoning(content: str) -> str:
        without_closed = _THINK_CLOSED.sub("", content)
        return _THINK_OPEN.sub("", without_closed).strip()

    def _truncate(self, content: str) -> str:
        limit = self._policy.max_chars
        if len(content) <= limit:
            return content

        window = content[:limit]
        boundary = max(window.rfind(punctuation) for punctuation in _SENTENCE_PUNCTUATION)
        if boundary >= limit // 2:
            return window[: boundary + 1]
        if limit == 1:
            return "…"
        return content[: limit - 1].rstrip() + "…"
