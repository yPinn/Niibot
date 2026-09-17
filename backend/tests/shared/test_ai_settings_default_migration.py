"""Static safety contract for AI settings factory-default changes."""

from pathlib import Path

_VERSIONS = Path(__file__).parents[2] / "shared" / "migrations" / "versions"


def test_default_preferences_migration_changes_schema_defaults_without_backfill() -> None:
    sql = (_VERSIONS / "123_ai_settings_default_preferences.sql").read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert "ALTER COLUMN catchphrase_frequency SET DEFAULT 'off'" in normalized
    assert "ALTER COLUMN refusal_style SET DEFAULT 'polite'" in normalized
    assert "ALTER COLUMN cooldown SET DEFAULT 30" in normalized
    assert "UPDATE " not in normalized.upper()
    assert "DROP " not in normalized.upper()
