"""Static safety contracts for Twitch authorization lifecycle storage."""

from pathlib import Path

_VERSIONS = Path(__file__).parents[2] / "shared" / "migrations" / "versions"


def test_authorization_lifecycle_migration_is_additive_and_bounded() -> None:
    sql = (_VERSIONS / "128_add_twitch_authorization_lifecycle.sql").read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS last_checked_at" in sql
    assert "ADD COLUMN IF NOT EXISTS last_validated_at" in sql
    assert "ADD COLUMN IF NOT EXISTS invalidated_at" in sql
    assert "ADD COLUMN IF NOT EXISTS validation_error_code" in sql
    assert "ADD COLUMN IF NOT EXISTS session_version" in sql
    assert "DEFAULT 1" in sql
    assert "provider_unavailable" in sql
    assert "DELETE FROM" not in sql.upper()
    assert "DROP TABLE" not in sql.upper()
    assert "UPDATE tokens" not in sql


def test_authorization_lifecycle_migration_indexes_due_checks() -> None:
    sql = (_VERSIONS / "128_add_twitch_authorization_lifecycle.sql").read_text(encoding="utf-8")

    assert "idx_tokens_authorization_check_due" in sql
    assert "last_checked_at" in sql


def test_credential_revision_migration_is_additive_and_hot_reloads_broadcasters() -> None:
    sql = (_VERSIONS / "138_add_twitch_credential_revision.sql").read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS credential_revision" in sql
    assert "DEFAULT 1" in sql
    assert "NEW.credential_revision IS DISTINCT FROM OLD.credential_revision" in sql
    assert "'scopes_changed', NEW.scopes IS DISTINCT FROM OLD.scopes" in sql
    assert "'reauth_cleared', OLD.requires_reauth AND NOT NEW.requires_reauth" in sql
    assert "pg_notify('token_reauth'" in sql
    assert "DELETE FROM" not in sql.upper()
    assert "DROP TABLE" not in sql.upper()
