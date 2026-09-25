from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parents[3] / "scripts" / "ci" / "paths.py"
SPEC = importlib.util.spec_from_file_location("ci_changed_paths", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.parametrize("event_name", ["push", "workflow_dispatch", "workflow_call"])
def test_non_pr_events_always_run_the_full_suite(event_name: str) -> None:
    decision = MODULE.classify_paths([], event_name=event_name, draft=False)

    assert decision.frontend is True
    assert decision.backend is True
    assert decision.reason == "protected-or-manual"


def test_draft_pr_only_runs_preflight() -> None:
    decision = MODULE.classify_paths(
        ["frontend/src/App.tsx", "backend/api/main.py"],
        event_name="pull_request",
        draft=True,
    )

    assert decision.frontend is False
    assert decision.backend is False
    assert decision.reason == "draft"


@pytest.mark.parametrize(
    ("paths", "frontend", "backend", "reason"),
    [
        (["frontend/src/App.tsx"], True, False, "changed-paths"),
        (["backend/api/main.py"], False, True, "changed-paths"),
        (
            ["frontend/src/App.tsx", "backend/api/main.py"],
            True,
            True,
            "changed-paths",
        ),
        (["docs/guides/deployment.md"], False, False, "preflight-only"),
        (["package-lock.json"], False, False, "preflight-only"),
        ([".github/dependabot.yml"], False, False, "preflight-only"),
        ([".github/workflows/ci.yml"], True, True, "ci-control-plane"),
        (["scripts/ci/paths.py"], True, True, "ci-control-plane"),
        (["scripts/env/gen.py"], True, True, "conservative-fallback"),
        (["unknown-runtime-file"], True, True, "conservative-fallback"),
    ],
)
def test_ready_pr_scope_is_change_aware_and_fail_safe(
    paths: list[str],
    frontend: bool,
    backend: bool,
    reason: str,
) -> None:
    decision = MODULE.classify_paths(
        paths,
        event_name="pull_request",
        draft=False,
    )

    assert decision.frontend is frontend
    assert decision.backend is backend
    assert decision.reason == reason


def test_paths_are_normalized_before_classification() -> None:
    decision = MODULE.classify_paths(
        [r".\frontend\src\App.tsx"],
        event_name="pull_request",
        draft=False,
    )

    assert decision.frontend is True
    assert decision.backend is False
