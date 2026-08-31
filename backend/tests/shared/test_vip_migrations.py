"""Static contracts for timed VIP persistence."""

from pathlib import Path

_VERSIONS = Path(__file__).parents[2] / "shared" / "migrations" / "versions"


def test_timed_vip_schema_is_tenant_scoped_and_auditable():
    sql = (_VERSIONS / "099_add_timed_vip_management.sql").read_text(encoding="utf-8")

    for table in (
        "vip_channel_settings",
        "vip_reward_rules",
        "vip_entitlements",
        "vip_redemption_events",
    ):
        assert f"CREATE TABLE {table}" in sql
        assert f"p_{table}_tenant" in sql

    assert sql.count("REFERENCES channels(channel_id) ON DELETE CASCADE") >= 4
    assert "UNIQUE (channel_id, reward_id)" in sql
    assert "UNIQUE (channel_id, user_id)" in sql
    assert "UNIQUE (channel_id, redemption_id)" in sql
    assert "idx_vip_entitlements_due" in sql
    assert "idx_vip_redemption_events_review" in sql
    assert "ENABLE ROW LEVEL SECURITY" not in sql


def test_legacy_vip_binding_is_imported_as_three_calendar_months():
    sql = (_VERSIONS / "099_add_timed_vip_management.sql").read_text(encoding="utf-8")

    assert "INSERT INTO vip_reward_rules" in sql
    assert "FROM redemption_configs" in sql
    assert "action_type = 'vip'" in sql
    assert "reward_id IS NOT NULL" in sql
    assert "duration_months" in sql
    assert "3" in sql
