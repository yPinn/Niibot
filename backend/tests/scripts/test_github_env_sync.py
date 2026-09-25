"""Contracts for the local GitHub configuration sync helpers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[3]
CI_SPEC = importlib.util.spec_from_file_location("env_ci", ROOT / "scripts" / "env" / "ci.py")
assert CI_SPEC is not None and CI_SPEC.loader is not None
ci = importlib.util.module_from_spec(CI_SPEC)
CI_SPEC.loader.exec_module(ci)


def _show_vars_program() -> str:
    script = (ROOT / ".github/pull.sh").read_text(encoding="utf-8")
    marker = '$PYTHON - "$tmp" "$outfile" "$example" <<\'PYEOF\'\n'
    return script.split(marker, 1)[1].split("\nPYEOF", 1)[0]


def _show_secrets_program() -> str:
    script = (ROOT / ".github/pull.sh").read_text(encoding="utf-8")
    marker = '$PYTHON - "$tmp" "$example_file" <<\'PYEOF\'\n'
    return script.split(marker, 1)[1].split("\nPYEOF", 1)[0]


def _run_show_vars(monkeypatch, data: list[dict[str, str]], output: Path, example: Path) -> None:
    source = output.with_suffix(".json")
    source.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["show_vars", str(source), str(output), str(example)])
    exec(compile(_show_vars_program(), "pull.sh:show_vars", "exec"), {"__name__": "__main__"})


def _run_show_secrets(
    monkeypatch,
    env_data: list[dict[str, str]],
    base_data: list[dict[str, str]],
    example: Path,
) -> None:
    source = example.with_suffix(".json")
    source.write_text(
        f"{json.dumps(env_data)}\n{json.dumps(base_data)}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["show_secrets", str(source), str(example)])
    exec(
        compile(_show_secrets_program(), "pull.sh:show_secrets", "exec"),
        {"__name__": "__main__"},
    )


def test_pull_preserves_example_structure_and_marks_missing_values(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    example = tmp_path / "vars.env.example"
    example.write_text("# ── App\nAPI_URL=\nENVIRONMENT=production\n", encoding="utf-8")
    output = tmp_path / "vars.env"

    _run_show_vars(
        monkeypatch,
        [
            {"name": "API_URL", "value": "https://example.invalid"},
            {"name": "EXTRA", "value": "kept"},
        ],
        output,
        example,
    )

    assert output.read_text(encoding="utf-8") == (
        "# ── App\nAPI_URL=https://example.invalid\nENVIRONMENT=production\n\n"
        "# ── extra\nEXTRA=kept\n"
    )
    stdout = capsys.readouterr().out
    assert "miss" in stdout
    assert "ENVIRONMENT" in stdout


def test_pull_rejects_multiline_variables(tmp_path: Path, monkeypatch) -> None:
    example = tmp_path / "vars.env.example"
    example.write_text("API_URL=\n", encoding="utf-8")
    output = tmp_path / "vars.env"

    with pytest.raises(SystemExit) as exc_info:
        _run_show_vars(
            monkeypatch,
            [{"name": "API_URL", "value": "first\nsecond"}],
            output,
            example,
        )

    assert exc_info.value.code == 1
    assert not output.exists()


def test_pull_keeps_missing_optional_variables_commented(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    example = tmp_path / "vars.env.example"
    example.write_text("# OPTIONAL_MODEL=default\nREQUIRED_VALUE=\n", encoding="utf-8")
    output = tmp_path / "vars.env"

    _run_show_vars(
        monkeypatch,
        [{"name": "REQUIRED_VALUE", "value": "configured"}],
        output,
        example,
    )

    assert output.read_text(encoding="utf-8") == (
        "# OPTIONAL_MODEL=default\nREQUIRED_VALUE=configured\n"
    )
    assert "OPTIONAL_MODEL" not in capsys.readouterr().out


def test_pull_does_not_report_missing_optional_secrets(tmp_path: Path, monkeypatch, capsys) -> None:
    example = tmp_path / "secrets.env.example"
    example.write_text("REQUIRED_SECRET=\n# OPTIONAL_SECRET=\n", encoding="utf-8")

    _run_show_secrets(monkeypatch, [], [], example)

    output = capsys.readouterr().out
    assert "REQUIRED_SECRET" in output
    assert "OPTIONAL_SECRET" not in output


def test_ci_writer_quotes_values_and_url_encodes_database_credentials(
    tmp_path: Path, monkeypatch
) -> None:
    manifest = {
        "required_secrets": ["POSTGRES_PASSWORD"],
        "required_variables": ["POSTGRES_USER", "POSTGRES_DB"],
        "ci": {
            "POSTGRES_USER": {"file": "root", "source": "var:POSTGRES_USER"},
            "POSTGRES_PASSWORD": {"file": "root", "source": "secret:POSTGRES_PASSWORD"},
            "POSTGRES_DB": {"file": "root", "source": "var:POSTGRES_DB"},
            "DOCKER_DATABASE_URL": {"file": "root", "source": "derived:db_url"},
            "SAMPLE": {"file": "shared", "source": "secret:SAMPLE"},
            "QUOTED": {"file": "shared", "source": "secret:QUOTED"},
        },
    }
    (tmp_path / "env.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    secrets = {
        "POSTGRES_PASSWORD": "p@ss$#",
        "SAMPLE": "space # $value",
        "QUOTED": "C:\\tmp it's safe",
    }
    variables = {"POSTGRES_USER": "user", "POSTGRES_DB": "db/name"}
    monkeypatch.setenv("SECRETS_JSON", json.dumps(secrets))
    monkeypatch.setenv("VARS_JSON", json.dumps(variables))
    monkeypatch.setenv("PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("DEPLOY_ENVIRONMENT", "production")
    monkeypatch.delenv("DRY_RUN", raising=False)

    assert ci.main() == 0

    assert (tmp_path / ".env.prod").read_text(encoding="utf-8").splitlines() == [
        "POSTGRES_USER='user'",
        "POSTGRES_PASSWORD='p@ss$#'",
        "POSTGRES_DB='db/name'",
        "DOCKER_DATABASE_URL='postgresql://user:p%40ss%24%23@postgres:5432/db%2Fname'",
    ]
    shared = tmp_path / "backend/shared.prod.env"
    parsed = dotenv_values(shared)
    assert shared.read_text(encoding="utf-8").splitlines()[0] == "SAMPLE='space # $value'"
    assert parsed["SAMPLE"] == "space # $value"
    assert parsed["QUOTED"] == "C:\\tmp it's safe"


def test_ci_writer_requires_public_deploy_variables(tmp_path: Path, monkeypatch, capsys) -> None:
    manifest = {
        "required_secrets": [],
        "required_variables": ["FRONTEND_URL"],
        "ci": {},
    }
    (tmp_path / "env.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("SECRETS_JSON", "{}")
    monkeypatch.setenv("VARS_JSON", "{}")
    monkeypatch.setenv("PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("DEPLOY_ENVIRONMENT", "staging")
    monkeypatch.delenv("DRY_RUN", raising=False)

    assert ci.main() == 1
    assert "missing required GitHub Variables: FRONTEND_URL" in capsys.readouterr().err
    assert not (tmp_path / ".env.stg").exists()


def test_ci_writer_dry_run_never_prints_values(tmp_path: Path, monkeypatch, capsys) -> None:
    manifest = {
        "required_secrets": [],
        "required_variables": [],
        "ci": {"SAMPLE": {"file": "shared", "source": "secret:SAMPLE"}},
    }
    (tmp_path / "env.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("SECRETS_JSON", json.dumps({"SAMPLE": "super-secret-value"}))
    monkeypatch.setenv("VARS_JSON", "{}")
    monkeypatch.setenv("PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("DEPLOY_ENVIRONMENT", "staging")
    monkeypatch.setenv("DRY_RUN", "1")

    assert ci.main() == 0

    output = capsys.readouterr().out
    assert "backend/shared.stg.env" in output
    assert "super-secret-value" not in output
    assert not (tmp_path / "backend/shared.stg.env").exists()
