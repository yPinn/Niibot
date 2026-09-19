"""Deterministic A/B/C request construction and code-based eval grading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from statistics import fmean

from shared.assistant.contracts import AssistantRequest, InputSection, InputSectionKind
from shared.roleplay.contracts import (
    CompiledRoleplay,
    RoleplayPackage,
    RoleplayRuntimeProfile,
)
from shared.roleplay.normalization import normalize_roleplay_text
from shared.roleplay.prompt import build_roleplay_context_sections
from shared.roleplay.retrieval import eligible_lore_entries


class EvaluationVariant(StrEnum):
    """The three prompt shapes compared by the V1 model gate."""

    PERSONA_A = "persona_a"
    CAPSULE_B = "capsule_b"
    FULL_CONTEXT_C = "full_context_c"


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    """One stable prompt plus deterministic, intentionally conservative checks."""

    id: str
    prompt: str
    required_any: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    unnecessary_world_terms: tuple[str, ...] = ()
    max_chars: int = 100

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("evaluation case id must not be blank")
        if not self.prompt.strip():
            raise ValueError("evaluation prompt must not be blank")
        if self.max_chars <= 0:
            raise ValueError("evaluation max_chars must be positive")


@dataclass(frozen=True, slots=True)
class EvaluationGrade:
    """Transparent code-grader outcome; naturalness remains a human review."""

    has_content: bool
    within_char_limit: bool
    required_match: str | None
    forbidden_matches: tuple[str, ...]
    unnecessary_world_references: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return (
            self.has_content
            and self.within_char_limit
            and self.required_match is not None
            and not self.forbidden_matches
            and not self.unnecessary_world_references
        )


@dataclass(frozen=True, slots=True)
class EvaluationRun:
    """One provider attempt with secret-free usage and deterministic grade data."""

    trial: int
    variant: EvaluationVariant
    case_id: str
    outcome: str
    content: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    grade: EvaluationGrade | None = None

    def __post_init__(self) -> None:
        if self.trial <= 0:
            raise ValueError("evaluation trial must be positive")
        if not self.case_id.strip():
            raise ValueError("evaluation case_id must not be blank")
        if not self.outcome.strip():
            raise ValueError("evaluation outcome must not be blank")
        if self.latency_ms < 0:
            raise ValueError("evaluation latency must not be negative")


@dataclass(frozen=True, slots=True)
class EvaluationSummary:
    """Aggregate reliability, latency, usage, and context-leak metrics."""

    variant: EvaluationVariant
    total_runs: int
    successful_runs: int
    code_passes: int
    case_pass_at_k_rate: float
    case_pass_all_k_rate: float
    unnecessary_world_reference_runs: int
    mean_latency_ms: float
    mean_input_tokens: float | None
    mean_output_tokens: float | None


def _mean_optional(values: tuple[int | None, ...]) -> float | None:
    present = tuple(value for value in values if value is not None)
    return fmean(present) if present else None


def summarize_evaluation_runs(runs: tuple[EvaluationRun, ...]) -> EvaluationSummary:
    """Summarize one variant, including pass@k and all-k reliability."""

    if not runs:
        raise ValueError("evaluation summary requires at least one run")
    variants = {run.variant for run in runs}
    if len(variants) != 1:
        raise ValueError("evaluation summary accepts only one variant")

    by_case: dict[str, list[EvaluationRun]] = {}
    for run in runs:
        by_case.setdefault(run.case_id, []).append(run)

    def passed(run: EvaluationRun) -> bool:
        return run.grade is not None and run.grade.passed

    code_passes = sum(passed(run) for run in runs)
    case_count = len(by_case)
    pass_at_k = sum(any(passed(run) for run in case_runs) for case_runs in by_case.values())
    pass_all_k = sum(all(passed(run) for run in case_runs) for case_runs in by_case.values())
    return EvaluationSummary(
        variant=runs[0].variant,
        total_runs=len(runs),
        successful_runs=sum(run.outcome == "ok" for run in runs),
        code_passes=code_passes,
        case_pass_at_k_rate=pass_at_k / case_count,
        case_pass_all_k_rate=pass_all_k / case_count,
        unnecessary_world_reference_runs=sum(
            bool(run.grade and run.grade.unnecessary_world_references) for run in runs
        ),
        mean_latency_ms=fmean(run.latency_ms for run in runs),
        mean_input_tokens=_mean_optional(tuple(run.input_tokens for run in runs)),
        mean_output_tokens=_mean_optional(tuple(run.output_tokens for run in runs)),
    )


def _roleplay_lore_section(subject: str, content: str) -> InputSection:
    return InputSection(
        InputSectionKind.RETRIEVED_CONTEXT,
        json.dumps(
            {
                "source": "roleplay_lore",
                "subject": subject,
                "content": content,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )


def _full_context_sections(
    compiled: CompiledRoleplay,
    package: RoleplayPackage,
    *,
    max_lore_chars: int = 1_500,
) -> tuple[InputSection, ...]:
    if max_lore_chars <= 0:
        raise ValueError("full-context lore budget must be positive")
    sections = list(
        build_roleplay_context_sections(
            compiled,
            package,
            "",
            profile=RoleplayRuntimeProfile.FULL,
        )
    )
    total_chars = 0
    for entry in eligible_lore_entries(package):
        if total_chars + len(entry.content) > max_lore_chars:
            continue
        sections.append(_roleplay_lore_section(entry.subject, entry.content))
        total_chars += len(entry.content)
    return tuple(sections)


def build_evaluation_request(
    variant: EvaluationVariant,
    *,
    trusted_sections: tuple[InputSection, ...],
    persona_section: InputSection,
    compiled: CompiledRoleplay,
    package: RoleplayPackage,
    case: EvaluationCase,
    max_output_tokens: int = 250,
) -> AssistantRequest:
    """Build comparable requests while keeping the production authority order."""

    if not trusted_sections or any(not section.trusted for section in trusted_sections):
        raise ValueError("trusted_sections must contain only trusted prompt sections")
    if persona_section.kind is not InputSectionKind.CHANNEL_PERSONA:
        raise ValueError("persona_section must be channel_persona")

    dynamic_sections: tuple[InputSection, ...]
    if variant is EvaluationVariant.PERSONA_A:
        dynamic_sections = (persona_section,)
    elif variant is EvaluationVariant.CAPSULE_B:
        dynamic_sections = build_roleplay_context_sections(compiled, package, case.prompt)
    else:
        dynamic_sections = _full_context_sections(compiled, package)

    return AssistantRequest(
        sections=(
            *trusted_sections,
            *dynamic_sections,
            InputSection(InputSectionKind.USER_INPUT, case.prompt),
        ),
        max_output_tokens=max_output_tokens,
        request_id=f"roleplay-eval-{variant.value}-{case.id}",
    )


def _matches(output: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    normalized_output = normalize_roleplay_text(output)
    return tuple(term for term in terms if normalize_roleplay_text(term) in normalized_output)


def grade_evaluation_output(case: EvaluationCase, output: str) -> EvaluationGrade:
    """Apply deterministic checks without pretending to judge prose naturalness."""

    required_matches = _matches(output, case.required_any)
    return EvaluationGrade(
        has_content=bool(output.strip()),
        within_char_limit=len(output) <= case.max_chars,
        required_match=(
            required_matches[0]
            if required_matches
            else ("" if not case.required_any and output.strip() else None)
        ),
        forbidden_matches=_matches(output, case.forbidden),
        unnecessary_world_references=_matches(output, case.unnecessary_world_terms),
    )
