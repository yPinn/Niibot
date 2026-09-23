"""Static contracts for check-in and community overlay migrations."""

from pathlib import Path

_VERSIONS = Path(__file__).parents[2] / "shared" / "migrations" / "versions"


def test_checkin_and_overlay_schema_has_tenant_and_integrity_guards():
    sql = (_VERSIONS / "093_add_checkin_overlay_infra.sql").read_text(encoding="utf-8")

    for table in (
        "checkin_settings",
        "viewer_checkins",
        "community_overlay_channels",
        "community_overlay_events",
    ):
        assert f"CREATE TABLE {table}" in sql
        assert f"p_{table}_tenant" in sql

    assert "UNIQUE (channel_id, user_id, checkin_date)" in sql
    assert "UNIQUE (channel_id, idempotency_key)" in sql
    assert sql.count("REFERENCES channels(channel_id) ON DELETE CASCADE") >= 4
    assert "jsonb_typeof(payload) = 'object'" in sql
    assert "idx_community_overlay_events_cursor" in sql
    assert "idx_community_overlay_events_expiry" in sql
    assert "ENABLE ROW LEVEL SECURITY" not in sql


def test_quotes_schema_has_tenant_scope_and_stays_staged():
    sql = (_VERSIONS / "126_add_quotes.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE quotes" in sql
    assert "p_quotes_tenant" in sql
    assert "REFERENCES channels(channel_id) ON DELETE CASCADE" in sql
    assert "UNIQUE (channel_id, quote_number)" in sql
    assert "ENABLE ROW LEVEL SECURITY" not in sql


def test_duplicate_template_count_upgrade_preserves_customized_rows():
    sql = (_VERSIONS / "094_checkin_duplicate_count_template.sql").read_text(encoding="utf-8")

    assert "ALTER COLUMN duplicate_template" in sql
    assert "$(count)" in sql
    assert "WHERE duplicate_template = '$(@user) 今天已經簽到過了！'" in sql


def test_overlay_theme_schema_keeps_drafts_tenant_scoped_and_revisions_immutable():
    sql = (_VERSIONS / "095_add_community_overlay_themes.sql").read_text(encoding="utf-8")

    for table in ("community_overlay_profiles", "community_overlay_revisions"):
        assert f"CREATE TABLE {table}" in sql
        assert f"p_{table}_tenant" in sql

    assert sql.count("REFERENCES channels(channel_id) ON DELETE CASCADE") >= 2
    assert "draft_theme" in sql
    assert "published_revision_id" in sql
    assert "jsonb_typeof(draft_theme) = 'object'" in sql
    assert "jsonb_typeof(theme) = 'object'" in sql
    assert "UNIQUE (channel_id, revision_number)" in sql
    assert "DEFERRABLE INITIALLY DEFERRED" in sql
    assert "trg_community_overlay_revisions_immutable" in sql
    assert "ENABLE ROW LEVEL SECURITY" not in sql

    hardening_sql = (_VERSIONS / "096_harden_community_overlay_themes.sql").read_text(
        encoding="utf-8"
    )
    assert "ADD COLUMN draft_version BIGINT NOT NULL DEFAULT 1" in hardening_sql
    assert "BEFORE UPDATE OR DELETE ON community_overlay_revisions" in hardening_sql

    cascade_sql = (_VERSIONS / "097_allow_overlay_revision_channel_cascade.sql").read_text(
        encoding="utf-8"
    )
    assert "TG_OP = 'DELETE' AND pg_trigger_depth() > 1" in cascade_sql

    block_sql = (_VERSIONS / "103_scope_overlay_themes_by_block.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN block_type TEXT NOT NULL DEFAULT 'checkin'" in block_sql
    assert "PRIMARY KEY (channel_id, block_type)" in block_sql
    assert "UNIQUE (channel_id, block_type, revision_number)" in block_sql
    assert "FOREIGN KEY (channel_id, block_type, published_revision_id)" in block_sql


def test_read_only_checkin_redemption_expands_schema_without_manage_scope():
    sql = (_VERSIONS / "098_add_checkin_redemption_binding.sql").read_text(encoding="utf-8")

    assert "ADD COLUMN reward_id TEXT" in sql
    assert "'checkin'" in sql
    assert "CREATE UNIQUE INDEX" in sql
    assert "WHERE reward_id IS NOT NULL" in sql

    from shared.twitch_scopes import BROADCASTER_SCOPES

    assert "channel:read:redemptions" in BROADCASTER_SCOPES
    assert "channel:manage:redemptions" not in BROADCASTER_SCOPES


def test_overlay_stream_notifications_are_wake_only_and_transaction_safe() -> None:
    sql = (_VERSIONS / "104_notify_community_overlay_updates.sql").read_text(encoding="utf-8")

    assert "pg_notify('community_overlay_updates'" in sql
    assert "AFTER INSERT ON community_overlay_events" in sql
    assert "AFTER UPDATE OF published_revision_id ON community_overlay_profiles" in sql
    assert "AFTER UPDATE OF public_key, enabled ON community_overlay_channels" in sql
    function_body = sql.split("CREATE OR REPLACE FUNCTION", 1)[1].split("$$ LANGUAGE", 1)[0]
    assert "channel_id" in function_body
    assert "public_key" not in function_body
    assert "payload" not in function_body


def test_checkin_reply_delay_was_initially_bounded_and_opt_in() -> None:
    sql = (_VERSIONS / "105_add_checkin_reply_delay.sql").read_text(encoding="utf-8")

    assert "ADD COLUMN reply_delay_seconds SMALLINT NOT NULL DEFAULT 0" in sql
    assert "CHECK (reply_delay_seconds BETWEEN 0 AND 30)" in sql


def test_checkin_reply_delay_default_becomes_five_without_rewriting_rows() -> None:
    sql = (_VERSIONS / "137_set_checkin_reply_delay_default.sql").read_text(encoding="utf-8")

    assert "ALTER COLUMN reply_delay_seconds SET DEFAULT 5" in sql
    assert "UPDATE checkin_settings" not in sql
