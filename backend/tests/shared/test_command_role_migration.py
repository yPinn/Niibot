"""Regression contract for builtin command role repair migration 147."""

from pathlib import Path

from shared.builtin_commands import COMMAND_RESERVED_NAMES

MIGRATION = (
    Path(__file__).parents[2]
    / "shared"
    / "migrations"
    / "versions"
    / "147_repair_builtin_command_roles.sql"
)


def test_migration_only_tightens_buggy_builtin_everyone_rows() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "command_type = 'builtin'" in sql
    assert "min_role = 'everyone'" in sql
    assert "command_name = 'subcount'" in sql
    assert "command_name IN ('so', 'condemn', 'marker', 'winner')" in sql
    assert "SET min_role = 'broadcaster'" in sql
    assert "SET min_role = 'moderator'" in sql


def test_namespace_repair_migrations_track_the_complete_reserved_registry() -> None:
    versions = Path(__file__).parents[2] / "shared" / "migrations" / "versions"
    baseline_sql = (versions / "150_disable_reserved_custom_command_conflicts.sql").read_text(
        encoding="utf-8"
    )
    concise_alias_sql = (versions / "152_disable_concise_alias_conflicts.sql").read_text(
        encoding="utf-8"
    )
    sql = f"{baseline_sql}\n{concise_alias_sql}".lower()

    assert "set enabled = false" in sql
    assert "command_type = 'custom'" in sql
    assert "command_aliases" in sql
    assert "set command_name =" in baseline_sql.lower()
    assert "__legacy_" in baseline_sql.lower()
    for name in COMMAND_RESERVED_NAMES:
        escaped = name.lower().replace("'", "''")
        assert f"('{escaped}')" in sql


def test_concise_alias_migration_only_disables_new_namespace_conflicts() -> None:
    path = (
        Path(__file__).parents[2]
        / "shared"
        / "migrations"
        / "versions"
        / "152_disable_concise_alias_conflicts.sql"
    )
    sql = path.read_text(encoding="utf-8").lower()

    for alias in {"標題", "抽", "選", "刪"}:
        assert alias in COMMAND_RESERVED_NAMES
        assert f"('{alias}')" in sql
    assert "command_type = 'custom'" in sql
    assert "command.enabled = true" in sql
    assert "set enabled = false" in sql
    assert "command_type = 'builtin'" in sql
    assert "update command_aliases" in sql
    for command_name, old_alias, new_alias in {
        ("title", "台標", "標題"),
        ("winner", "幸運兒", "抽"),
        ("choose", "選擇", "選"),
        ("del", "刪除", "刪"),
    }:
        assert f"('{command_name}', '{old_alias}', '{new_alias}')" in sql
    assert "delete from command_configs" not in sql
    assert "drop " not in sql
