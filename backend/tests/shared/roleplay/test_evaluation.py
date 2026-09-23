"""Deterministic contracts for Role-play A/B/C evaluation requests and graders."""

from __future__ import annotations

import json

import pytest

from shared.assistant import InputSection, InputSectionKind
from shared.roleplay import (
    CanonMode,
    ChannelStage,
    CharacterKnowledge,
    CharacterSheet,
    EvaluationCase,
    EvaluationRun,
    EvaluationVariant,
    LoreEntry,
    Relationship,
    RelationshipState,
    RoleplayPackage,
    Scene,
    SourceKind,
    SpoilerPolicy,
    WorldSnapshot,
    build_evaluation_request,
    compile_roleplay_package,
    grade_evaluation_output,
    summarize_evaluation_runs,
)


def _package() -> RoleplayPackage:
    return RoleplayPackage(
        schema_version=1,
        name="月港守望者拉娜",
        world=WorldSnapshot(
            title="月港紀事",
            source_kind=SourceKind.ORIGINAL,
            canon_mode=CanonMode.ORIGINAL,
            canon_scope="潮汐祭以前",
            world_anchor="月港以潮汐鐘安排每日作息。",
            story_stage="潮汐祭前三日。",
            spoiler_policy=SpoilerPolicy.FORBID,
        ),
        character=CharacterSheet(
            name="拉娜",
            role="月港守望者",
            motivation="協助居民避開風暴。",
            stable_traits=("細心", "務實"),
            boundaries=("不把猜測當成事實",),
            voice="沉穩，先回答再補充。",
            relationships=(
                Relationship("米洛", "巡查前輩", RelationshipState.TRUSTED, "值得信任"),
            ),
            knowledge=CharacterKnowledge(
                known=("潮汐鐘的用途",),
                unknown=("祭典事故的原因",),
            ),
        ),
        scene=Scene(
            location="東塔",
            current_activity="記錄潮汐",
            current_goal="確認風暴時間",
            emotional_baseline="專注",
            channel_stage=ChannelStage.CHAT_ADAPTED,
            host_relationship="通訊鏡主持人",
            audience_relationship="來訪者",
            adaptation_note="通訊鏡轉述現代名詞。",
        ),
        lore_entries=(
            LoreEntry("月港", ("港口",), "以潮汐鐘安排漁船與市集作息。", True, False, 20),
            LoreEntry("米洛", ("前輩",), "拉娜信任的巡查前輩。", True, False, 10),
            LoreEntry("祭典事故", ("事故",), "事故由鐘塔祭司造成。", False, True, 100),
            LoreEntry("禁用劇透", ("風暴真相",), "風暴其實是人為。", True, True, 90),
        ),
        example_replies=("先確認紀錄，再做判斷。",),
    )


def _trusted_sections() -> tuple[InputSection, ...]:
    return (
        InputSection(InputSectionKind.CORE_POLICY, "core"),
        InputSection(InputSectionKind.PRODUCT_CONTRACT, "product"),
    )


def _persona_section() -> InputSection:
    return InputSection(
        InputSectionKind.CHANNEL_PERSONA,
        json.dumps({"persona": "沉穩務實的守望者拉娜"}, ensure_ascii=False),
    )


def test_variant_a_uses_only_existing_persona_baseline() -> None:
    package = _package()
    case = EvaluationCase("daily", "晚餐吃什麼？")

    request = build_evaluation_request(
        EvaluationVariant.PERSONA_A,
        trusted_sections=_trusted_sections(),
        persona_section=_persona_section(),
        compiled=compile_roleplay_package(package),
        package=package,
        case=case,
    )

    assert [section.kind for section in request.sections] == [
        InputSectionKind.CORE_POLICY,
        InputSectionKind.PRODUCT_CONTRACT,
        InputSectionKind.CHANNEL_PERSONA,
        InputSectionKind.USER_INPUT,
    ]
    assert request.sections[2] == _persona_section()


def test_variant_b_loads_only_query_matched_lore() -> None:
    package = _package()
    case = EvaluationCase("relationship", "米洛值得信任嗎？")

    request = build_evaluation_request(
        EvaluationVariant.CAPSULE_B,
        trusted_sections=_trusted_sections(),
        persona_section=_persona_section(),
        compiled=compile_roleplay_package(package),
        package=package,
        case=case,
    )

    assert [section.kind for section in request.sections] == [
        InputSectionKind.CORE_POLICY,
        InputSectionKind.PRODUCT_CONTRACT,
        InputSectionKind.CHANNEL_PERSONA,
        InputSectionKind.RETRIEVED_CONTEXT,
        InputSectionKind.USER_INPUT,
    ]
    lore = json.loads(request.sections[3].content)
    persona = json.loads(request.sections[2].content)
    assert persona["profile"] == "compact"
    assert persona["performance_capsule"] == compile_roleplay_package(package).compact_capsule
    assert lore["subject"] == "米洛"


def test_variant_b_simple_question_has_no_lore() -> None:
    package = _package()
    case = EvaluationCase("daily", "晚餐吃什麼？")

    request = build_evaluation_request(
        EvaluationVariant.CAPSULE_B,
        trusted_sections=_trusted_sections(),
        persona_section=_persona_section(),
        compiled=compile_roleplay_package(package),
        package=package,
        case=case,
    )

    assert [section.kind for section in request.sections].count(
        InputSectionKind.RETRIEVED_CONTEXT
    ) == 0


