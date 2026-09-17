"""Static safety contracts for AI persona v2's additive migration."""

from pathlib import Path

_VERSIONS = Path(__file__).parents[2] / "shared" / "migrations" / "versions"


def test_persona_v2_migration_is_additive_bounded_and_default_off() -> None:
    sql = (_VERSIONS / "120_add_ai_persona_v2_memory.sql").read_text(encoding="utf-8")

    assert "ALTER TABLE ai_settings" in sql
    assert "DROP COLUMN" not in sql.upper()
    assert "audience_reference TEXT NOT NULL DEFAULT '大家'" in sql
    assert "tone_preset TEXT NOT NULL DEFAULT 'neutral'" in sql
    assert "catchphrase_frequency TEXT NOT NULL DEFAULT 'rare'" in sql
    assert "example_replies TEXT[] NOT NULL DEFAULT '{}'" in sql
    assert "memory_enabled BOOLEAN NOT NULL DEFAULT false" in sql
    assert "tone_preset IN ('neutral', 'witty', 'energetic', 'tsundere', 'calm')" in sql
    assert "catchphrase_frequency IN ('off', 'rare', 'occasional')" in sql
    assert "cardinality(example_replies) <= 3" in sql
