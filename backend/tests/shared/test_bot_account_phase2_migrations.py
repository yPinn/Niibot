"""Static schema contracts for the tenant-private Bot account registry."""

from pathlib import Path

_VERSIONS = Path(__file__).parents[2] / "shared" / "migrations" / "versions"


def test_bot_account_registry_is_tenant_scoped_and_secret_free():
    sql = (_VERSIONS / "101_add_bot_account_registry.sql").read_text(encoding="utf-8")

    for table in (
        "bot_accounts",
        "channel_bot_accounts",
        "bot_oauth_invites",
        "tenant_audit_events",
    ):
        assert f"CREATE TABLE {table}" in sql

    assert "PRIMARY KEY (channel_id, bot_user_id)" in sql
    assert "UNIQUE INDEX uq_bot_accounts_system_default" in sql
    assert "public_token_hash" in sql
    assert "state_nonce_hash" in sql
    assert "access_token" not in sql
    assert "refresh_token" not in sql
    assert "ENABLE ROW LEVEL SECURITY" not in sql


def test_bot_invites_have_one_time_and_expiry_constraints():
    sql = (_VERSIONS / "101_add_bot_account_registry.sql").read_text(encoding="utf-8")

    assert "expires_at > created_at" in sql
    assert "consumed_at" in sql
    assert "status IN ('pending', 'authorized', 'declined', 'expired')" in sql
    assert "purpose IN ('link_new', 'reauthorize', 'system_default_reset')" in sql


def test_expected_account_cannot_be_cleared_into_an_any_account_invite():
    sql = (_VERSIONS / "102_harden_bot_invite_expected_account.sql").read_text(encoding="utf-8")

    assert "bot_oauth_invites_expected_bot_user_id_fkey" in sql
    assert "ON DELETE CASCADE" in sql
    assert "ON DELETE SET NULL" not in sql
