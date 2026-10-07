"""Static contract for migration 106 (video_queue NOTIFY trigger)."""

from pathlib import Path

_VERSIONS = Path(__file__).parents[2] / "shared" / "migrations" / "versions"


def test_video_queue_notify_trigger_uses_search_path_and_covers_mutable_columns():
    sql = (_VERSIONS / "106_notify_video_queue_updates.sql").read_text(encoding="utf-8")

    assert "pg_notify('video_queue_updates'" in sql
    # 104 omitted this and left a latent search-path-hijack risk; must not repeat it.
    assert "SET search_path = public" in sql

    # INSERT and UPDATE must be split — Postgres forbids a WHEN clause
    # referencing OLD on a trigger that also fires for INSERT.
    assert "AFTER INSERT ON video_queue" in sql
    assert "AFTER UPDATE OF" in sql

    mutable_columns = (
        "status",
        "priority",
        "created_at",
        "started_at",
        "duration_seconds",
        "title",
    )
    update_clause_start = sql.index("AFTER UPDATE OF")
    update_clause = sql[update_clause_start : sql.index("EXECUTE FUNCTION", update_clause_start)]
    for column in mutable_columns:
        assert column in update_clause, f"{column} missing from AFTER UPDATE OF column list"
        assert f"OLD.{column} IS DISTINCT FROM NEW.{column}" in update_clause

    # video_queue_settings intentionally has no trigger (see migration comment) —
    # check there is no CREATE TRIGGER targeting it, not just absence of the name.
    assert "ON video_queue_settings" not in sql


def test_overlay_capability_migration_uses_unique_random_uuid_default():
    sql = (_VERSIONS / "132_video_queue_overlay_capability.sql").read_text(encoding="utf-8")

    assert "overlay_key UUID NOT NULL DEFAULT gen_random_uuid()" in sql
    assert "CREATE UNIQUE INDEX" in sql
    assert "ON video_queue_settings (overlay_key)" in sql


def test_volume_migration_has_safe_default_and_database_bounds():
    sql = (_VERSIONS / "133_video_queue_volume.sql").read_text(encoding="utf-8")

    assert "volume_percent SMALLINT NOT NULL DEFAULT 100" in sql
    assert "CHECK (volume_percent BETWEEN 0 AND 100)" in sql


def test_rankings_migration_tracks_real_playback_and_provider_scoped_blocks():
    sql = (_VERSIONS / "135_video_queue_rankings.sql").read_text(encoding="utf-8")

    assert "playback_started_at TIMESTAMPTZ" in sql
    assert "playback_signal TEXT" in sql
    assert "end_reason TEXT" in sql
    assert "played_seconds INTEGER" in sql
    assert "idx_video_queue_rankings_global" in sql
    assert "idx_video_queue_rankings_channel" in sql

    assert "ALTER TABLE video_queue_blocklist" in sql
    assert "ADD COLUMN IF NOT EXISTS video_type TEXT" in sql
    assert "COALESCE(video_type, '*')" in sql
    assert "kind IN ('video', 'creator')" in sql
    assert "'youtube', 'twitch_clip', 'twitch_vod', 'bilibili', 'instagram_reel'" in sql


def test_chat_skip_end_reason_matches_the_repository_allowlist():
    from shared.repositories.video_queue import END_REASONS

    sql = (_VERSIONS / "153_video_queue_chat_skip_end_reason.sql").read_text(encoding="utf-8")
    assert "DROP CONSTRAINT IF EXISTS chk_video_queue_end_reason" in sql
    for reason in END_REASONS:
        assert f"'{reason}'" in sql, f"{reason} missing from the end_reason CHECK"


def test_np_catalog_migration_moves_legacy_custom_rows_aside():
    sql = (_VERSIONS / "154_np_builtin_catalog.sql").read_text(encoding="utf-8")
    assert "command.command_type = 'custom'" in sql
    assert "lower(command.command_name) = 'np'" in sql
    assert "'__legacy_'" in sql
    assert "enabled = FALSE" in sql


def test_live_insert_migration_wakes_the_queue_stream_and_bounds_the_row():
    sql = (_VERSIONS / "155_video_queue_live_insert.sql").read_text(encoding="utf-8")

    # Same wake channel as 106, hardened the same way.
    assert "pg_notify('video_queue_updates'" in sql
    assert "SET search_path = public" in sql
    # DELETE (stop) must wake the overlay too, and has no NEW row.
    assert "AFTER INSERT OR UPDATE OR DELETE ON video_queue_inserts" in sql
    assert "COALESCE(NEW.channel_id, OLD.channel_id)" in sql
    # One insert per channel; removed with the channel.
    assert (
        "channel_id     TEXT NOT NULL UNIQUE REFERENCES channels(channel_id) ON DELETE CASCADE"
        in sql
    )
    assert "CHECK (source_type IN ('twitch_live', 'youtube_live'))" in sql


def test_shared_volume_migration_drops_the_live_volume_and_lowers_the_default():
    sql = (_VERSIONS / "157_video_queue_shared_volume.sql").read_text(encoding="utf-8")

    assert "DROP COLUMN IF EXISTS insert_volume_percent" in sql
    assert "DROP CONSTRAINT IF EXISTS chk_video_queue_insert_volume_percent" in sql
    assert "ALTER COLUMN volume_percent SET DEFAULT 50" in sql
