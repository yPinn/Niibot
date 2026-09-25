"""Env file structure validation contracts."""

from __future__ import annotations

import importlib.util
from base64 import urlsafe_b64encode
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
        (tmp_path / "frontend/.env.dev", tmp_path / "frontend/.env.example"),
    ]
    assert check.target_pairs(tmp_path, "stg")[-1] == (
        tmp_path / "backend/api/.env.stg",
        tmp_path / "backend/api/.env.example",
    )


def test_frontend_dev_sync_uses_the_suffixed_runtime_file() -> None:
    template = Path("frontend/.env")

    assert sync._actual_path(template, "dev") == Path("frontend/.env.dev")
    assert sync._actual_path(template, "stg") is None
    assert sync._actual_path(template, "prod") is None


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


def _write_github_validation_fixture(tmp_path: Path) -> None:
    (tmp_path / "env.registry.toml").write_text(
        """
[[var]]
key = "PROJECT_DIR"
scopes = []
required = true
sensitive = false
[var.ci]
source = "var:PROJECT_DIR"
scope = "env"

[[var]]
key = "GROQ_API_KEY"
scopes = ["shared"]
group = "groq"
activates_group = true
[var.ci]
file = "shared"
source = "secret:GROQ_API_KEY"
scope = "base"
conditional = true

[[var]]
key = "GROQ_MODEL"
scopes = ["shared"]
group = "groq"
default = "default-model"
sensitive = false
[var.ci]
file = "shared"
source = "var:GROQ_MODEL"
scope = "base"
conditional = true

[[var]]
key = "NIGHTBOT_CLIENT_ID"
scopes = ["api"]
group = "nightbot"
activates_group = true
sensitive = false
[var.ci]
file = "api"
source = "var:NIGHTBOT_CLIENT_ID"
scope = "env"
conditional = true

[[var]]
key = "NIGHTBOT_CLIENT_SECRET"
scopes = ["api"]
group = "nightbot"
activates_group = true
[var.ci]
file = "api"
source = "secret:NIGHTBOT_CLIENT_SECRET"
scope = "env"
conditional = true
""".strip()
        + "\n",
        encoding="utf-8",
    )
    files = {
        ".github/variables/base.env.example": "# GROQ_MODEL=default-model\n",
        ".github/variables/base.env": "# GROQ_MODEL=default-model\n",
        ".github/secrets/base.env.example": "# GROQ_API_KEY=\n",
        ".github/secrets/base.env": "# GROQ_API_KEY=\n",
        ".github/variables/stg.env.example": "PROJECT_DIR=\n# NIGHTBOT_CLIENT_ID=\n",
        ".github/variables/stg.env": "PROJECT_DIR=\n# NIGHTBOT_CLIENT_ID=\n",
        ".github/secrets/stg.env.example": "# NIGHTBOT_CLIENT_SECRET=\n",
        ".github/secrets/stg.env": "# NIGHTBOT_CLIENT_SECRET=\n",
        ".github/variables/prod.env.example": "PROJECT_DIR=\n# NIGHTBOT_CLIENT_ID=\n",
        ".github/variables/prod.env": "PROJECT_DIR=unused\n# NIGHTBOT_CLIENT_ID=\n",
        ".github/secrets/prod.env.example": "# NIGHTBOT_CLIENT_SECRET=\n",
        ".github/secrets/prod.env": "# NIGHTBOT_CLIENT_SECRET=\n",
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_github_value_validation_rejects_blank_required_values(tmp_path: Path) -> None:
    _write_github_validation_fixture(tmp_path)

    errors = check.value_errors(tmp_path, "gh-stg")

    assert errors == ["required value is blank: PROJECT_DIR"]


def test_github_value_validation_uses_group_defaults(tmp_path: Path) -> None:
    _write_github_validation_fixture(tmp_path)
    (tmp_path / ".github/variables/stg.env").write_text(
        "PROJECT_DIR=/srv/niibot\n# NIGHTBOT_CLIENT_ID=\n", encoding="utf-8"
    )
    (tmp_path / ".github/secrets/base.env").write_text(
        "GROQ_API_KEY=secret-value\n", encoding="utf-8"
    )

    assert check.value_errors(tmp_path, "gh-stg") == []


def test_github_value_validation_rejects_incomplete_groups_without_values(tmp_path: Path) -> None:
    _write_github_validation_fixture(tmp_path)
    (tmp_path / ".github/variables/stg.env").write_text(
        "PROJECT_DIR=/srv/niibot\nNIGHTBOT_CLIENT_ID=nightbot-id\n", encoding="utf-8"
    )

    errors = check.value_errors(tmp_path, "gh-stg")

    assert errors == ["incomplete group nightbot: missing NIGHTBOT_CLIENT_SECRET"]
    assert "nightbot-id" not in " ".join(errors)


def test_deployment_paths_must_be_distinct(tmp_path: Path) -> None:
    for scope in ("stg", "prod"):
        path = tmp_path / f".github/variables/{scope}.env"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("PROJECT_DIR=/srv/niibot\n", encoding="utf-8")

    assert check.deployment_path_errors(tmp_path) == [
        "staging and production PROJECT_DIR must differ"
    ]

    (tmp_path / ".github/variables/stg.env").write_text(
        "PROJECT_DIR=/srv/niibot-stg/\n", encoding="utf-8"
    )
    assert check.deployment_path_errors(tmp_path) == []


def test_dev_value_validation_rejects_blank_required_values(tmp_path: Path) -> None:
    (tmp_path / "env.registry.toml").write_text(
        '[[var]]\nkey = "TOKEN"\nscopes = ["shared"]\nrequired = true\n',
        encoding="utf-8",
    )
    (tmp_path / "env.manifest.json").write_text(
        __import__("json").dumps({"runtime_files": {"backend/shared.env": []}}),
        encoding="utf-8",
    )
    shared = tmp_path / "backend/shared.dev.env"
    shared.parent.mkdir(parents=True)
    shared.write_text("TOKEN=\n", encoding="utf-8")

    assert check.value_errors(tmp_path, "dev") == ["required value is blank: TOKEN"]


def test_value_validation_rejects_invalid_fernet_keys(tmp_path: Path) -> None:
    (tmp_path / "env.registry.toml").write_text(
        "\n".join(
            (
                "[[var]]",
                'key = "ENCRYPTION_KEY"',
                'scopes = ["shared"]',
                "required = true",
                'format = "fernet"',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "env.manifest.json").write_text(
        __import__("json").dumps({"runtime_files": {"backend/shared.env": []}}),
        encoding="utf-8",
    )
    shared = tmp_path / "backend/shared.dev.env"
    shared.parent.mkdir(parents=True)
    shared.write_text("ENCRYPTION_KEY=invalid-secret\n", encoding="utf-8")

    assert check.value_errors(tmp_path, "dev") == ["invalid Fernet key: ENCRYPTION_KEY"]

    shared.write_text(
        f"ENCRYPTION_KEY={urlsafe_b64encode(b'0' * 32).decode()}\n",
        encoding="utf-8",
    )
    assert check.value_errors(tmp_path, "dev") == []


def _write_dev_boundary_fixture(tmp_path: Path) -> None:
    (tmp_path / "env.registry.toml").write_text(
        """
[[var]]
key = "DATABASE_URL"
scopes = ["shared"]

[[var]]
key = "POSTGRES_PASSWORD"
scopes = ["root"]

[[var]]
key = "TWITCH_CLIENT_ID"
scopes = ["shared"]
sensitive = false

[[var]]
key = "TWITCH_CLIENT_SECRET"
scopes = ["shared"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "env.manifest.json").write_text(
        __import__("json").dumps({"runtime_files": {".env": [], "backend/shared.env": []}}),
        encoding="utf-8",
    )
    (tmp_path / "backend").mkdir()
    (tmp_path / ".env.dev").write_text("POSTGRES_PASSWORD=prod-password\n", encoding="utf-8")
    (tmp_path / "backend/shared.dev.env").write_text(
        "DATABASE_URL=postgresql://dev:password@postgres:5432/dev\nTWITCH_CLIENT_ID=prod-client\n",
        encoding="utf-8",
    )
    for kind in ("secrets", "variables"):
        (tmp_path / f".github/{kind}").mkdir(parents=True)
    (tmp_path / ".github/secrets/stg.env").write_text("", encoding="utf-8")
    (tmp_path / ".github/secrets/prod.env").write_text(
        "POSTGRES_PASSWORD=prod-password\n", encoding="utf-8"
    )
    (tmp_path / ".github/variables/stg.env").write_text("", encoding="utf-8")
    (tmp_path / ".github/variables/prod.env").write_text(
        "TWITCH_CLIENT_ID=prod-client\n", encoding="utf-8"
    )


def test_dev_boundary_rejects_container_db_host_and_deployed_credentials(tmp_path: Path) -> None:
    _write_dev_boundary_fixture(tmp_path)

    errors = check.dev_boundary_errors(tmp_path)

    assert errors == [
        "dev DATABASE_URL must use a loopback host",
        "dev value reuses prod application identity: TWITCH_CLIENT_ID",
        "dev value reuses prod secret: POSTGRES_PASSWORD",
    ]
    assert "prod-password" not in " ".join(errors)
    assert "prod-client" not in " ".join(errors)


def test_dev_boundary_accepts_loopback_and_distinct_values(tmp_path: Path) -> None:
    _write_dev_boundary_fixture(tmp_path)
    (tmp_path / ".env.dev").write_text("POSTGRES_PASSWORD=dev-password\n", encoding="utf-8")
    (tmp_path / "backend/shared.dev.env").write_text(
        "DATABASE_URL=postgresql://dev:password@localhost:5432/dev\nTWITCH_CLIENT_ID=dev-client\n",
        encoding="utf-8",
    )

    assert check.dev_boundary_errors(tmp_path) == []


def test_dev_boundary_accepts_declared_staging_nonprod_identity(tmp_path: Path) -> None:
    _write_dev_boundary_fixture(tmp_path)
    (tmp_path / ".env.dev").write_text("POSTGRES_PASSWORD=dev-password\n", encoding="utf-8")
    registry = tmp_path / "env.registry.toml"
    registry.write_text(
        registry.read_text(encoding="utf-8")
        .replace(
            'key = "TWITCH_CLIENT_ID"\nscopes = ["shared"]\nsensitive = false',
            'key = "TWITCH_CLIENT_ID"\nscopes = ["shared"]\n'
            "sensitive = false\nnonprod_shared = true",
        )
        .replace(
            'key = "TWITCH_CLIENT_SECRET"\nscopes = ["shared"]',
            'key = "TWITCH_CLIENT_SECRET"\nscopes = ["shared"]\nnonprod_shared = true',
        ),
        encoding="utf-8",
    )
    (tmp_path / ".github/variables/stg.env").write_text(
        "TWITCH_CLIENT_ID=stg-client\n", encoding="utf-8"
    )
    (tmp_path / ".github/secrets/stg.env").write_text(
        "TWITCH_CLIENT_SECRET=stg-secret\n", encoding="utf-8"
    )
    (tmp_path / "backend/shared.dev.env").write_text(
        "DATABASE_URL=postgresql://dev:password@localhost:5432/dev\n"
        "TWITCH_CLIENT_ID=stg-client\n"
        "TWITCH_CLIENT_SECRET=stg-secret\n",
        encoding="utf-8",
    )

    assert check.dev_boundary_errors(tmp_path) == []


def test_dev_boundary_rejects_undeclared_staging_secret(tmp_path: Path) -> None:
    _write_dev_boundary_fixture(tmp_path)
    (tmp_path / ".github/secrets/stg.env").write_text(
        "POSTGRES_PASSWORD=stg-password\n", encoding="utf-8"
    )
    (tmp_path / ".env.dev").write_text("POSTGRES_PASSWORD=stg-password\n", encoding="utf-8")
    (tmp_path / "backend/shared.dev.env").write_text(
        "DATABASE_URL=postgresql://dev:password@localhost:5432/dev\nTWITCH_CLIENT_ID=dev-client\n",
        encoding="utf-8",
    )

    assert check.dev_boundary_errors(tmp_path) == ["dev value reuses stg secret: POSTGRES_PASSWORD"]


def test_dev_boundary_rejects_inconsistent_database_urls(tmp_path: Path) -> None:
    _write_dev_boundary_fixture(tmp_path)
    (tmp_path / ".env.dev").write_text(
        "POSTGRES_USER=dev_user\n"
        "POSTGRES_PASSWORD=dev_password\n"
        "POSTGRES_DB=dev_db\n"
        "DOCKER_DATABASE_URL=postgresql://dev_user:wrong@localhost:5432/dev_db\n",
        encoding="utf-8",
    )
    (tmp_path / "backend/shared.dev.env").write_text(
        "DATABASE_URL=postgresql://wrong:dev_password@localhost:5432/other_db\n"
        "TWITCH_CLIENT_ID=dev-client\n",
        encoding="utf-8",
    )

    errors = check.dev_boundary_errors(tmp_path)

    assert errors == [
        "dev DATABASE_URL must match POSTGRES_* credentials",
        "dev DOCKER_DATABASE_URL must match POSTGRES_* credentials",
        "dev DOCKER_DATABASE_URL must use postgres host",
    ]
    assert "dev_password" not in " ".join(errors)


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


def test_sync_keeps_blank_optional_values_commented(tmp_path: Path) -> None:
    example = tmp_path / "optional.env.example"
    example.write_text("# OPTIONAL_TOKEN=\nREQUIRED_TOKEN=\n", encoding="utf-8")

    rendered = sync._render(
        example,
        "shared",
        {("shared", "OPTIONAL_TOKEN"): "", ("shared", "REQUIRED_TOKEN"): ""},
    )

    assert rendered == "# OPTIONAL_TOKEN=\nREQUIRED_TOKEN=\n"


def test_sync_dev_can_overlay_declared_staging_nonprod_values(tmp_path: Path) -> None:
    (tmp_path / "env.registry.toml").write_text(
        """
[[var]]
key = "POSTGRES_PASSWORD"
scopes = ["root"]

[[var]]
key = "TWITCH_CLIENT_ID"
scopes = ["shared"]
nonprod_shared = true
[var.ci]
file = "shared"
source = "var:TWITCH_CLIENT_ID"
scope = "env"

[[var]]
key = "TWITCH_CLIENT_SECRET"
scopes = ["shared"]
nonprod_shared = true
[var.ci]
file = "shared"
source = "secret:TWITCH_CLIENT_SECRET"
scope = "env"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.example").write_text("POSTGRES_PASSWORD=\n", encoding="utf-8")
    (tmp_path / ".env.dev").write_text("POSTGRES_PASSWORD=dev-db\n", encoding="utf-8")
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend/shared.env.example").write_text(
        "TWITCH_CLIENT_ID=\nTWITCH_CLIENT_SECRET=\n", encoding="utf-8"
    )
    (tmp_path / "backend/shared.dev.env").write_text(
        "TWITCH_CLIENT_ID=old-dev-id\nTWITCH_CLIENT_SECRET=old-dev-secret\n",
        encoding="utf-8",
    )
    for kind in ("variables", "secrets"):
        (tmp_path / f".github/{kind}").mkdir(parents=True)
    (tmp_path / ".github/variables/stg.env").write_text(
        "TWITCH_CLIENT_ID=stg-id\n", encoding="utf-8"
    )
    (tmp_path / ".github/secrets/stg.env").write_text(
        "TWITCH_CLIENT_SECRET=stg-secret\n", encoding="utf-8"
    )

    outputs = sync.normalized_outputs(tmp_path, "dev", from_stg=True)

    assert outputs[tmp_path / ".env.dev"] == "POSTGRES_PASSWORD=dev-db\n"
    assert outputs[tmp_path / "backend/shared.dev.env"] == (
        "TWITCH_CLIENT_ID=stg-id\nTWITCH_CLIENT_SECRET=stg-secret\n"
    )


def test_sync_rejects_staging_overlay_for_non_dev_target(tmp_path: Path) -> None:
    try:
        sync.normalized_outputs(tmp_path, "prod", from_stg=True)
    except ValueError as exc:
        assert str(exc) == "--from-stg is only valid for target dev"
    else:
        raise AssertionError("staging overlay was accepted for production")


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


def _write_github_env_files(tmp_path: Path) -> None:
    examples = {
        ".github/variables/base.env.example": "BOT_ID=\nLOG_LEVEL=INFO\n",
        ".github/variables/stg.env.example": "API_URL=\nENVIRONMENT=staging\n",
        ".github/variables/prod.env.example": "API_URL=\nENVIRONMENT=production\n",
        ".github/secrets/base.env.example": "OPENROUTER_API_KEY=\n",
        ".github/secrets/stg.env.example": "TOKEN=\n",
        ".github/secrets/prod.env.example": "TOKEN=\n",
    }
    actual = {
        ".github/variables/base.env": "API_URL=base-url\nLOG_LEVEL=DEBUG\n",
        ".github/variables/stg.env": "API_URL=stg-url\nENVIRONMENT=production\n",
        ".github/variables/prod.env": "API_URL=prod-url\nENVIRONMENT=staging\n",
        ".github/secrets/base.env": "OPENROUTER_API_KEY=secret-key\n",
        ".github/secrets/stg.env": "BOT_ID=123\nTOKEN=stg-token\n",
        ".github/secrets/prod.env": "BOT_ID=123\nTOKEN=prod-token\n",
    }
    for name, content in (examples | actual).items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_sync_formats_all_github_files_and_preserves_values(tmp_path: Path) -> None:
    _write_github_env_files(tmp_path)

    outputs = sync.normalized_outputs(tmp_path, "gh")

    assert outputs[tmp_path / ".github/variables/base.env"] == ("BOT_ID=123\nLOG_LEVEL=DEBUG\n")
    assert outputs[tmp_path / ".github/variables/stg.env"] == (
        "API_URL=stg-url\nENVIRONMENT=staging\n"
    )
    assert outputs[tmp_path / ".github/variables/prod.env"] == (
        "API_URL=prod-url\nENVIRONMENT=production\n"
    )
    assert outputs[tmp_path / ".github/secrets/base.env"] == ("OPENROUTER_API_KEY=secret-key\n")
    assert outputs[tmp_path / ".github/secrets/stg.env"] == "TOKEN=stg-token\n"
    assert outputs[tmp_path / ".github/secrets/prod.env"] == "TOKEN=prod-token\n"


def test_sync_github_refuses_unknown_keys_without_printing_values(tmp_path: Path) -> None:
    _write_github_env_files(tmp_path)
    path = tmp_path / ".github/secrets/base.env"
    path.write_text(
        path.read_text(encoding="utf-8") + "LEGACY_KEY=legacy-secret\n",
        encoding="utf-8",
    )

    try:
        sync.normalized_outputs(tmp_path, "gh")
    except ValueError as exc:
        message = str(exc)
        assert "unknown keys: LEGACY_KEY" in message
        assert "legacy-secret" not in message
    else:
        raise AssertionError("unknown GitHub key was accepted")

    outputs = sync.normalized_outputs(tmp_path, "gh", drop_unknown=True)
    assert "LEGACY_KEY" not in "".join(outputs.values())


def test_sync_github_refuses_cross_environment_base_conflicts(tmp_path: Path) -> None:
    _write_github_env_files(tmp_path)
    stg = tmp_path / ".github/secrets/stg.env"
    prod = tmp_path / ".github/secrets/prod.env"
    stg.write_text(
        stg.read_text(encoding="utf-8").replace("BOT_ID=123", "BOT_ID=stg-secret"),
        encoding="utf-8",
    )
    prod.write_text(
        prod.read_text(encoding="utf-8").replace("BOT_ID=123", "BOT_ID=prod-secret"),
        encoding="utf-8",
    )

    try:
        sync.normalized_outputs(tmp_path, "gh")
    except ValueError as exc:
        message = str(exc)
        assert "conflicting values for BOT_ID" in message
        assert "stg-secret" not in message
        assert "prod-secret" not in message
    else:
        raise AssertionError("conflicting GitHub values were accepted")


def test_sync_github_moves_retired_base_credential_to_prod_only(tmp_path: Path) -> None:
    examples = {
        ".github/variables/base.env.example": "",
        ".github/variables/stg.env.example": "",
        ".github/variables/prod.env.example": "",
        ".github/secrets/base.env.example": "",
        ".github/secrets/stg.env.example": "# PROVIDER_KEY=\n",
        ".github/secrets/prod.env.example": "# PROVIDER_KEY=\n",
    }
    actual = {
        ".github/variables/base.env": "",
        ".github/variables/stg.env": "",
        ".github/variables/prod.env": "",
        ".github/secrets/base.env": "PROVIDER_KEY=existing-prod-key\n",
        ".github/secrets/stg.env": "",
        ".github/secrets/prod.env": "",
    }
    for name, content in (examples | actual).items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    outputs = sync.normalized_outputs(tmp_path, "gh")

    assert outputs[tmp_path / ".github/secrets/base.env"] == "\n"
    assert outputs[tmp_path / ".github/secrets/stg.env"] == "# PROVIDER_KEY=\n"
    assert outputs[tmp_path / ".github/secrets/prod.env"] == "PROVIDER_KEY=existing-prod-key\n"
