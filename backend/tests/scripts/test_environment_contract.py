"""Environment isolation contracts for Compose, scripts, and CI."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def _compose(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def test_compose_files_use_short_explicit_environment_names() -> None:
    assert (ROOT / "compose.yaml").is_file()
    for env in ("dev", "stg", "prod"):
        assert (ROOT / f"compose.{env}.yaml").is_file()

    assert not list(ROOT.glob("docker-compose*.yml"))


def test_base_compose_has_no_fixed_container_names_or_host_ports() -> None:
    compose = _compose("compose.yaml")

    for service in compose["services"].values():
        assert "container_name" not in service
        assert "ports" not in service


def test_host_port_matrix_is_explicit_and_loopback_only() -> None:
    dev = _compose("compose.dev.yaml")["services"]
    stg = _compose("compose.stg.yaml")["services"]
    prod = _compose("compose.prod.yaml")["services"]

    assert dev["api"]["ports"] == ["127.0.0.1:8000:8000"]
    assert dev["postgres"]["ports"] == ["127.0.0.1:5432:5432"]
    assert dev["twitch-bot"]["ports"] == ["127.0.0.1:4344:4344"]
    assert dev["discord-bot"]["ports"] == ["127.0.0.1:8080:8080"]
    assert dev["instafix"]["ports"] == ["127.0.0.1:3002:3000"]

    assert stg["api"]["ports"] == ["127.0.0.1:18001:8000"]
    assert prod["api"]["ports"] == ["127.0.0.1:18000:8000"]
    for services in (stg, prod):
        for name in ("postgres", "twitch-bot", "discord-bot", "instafix"):
            assert "ports" not in services.get(name, {})


def test_overlays_use_matching_env_files() -> None:
    expected = {
        "dev": ("./backend/shared.dev.env", ".env.dev"),
        "stg": ("./backend/shared.stg.env", ".env.stg"),
        "prod": ("./backend/shared.prod.env", ".env.prod"),
    }
    for env, (shared, service) in expected.items():
        services = _compose(f"compose.{env}.yaml")["services"]
        assert services["api"]["env_file"] == [shared, f"./backend/api/{service}"]
        assert services["twitch-bot"]["env_file"] == [
            shared,
            f"./backend/twitch/{service}",
        ]


def test_overlays_use_environment_scoped_images() -> None:
    for env in ("dev", "stg", "prod"):
        services = _compose(f"compose.{env}.yaml")["services"]
        assert services["migrate"]["image"] == f"nb-api-{env}"
        assert services["api"]["image"] == f"nb-api-{env}"
        assert services["twitch-bot"]["image"] == f"nb-twitch-{env}"
        assert services["discord-bot"]["image"] == f"nb-discord-{env}"


def test_stack_wrapper_uses_explicit_project_and_env_file() -> None:
    script = (ROOT / "scripts" / "stack.sh").read_text(encoding="utf-8")

    assert 'PROJECT="niibot-$TARGET"' in script
    assert '--env-file "$ENV_FILE"' in script
    assert '-f "$ROOT/compose.yaml"' in script
    assert '-f "$ROOT/compose.$TARGET.yaml"' in script
    assert "config --quiet" in script
    assert 'rm -rf -- "$ROOT/data/staging/postgres"' in script
    assert "prod reset is disabled" in script


def test_script_tree_uses_domain_directories_and_short_names() -> None:
    expected = (
        "backend/scripts/db/migrate.py",
        "backend/scripts/twitch_ops/oauth.py",
        "backend/scripts/discord_ops/commands.py",
        "backend/scripts/checkin/backfill.py",
        "backend/scripts/ai/eval.py",
        "scripts/env/gen.py",
        "scripts/ci/paths.py",
        "scripts/assets/badges.py",
        "scripts/stack.sh",
    )
    for path in expected:
        assert (ROOT / path).is_file()

    old_names = (
        "scripts/gen_env.py",
        "scripts/env.sh",
        "scripts/staging.sh",
        "backend/scripts/db_migrate.py",
        "backend/scripts/twitch_oauth.py",
        "backend/scripts/discord_cmds.py",
    )
    for path in old_names:
        assert not (ROOT / path).exists()


def test_nested_shell_scripts_resolve_the_repository_root() -> None:
    backup = (ROOT / "backend/scripts/db/backup.sh").read_text(encoding="utf-8")

    assert 'dirname "$0")/../../..' in backup
    assert "xargs -r" not in backup


def test_sensitive_env_and_backup_writers_use_private_permissions() -> None:
    for relative in (
        "scripts/env/manage.sh",
        "scripts/env/write_ci.sh",
        "backend/scripts/db/backup.sh",
        ".github/push.sh",
    ):
        script = (ROOT / relative).read_text(encoding="utf-8")
        assert "umask 077" in script


def test_dev_database_mutators_enforce_a_local_target() -> None:
    for relative in (
        "backend/scripts/db/clear.py",
        "backend/scripts/db/seed.py",
        "backend/scripts/twitch_ops/oauth.py",
    ):
        script = (ROOT / relative).read_text(encoding="utf-8")
        assert "require_dev_database" in script


def test_env_migration_requires_an_explicit_target() -> None:
    script = (ROOT / "scripts/env/manage.sh").read_text(encoding="utf-8")

    assert "migrate <dev|stg|prod>" in script
    assert 'local env="${1:-}"' in script
    assert "mapfile" not in script


def test_github_sync_validates_structure_and_reports_scope_drift() -> None:
    push = (ROOT / ".github/push.sh").read_text(encoding="utf-8")
    pull = (ROOT / ".github/pull.sh").read_text(encoding="utf-8")

    assert "scripts/env/check.py" in push
    assert "base-only" in pull
    assert "trap 'rm -f -- \"${TEMP_FILES[@]}\"' EXIT" in push


def test_deploy_checks_private_services_via_compose_health() -> None:
    workflow = (ROOT / ".github" / "workflows" / "_deploy.yml").read_text(encoding="utf-8")

    assert "docker-compose" not in workflow
    assert "localhost:4344" not in workflow
    assert "localhost:8080" not in workflow
    assert "niibot-prod" in workflow
    assert "niibot-stg" in workflow
    assert "${PROJECT_FLAG:-} ${ENV_FILE_FLAG:-} build" in workflow
    assert "${PROJECT_FLAG:-} ${ENV_FILE_FLAG:-} pull instafix" in workflow
    assert "LEGACY_CONTAINER_PATTERN" in workflow
    assert "Refuse running legacy stack" in workflow
    for path_pattern in (
        r"^env\.registry\.toml$",
        r"^env\.manifest\.json$",
        r"^scripts/env/write_ci\.sh$",
    ):
        assert path_pattern in workflow
