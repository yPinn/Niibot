from pathlib import Path

_VERSIONS = Path(__file__).parents[2] / "shared" / "migrations" / "versions"


def test_opening_segment_backfill_is_idempotent_and_preserves_legacy_skips() -> None:
    sql = (_VERSIONS / "141_backfill_stream_schedule_opening_segments.sql").read_text(
        encoding="utf-8"
    )

    assert "schedules.title_template <> ''" in sql
    assert "segments.offset_minutes = 0" in sql
    assert "ON CONFLICT (schedule_id, offset_minutes) DO NOTHING" in sql
    assert "DROP COLUMN" not in sql


def test_occurrence_exception_schema_is_tenant_scoped_and_unique() -> None:
    sql = (_VERSIONS / "142_add_stream_schedule_occurrence_exceptions.sql").read_text(
        encoding="utf-8"
    )

    assert "channel_id" in sql
    assert "UNIQUE (recurring_schedule_id, occurrence_date)" in sql
    assert "replacement_schedule_id" in sql
    assert "kind IN ('cancelled', 'replacement')" in sql
    assert sql.count("FOREIGN KEY (channel_id,") == 2
    assert "REFERENCES stream_schedules(channel_id, id)" in sql


def test_legacy_skip_migration_is_idempotent_and_disables_sentinels() -> None:
    sql = (_VERSIONS / "143_migrate_stream_schedule_skip_sentinels.sql").read_text(encoding="utf-8")

    assert "sentinel.title_template = ''" in sql
    assert "NOT EXISTS" in sql
    assert "ON CONFLICT (recurring_schedule_id, occurrence_date) DO NOTHING" in sql
    assert "SET enabled = FALSE" in sql


def test_schedule_bounds_preserve_legacy_rows_and_guard_new_writes() -> None:
    sql = (_VERSIONS / "144_harden_stream_schedule_bounds.sql").read_text(encoding="utf-8")

    assert "duration_minutes BETWEEN 30 AND 1380" in sql
    assert "char_length(title_template) <= 140" in sql
    assert sql.count("NOT VALID") >= 2
    assert "NEW.offset_minutes >= schedule_duration" in sql
    assert "offset_minutes >= NEW.duration_minutes" in sql


def test_twitch_publish_schema_is_tenant_scoped_and_transactionally_enqueued() -> None:
    sql = (_VERSIONS / "149_add_stream_schedule_twitch_publish.sql").read_text(encoding="utf-8")

    assert "stream_schedule_twitch_states" in sql
    assert "stream_schedule_twitch_occurrences" in sql
    assert "stream_schedule_publish_queue" in sql
    assert "channel_id" in sql
    assert "twitch_segment_id" in sql
    assert "payload_fingerprint" in sql
    assert "generation" in sql
    assert "FOR EACH ROW EXECUTE FUNCTION fn_enqueue_stream_schedule_publish" in sql
    assert "stream_schedule_segments" in sql
    assert "stream_schedule_occurrence_exceptions" in sql
    assert "AFTER UPDATE OF scopes, credential_revision, requires_reauth ON tokens" in sql
    assert "NEW.token_type <> 'broadcaster'" in sql
    assert "COALESCE(NEW.offset_minutes, OLD.offset_minutes)" not in sql