def test_variant_c_loads_all_eligible_lore_but_never_unknown_or_forbidden_spoilers() -> None:
    package = _package()
    case = EvaluationCase("daily", "晚餐吃什麼？")

    request = build_evaluation_request(
        EvaluationVariant.FULL_CONTEXT_C,
        trusted_sections=_trusted_sections(),
        persona_section=_persona_section(),
        compiled=compile_roleplay_package(package),
        package=package,
        case=case,
    )

    lore_payloads = [
        json.loads(section.content)
        for section in request.sections
        if section.kind is InputSectionKind.RETRIEVED_CONTEXT
    ]
    persona = json.loads(request.sections[2].content)
    assert persona["profile"] == "full"
    assert persona["performance_capsule"] == compile_roleplay_package(package).capsule
    assert [payload["subject"] for payload in lore_payloads] == ["月港", "米洛"]
    assert sum(len(payload["content"]) for payload in lore_payloads) <= 1_500


def test_evaluation_request_rejects_untrusted_base_sections() -> None:
    package = _package()

    with pytest.raises(ValueError, match="trusted_sections"):
        build_evaluation_request(
            EvaluationVariant.PERSONA_A,
            trusted_sections=(InputSection(InputSectionKind.CHANNEL_PERSONA, "not trusted"),),
            persona_section=_persona_section(),
            compiled=compile_roleplay_package(package),
            package=package,
            case=EvaluationCase("daily", "晚餐吃什麼？"),
        )


def test_code_grader_tracks_required_forbidden_length_and_unnecessary_world_terms() -> None:
    case = EvaluationCase(
        id="daily",
        prompt="泡麵要加蛋嗎？",
        required_any=("加蛋", "可以"),
        forbidden=("海底遺跡",),
        unnecessary_world_terms=("月港", "潮汐"),
        max_chars=100,
    )

    passing = grade_evaluation_output(case, "可以加蛋，也記得補一點蔬菜。")
    failing = grade_evaluation_output(case, "月港的海底遺跡說一定要加蛋。" + "很長" * 50)

    assert passing.passed is True
    assert passing.required_match == "加蛋"
    assert passing.forbidden_matches == ()
    assert passing.unnecessary_world_references == ()
    assert failing.passed is False
    assert failing.forbidden_matches == ("海底遺跡",)
    assert failing.unnecessary_world_references == ("月港",)
    assert failing.within_char_limit is False


def test_code_grader_uses_nfkc_and_casefold() -> None:
    case = EvaluationCase(
        id="latin",
        prompt="Who is Lana?",
        required_any=("lana",),
        forbidden=("pirate",),
    )

    grade = grade_evaluation_output(case, "ＬＡＮＡ is the harbor watcher.")

    assert grade.passed is True
    assert grade.required_match == "lana"


def test_summary_reports_pass_at_k_pass_all_k_and_runtime_metrics() -> None:
    case = EvaluationCase("daily", "吃什麼？", required_any=("飯",))
    passing = grade_evaluation_output(case, "可以吃飯。")
    failing = grade_evaluation_output(case, "先休息。")
    runs = (
        EvaluationRun(
            trial=1,
            variant=EvaluationVariant.CAPSULE_B,
            case_id="daily",
            outcome="ok",
            content="可以吃飯。",
            latency_ms=100,
            input_tokens=100,
            output_tokens=10,
            total_tokens=110,
            grade=passing,
        ),
        EvaluationRun(
            trial=2,
            variant=EvaluationVariant.CAPSULE_B,
            case_id="daily",
            outcome="ok",
            content="先休息。",
            latency_ms=300,
            input_tokens=120,
            output_tokens=8,
            total_tokens=128,
            grade=failing,
        ),
        EvaluationRun(
            trial=1,
            variant=EvaluationVariant.CAPSULE_B,
            case_id="unknown",
            outcome="rate_limited",
            content="",
            latency_ms=200,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            grade=None,
        ),
    )

    summary = summarize_evaluation_runs(runs)

    assert summary.variant is EvaluationVariant.CAPSULE_B
    assert summary.total_runs == 3
    assert summary.successful_runs == 2
    assert summary.code_passes == 1
    assert summary.case_pass_at_k_rate == 0.5
    assert summary.case_pass_all_k_rate == 0.0
    assert summary.mean_latency_ms == 200.0
    assert summary.mean_input_tokens == 110.0


def test_summary_requires_one_variant_and_at_least_one_run() -> None:
    with pytest.raises(ValueError, match="at least one"):
        summarize_evaluation_runs(())

    grade = grade_evaluation_output(EvaluationCase("a", "a"), "answer")
    mixed = (
        EvaluationRun(1, EvaluationVariant.PERSONA_A, "a", "ok", "answer", 1, grade=grade),
        EvaluationRun(1, EvaluationVariant.CAPSULE_B, "a", "ok", "answer", 1, grade=grade),
    )
    with pytest.raises(ValueError, match="one variant"):
        summarize_evaluation_runs(mixed)
