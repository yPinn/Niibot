"""Static contracts for role-aware token insertion notifications."""

from pathlib import Path


def test_new_token_notification_includes_role_for_runtime_routing() -> None:
    sql = (
        Path(__file__).parents[2]
        / "shared"
        / "migrations"
        / "versions"
        / "151_add_token_type_to_new_token_notify.sql"
    ).read_text(encoding="utf-8")

    assert "'user_id', NEW.user_id" in sql
    assert "'token_type', NEW.token_type" in sql
    assert "SET search_path = public" in sql
