from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).parents[3]


def test_ci_runs_only_before_or_on_the_staging_release_candidate() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    triggers = workflow.split("permissions:", maxsplit=1)[0]
    branch_filters = [
        line.strip() for line in triggers.splitlines() if line.strip().startswith("branches:")
    ]

    assert "  push:" in triggers
    assert "  pull_request:" in triggers
    assert branch_filters == ["branches: [staging]", "branches: [staging]"]


def test_staging_auto_deploy_forces_its_api_to_the_current_branch_head() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    deploy_job = workflow.split("  deploy-staging:", maxsplit=1)[1]

    assert "      environment: staging" in deploy_job
    assert "      force_all: true" in deploy_job


def test_reusable_deploy_requires_an_immutable_commit_sha() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "_deploy.yml").read_text(encoding="utf-8")
    inputs = workflow.split("    inputs:", maxsplit=1)[1].split("\njobs:", maxsplit=1)[0]

    assert "      deploy_sha:" in inputs
    assert 'description: "Exact 40-character commit SHA validated by the caller"' in inputs
    assert "        type: string\n        required: true" in inputs


@pytest.mark.parametrize(
    "workflow_path",
    ["ci.yml", "deploy-staging.yml", "deploy-prod.yml"],
)
def test_deploy_callers_pass_the_validated_commit_sha(workflow_path: str) -> None:
    workflow = (_ROOT / ".github" / "workflows" / workflow_path).read_text(encoding="utf-8")

    assert "      deploy_sha: ${{ github.sha }}" in workflow


def test_deploy_checks_out_the_exact_validated_sha_on_the_expected_branch() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "_deploy.yml").read_text(encoding="utf-8")
    pull_step = workflow.split("      - name: Pull validated code", maxsplit=1)[1].split(
        "      - name: Write env files from secrets", maxsplit=1
    )[0]

    assert "DEPLOY_SHA: ${{ inputs.deploy_sha }}" in pull_step
    assert "DEPLOY_SHA must be a full lowercase 40-character commit SHA" in pull_step
    assert 'git -C "$PROJECT_PATH" merge-base --is-ancestor' in pull_step
    assert '"$DEPLOY_SHA" "origin/$DEPLOY_BRANCH"' in pull_step
    assert 'git -C "$PROJECT_PATH" reset --hard "$DEPLOY_SHA"' in pull_step
    assert 'reset --hard "origin/$DEPLOY_BRANCH"' not in pull_step


def test_manual_production_deploy_defaults_to_the_full_eligible_set() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "deploy-prod.yml").read_text(encoding="utf-8")
    force_input = workflow.split("      force_all:", maxsplit=1)[1].split(
        "\n\npermissions:", maxsplit=1
    )[0]

    assert "        default: true" in force_input


def test_deploy_health_gate_rejects_a_stale_api_revision() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "_deploy.yml").read_text(encoding="utf-8")
    health_check = workflow.split("      - name: Health check", maxsplit=1)[1].split(
        "      - name: Smoke test", maxsplit=1
    )[0]

    assert 'EXPECTED_COMMIT="${{ steps.meta.outputs.commit }}"' in health_check
    assert "d.get('git_commit') == expected" in health_check


def test_cve_gate_only_runs_the_vulnerability_scanner() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "_deploy.yml").read_text(encoding="utf-8")
    scan_step = workflow.split("      - name: Scan images for CVEs", maxsplit=1)[1].split(
        "      - name: Tag images with version", maxsplit=1
    )[0]

    assert "--scanners vuln" in scan_step


def test_cve_scanner_image_is_versioned_and_digest_pinned() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "_deploy.yml").read_text(encoding="utf-8")
    scan_step = workflow.split("      - name: Scan images for CVEs", maxsplit=1)[1].split(
        "      - name: Tag images with version", maxsplit=1
    )[0]

    assert (
        "aquasec/trivy:0.74.0@sha256:"
        "62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969 image"
    ) in scan_step
    assert "aquasec/trivy:latest" not in scan_step
