"""Env file structure validation contracts."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("env_check", ROOT / "scripts" / "env" / "check.py")
assert SPEC is not None and SPEC.loader is not None
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)

SYNC_SPEC = importlib.util.spec_from_file_location("env_sync", ROOT / "scripts" / "env" / "sync.py")
assert SYNC_SPEC is not None and SYNC_SPEC.loader is not None
sync = importlib.util.module_from_spec(SYNC_SPEC)
SYNC_SPEC.loader.exec_module(sync)


def test_accepts_exact_key_set_and_order(tmp_path: Path) -> None:
    example = tmp_path / "x.env.example"
    actual = tmp_path / "x.env"
    example.write_text("# A\nFIRST=\nSECOND=\n", encoding="utf-8")
    actual.write_text("FIRST=value\nSECOND=other\n", encoding="utf-8")

    assert check.validate(actual, example) == []


def test_rejects_missing_extra_and_reordered_keys(tmp_path: Path) -> None:
    example = tmp_path / "x.env.example"
    example.write_text("FIRST=\nSECOND=\n", encoding="utf-8")

    missing = tmp_path / "missing.env"
    missing.write_text("FIRST=x\n", encoding="utf-8")
    assert check.validate(missing, example) == ["missing keys: SECOND"]

    extra = tmp_path / "extra.env"
    extra.write_text("FIRST=x\nSECOND=y\nTHIRD=z\n", encoding="utf-8")
    assert check.validate(extra, example) == ["unknown keys: THIRD"]

    reordered = tmp_path / "reordered.env"
    reordered.write_text("SECOND=y\nFIRST=x\n", encoding="utf-8")
    assert check.validate(reordered, example) == ["key order differs from generated example"]


def test_rejects_duplicate_keys(tmp_path: Path) -> None:
    env_file = tmp_path / "x.env"
    env_file.write_text("FIRST=x\nFIRST=y\n", encoding="utf-8")

    try:
        check.keys(env_file)
    except ValueError as exc:
        assert "duplicate FIRST" in str(exc)
    else:
        raise AssertionError("duplicate key was accepted")


def test_commented_optional_keys_and_repeated_dev_hints_are_structural(tmp_path: Path) -> None:
    example = tmp_path / "x.env.example"
    actual = tmp_path / "x.env"
    example.write_text(
        "ENVIRONMENT=development\n# OPTIONAL=\n# ENVIRONMENT=development\n",
        encoding="utf-8",
    )
    actual.write_text(
        "ENVIRONMENT=development\nOPTIONAL=value\n# ENVIRONMENT=development\n",
        encoding="utf-8",
    )

    assert check.validate(actual, example) == []


def test_runtime_target_pairs_use_explicit_short_environment_names(tmp_path: Path) -> None:
    manifest = {
        "runtime_files": {
            ".env": ["ROOT"],
            "backend/shared.env": ["SHARED"],
            "backend/api/.env": ["API"],
            "frontend/.env": ["FRONTEND"],
        }
    }
    (tmp_path / "env.manifest.json").write_text(
        __import__("json").dumps(manifest), encoding="utf-8"
    )

    assert check.target_pairs(tmp_path, "dev") == [
        (tmp_path / ".env.dev", tmp_path / ".env.example"),
        (tmp_path / "backend/shared.dev.env", tmp_path / "backend/shared.env.example"),
        (tmp_path / "backend/api/.env.dev", tmp_path / "backend/api/.env.example"),
        (tmp_path / "frontend/.env", tmp_path / "frontend/.env.example"),
    ]
    assert check.target_pairs(tmp_path, "stg")[-1] == (
        tmp_path / "backend/api/.env.stg",
        tmp_path / "backend/api/.env.example",
    )


def test_github_target_pairs_include_base_and_selected_environment(tmp_path: Path) -> None:
    assert check.target_pairs(tmp_path, "gh-stg") == [
        (
            tmp_path / ".github/variables/base.env",
            tmp_path / ".github/variables/base.env.example",
        ),
        (
            tmp_path / ".github/variables/stg.env",
            tmp_path / ".github/variables/stg.env.example",
        ),
        (
            tmp_path / ".github/secrets/base.env",
            tmp_path / ".github/secrets/base.env.example",
        ),
        (
            tmp_path / ".github/secrets/stg.env",
            tmp_path / ".github/secrets/stg.env.example",
        ),
    ]


def test_sync_moves_shared_keys_and_preserves_service_values(tmp_path: Path) -> None:
    (tmp_path / "env.registry.toml").write_text(
        """
[[var]]
key = "ENVIRONMENT"
scopes = ["shared"]
[[var]]
key = "LOG_LEVEL"
scopes = ["shared"]
[[var]]
key = "API_PORT"
name = "PORT"
scopes = ["api"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "backend/api").mkdir(parents=True)
    (tmp_path / "backend/shared.env.example").write_text(
        "ENVIRONMENT=development\nLOG_LEVEL=INFO\n", encoding="utf-8"
    )
    (tmp_path / "backend/api/.env.example").write_text("# PORT=8000\n", encoding="utf-8")
    (tmp_path / "backend/shared.dev.env").write_text("LOG_LEVEL=DEBUG\n", encoding="utf-8")
    (tmp_path / "backend/api/.env.dev").write_text(
        "ENVIRONMENT=development\nLOG_LEVEL=DEBUG\nPORT=8123\n", encoding="utf-8"
    )

    outputs = sync.normalized_outputs(tmp_path, "dev")

    assert outputs[tmp_path / "backend/shared.dev.env"] == (
        "ENVIRONMENT=development\nLOG_LEVEL=DEBUG\n"
    )
    assert outputs[tmp_path / "backend/api/.env.dev"] == "PORT=8123\n"


def test_sync_refuses_conflicting_values_without_printing_them(tmp_path: Path) -> None:
    (tmp_path / "env.registry.toml").write_text(
        '[[var]]\nkey = "LOG_LEVEL"\nscopes = ["shared"]\n', encoding="utf-8"
    )
    (tmp_path / "backend/api").mkdir(parents=True)
    (tmp_path / "backend/shared.env.example").write_text("LOG_LEVEL=INFO\n", encoding="utf-8")
    (tmp_path / "backend/api/.env.example").write_text("# API_ONLY=\n", encoding="utf-8")
    (tmp_path / "backend/shared.dev.env").write_text("LOG_LEVEL=first-secret\n", encoding="utf-8")
    (tmp_path / "backend/api/.env.dev").write_text("LOG_LEVEL=second-secret\n", encoding="utf-8")

    try:
        sync.normalized_outputs(tmp_path, "dev")
    except ValueError as exc:
        message = str(exc)
        assert "conflicting values for LOG_LEVEL" in message
        assert "first-secret" not in message
        assert "second-secret" not in message
    else:
        raise AssertionError("conflicting secret values were accepted")
