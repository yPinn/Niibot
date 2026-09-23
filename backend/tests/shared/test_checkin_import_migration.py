"""Static schema contract for check-in carry-over imports."""

from pathlib import Path


def test_checkin_import_schema_is_tenant_safe_and_additive() -> None:
    path = (
        Path(__file__).parents[2]
        / "shared"
        / "migrations"
        / "versions"
        / "129_add_checkin_carryovers.sql"
    )
    sql = path.read_text(encoding="utf-8")

    for table in (
        "checkin_import_batches",
        "viewer_checkin_carryovers",
        "viewer_daily_checkin_streaks",
    ):
        assert f"CREATE TABLE {table}" in sql
        assert f"p_{table}_tenant" in sql

    assert "UNIQUE (id, channel_id)" in sql
    assert "PRIMARY KEY (channel_id, user_id)" in sql
    assert "FOREIGN KEY (import_batch_id, channel_id)" in sql
    assert "carried_total_days > 0" in sql
    assert "source_current_streak <= carried_total_days" in sql
    assert "ENABLE ROW LEVEL SECURITY" not in sql
    assert "WITH latest_island" in sql
