"""Static safety contracts for Bot account Phase 0 migrations."""

from pathlib import Path

_VERSIONS = Path(__file__).parents[2] / "shared" / "migrations" / "versions"


def test_token_encryption_expand_is_schema_only_and_forward_compatible():
    sql = (_VERSIONS / "100_expand_twitch_token_encryption.sql").read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS encryption_version" in sql
    assert "DEFAULT 0" in sql
    assert "CHECK (encryption_version IN (0, 1))" in sql
    assert "ON DELETE SET NULL" in sql
    assert "ON DELETE CASCADE" not in sql
    assert "UPDATE tokens" not in sql


def test_expand_migration_does_not_prematurely_require_encrypted_rows():
    sql = (_VERSIONS / "100_expand_twitch_token_encryption.sql").read_text(encoding="utf-8")

    assert "CHECK (encryption_version = 1)" not in sql
