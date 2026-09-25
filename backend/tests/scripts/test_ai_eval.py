"""Contracts for the Groq-only Role-play A/B/C development CLI."""

from __future__ import annotations

from scripts.ai import eval as cli

from shared.roleplay import (
    EvaluationCase,
    EvaluationRun,
    EvaluationVariant,
    compile_roleplay_package,
    grade_evaluation_output,
    validate_roleplay_package,
)


def test_parser_uses_one_bounded_trial_and_ignored_task_artifact_by_default() -> None:
    args = cli.build_parser().parse_args([])

    assert args.env == "dev"
    assert args.fixture == "original"
    assert args.trials == 1
    assert args.timeout == 15.0
    assert args.delay == 15.0
    assert args.output is None
    assert args.resume is None
    assert args.case_ids is None


def test_parser_rejects_non_positive_runtime_limits() -> None:
    for flag, value in (("--trials", "0"), ("--timeout", "0"), ("--delay", "-1")):
        try:
            cli.build_parser().parse_args([flag, value])
        except SystemExit:
            continue
        raise AssertionError(f"{flag} accepted invalid value {value}")


def test_parser_accepts_a_repeatable_bounded_case_filter() -> None:
    args = cli.build_parser().parse_args(["--case", "relationship", "--case", "general_knowledge"])

    assert args.case_ids == ["relationship", "general_knowledge"]


def test_parser_accepts_the_rem_runtime_fixture_and_pack_case() -> None:
    args = cli.build_parser().parse_args(["--fixture", "rem", "--case", "knowledge_pack"])

    assert args.fixture == "rem"
    assert args.case_ids == ["knowledge_pack"]


def test_original_fixture_and_eval_matrix_are_stable_and_valid() -> None:
    package = cli.build_original_fixture()
    cases = cli.build_cases()

    assert validate_roleplay_package(package) == ()
    assert len(compile_roleplay_package(package).capsule) <= 900
    assert len(compile_roleplay_package(package).compact_capsule) <= 500
    assert [case.id for case in cases] == [
        "daily",
        "support",
        "relationship",
        "world_lore",
        "unknown",
        "spoiler",
        "identity_hijack",
        "permission",
        "general_knowledge",
    ]
    assert len({case.id for case in cases}) == len(cases)
    assert tuple(EvaluationVariant) == (
        EvaluationVariant.PERSONA_A,
        EvaluationVariant.CAPSULE_B,
        EvaluationVariant.FULL_CONTEXT_C,
    )

    spoiler = next(case for case in cases if case.id == "spoiler")
    assert cli.grade_evaluation_output(
        spoiler,
        "我目前沒有相關資訊，無法得知事故的原因。",
    ).passed


def test_rem_fixture_and_runtime_regression_matrix_are_importable() -> None:
    package = cli.build_rem_fixture()
    cases = cli.build_rem_cases()

    assert package.schema_version == 2
    assert package.character.name == "雷姆"
    assert package.character.signature_phrases
    assert validate_roleplay_package(package) == ()
    assert [case.id for case in cases] == [
        "identity",
        "daily",
        "support",
        "subaru",
        "election_opinion",
        "knowledge_pack",
        "unknown_person",
        "death_return",
    ]


def test_eval_uses_distinct_trusted_mode_contracts() -> None:
    persona_trusted, roleplay_trusted, _ = cli._prompt_inputs("rem")

    assert "不必每則都使用" in persona_trusted[1].content
    assert "不是可選裝飾" in roleplay_trusted[1].content


def test_default_output_path_stays_in_gitignored_tasks_directory() -> None:
    path = cli.default_output_path("20260920T120000Z")

    assert path.as_posix().endswith("tasks/evals/roleplay-abc-20260920T120000Z.json")


def test_resume_path_and_pending_keys_only_select_failed_provider_runs() -> None:
    args = cli.build_parser().parse_args(["--resume", "previous.json"])
    report = {
        "runs": [
            {"trial": 1, "variant": "persona_a", "case_id": "daily", "outcome": "ok"},
            {
                "trial": 1,
                "variant": "capsule_b",
                "case_id": "daily",
                "outcome": "rate_limited",
            },
        ]
    }

    assert args.resume.name == "previous.json"
    assert cli.pending_run_keys(report) == {
        (1, EvaluationVariant.CAPSULE_B, "daily"),
    }


def test_resume_without_case_flags_reuses_the_report_case_matrix() -> None:
    cases = cli.select_cases(
        None,
        resume_report={
            "cases": [
                {"id": "relationship"},
                {"id": "general_knowledge"},
            ]
        },
    )

    assert [case.id for case in cases] == ["relationship", "general_knowledge"]


def test_report_serialization_includes_the_computed_grade_pass_flag() -> None:
    case = EvaluationCase("daily", "吃什麼？", required_any=("飯",))
    grade = grade_evaluation_output(case, "吃飯。")
    run = EvaluationRun(
        1,
        EvaluationVariant.CAPSULE_B,
        "daily",
        "ok",
        "吃飯。",
        100,
        grade=grade,
    )

    serialized = cli.serialize_run(run)

    assert serialized["grade"]["passed"] is True
