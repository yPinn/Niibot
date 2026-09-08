from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).parents[3]


def test_staging_auto_deploy_forces_its_api_to_the_current_branch_head() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    deploy_job = workflow.split("  deploy-staging:", maxsplit=1)[1]

    assert "      environment: staging\n      force_all: true" in deploy_job


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
