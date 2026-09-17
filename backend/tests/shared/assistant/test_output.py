"""Tests for provider-independent output normalization and display outcomes."""

from __future__ import annotations

import pytest

from shared.assistant.contracts import (
    AssistantOutcome,
    AssistantResult,
    FailureKind,
    ProviderCompletion,
    ProviderFailure,
)
from shared.assistant.output import OutputPolicy, OutputProcessor


def _success(content: str) -> AssistantResult:
    return AssistantResult.from_completion(
        ProviderCompletion(provider="fake", model="fake-1", content=content),
        attempts=(),
    )


def test_removes_closed_and_unclosed_think_blocks() -> None:
    processor = OutputProcessor(OutputPolicy(max_chars=100))

    closed = processor.process(_success("<think>secret reasoning</think>最後答案"))
    unclosed = processor.process(_success("最後答案<think>secret tail"))

    assert closed.outcome is AssistantOutcome.OK
    assert closed.content == "最後答案"
    assert unclosed.content == "最後答案"


def test_normalizes_multiline_whitespace_to_one_line() -> None:
    processor = OutputProcessor(OutputPolicy(max_chars=100))

    result = processor.process(_success(" 第一行\n\n 第二行\t第三段 "))

    assert result.content == "第一行 第二行 第三段"


def test_truncates_at_late_sentence_boundary() -> None:
    processor = OutputProcessor(OutputPolicy(max_chars=16))

    result = processor.process(_success("前半段內容很重要。後半段內容會超過限制而被截掉"))

    assert result.content == "前半段內容很重要。"
    assert len(result.content) <= 16


def test_truncates_with_ellipsis_when_no_late_sentence_boundary() -> None:
    processor = OutputProcessor(OutputPolicy(max_chars=10))

    result = processor.process(_success("這是一段完全沒有任何標點符號的長文字"))

    assert result.content == "這是一段完全沒有任…"
    assert len(result.content) == 10


def test_only_reasoning_becomes_empty_outcome() -> None:
    processor = OutputProcessor(OutputPolicy(max_chars=100))

    result = processor.process(_success("<think>nothing else</think>"))

    assert result.outcome is AssistantOutcome.EMPTY
    assert result.content == ""


def test_injected_scanner_blocks_normalized_visible_content() -> None:
    seen: list[str] = []

    def scanner(content: str) -> str | None:
        seen.append(content)
        return "synthetic-match" if "blocked" in content else None

    processor = OutputProcessor(OutputPolicy(max_chars=100), scanner=scanner)

    result = processor.process(_success("safe\nblocked"))

    assert seen == ["safe blocked"]
    assert result.outcome is AssistantOutcome.BLOCKED
    assert result.content == ""
    assert result.block_reason == "synthetic-match"


@pytest.mark.parametrize(
    "outcome",
    [
        AssistantOutcome.EMPTY,
        AssistantOutcome.BLOCKED,
        AssistantOutcome.UNAVAILABLE,
        AssistantOutcome.MISCONFIGURED,
    ],
)
def test_non_success_router_outcomes_pass_through(outcome: AssistantOutcome) -> None:
    kind = {
        AssistantOutcome.EMPTY: FailureKind.EMPTY,
        AssistantOutcome.BLOCKED: FailureKind.SAFETY,
        AssistantOutcome.UNAVAILABLE: FailureKind.TIMEOUT,
        AssistantOutcome.MISCONFIGURED: FailureKind.AUTHENTICATION,
    }[outcome]
    failure = ProviderFailure(provider="fake", model="fake-1", kind=kind)
    source = AssistantResult.from_failure(failure, attempts=())
    processor = OutputProcessor(OutputPolicy(max_chars=100))

    result = processor.process(source)

    assert result.outcome is outcome
    assert result.content == ""


def test_output_policy_rejects_nonpositive_limit() -> None:
    with pytest.raises(ValueError, match="max_chars"):
        OutputPolicy(max_chars=0)
