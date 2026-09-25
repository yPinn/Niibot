"""Tests for shared.database helpers."""

from __future__ import annotations

import pytest

from shared.database import resolve_db_ssl


class TestResolveDbSsl:
    def test_local_host_prefers_ssl(self):
        assert resolve_db_ssl("postgresql://u:p@localhost:5432/db") == "prefer"
        assert resolve_db_ssl("postgresql://u:p@127.0.0.1/db") == "prefer"

    def test_container_host_prefers_ssl(self):
        assert resolve_db_ssl("postgresql://u:p@postgres/db") == "prefer"

    def test_remote_host_requires_ssl(self):
        assert resolve_db_ssl("postgresql://u:p@db.example.com:5432/db") == "require"
        assert resolve_db_ssl("postgresql://u:p@aws-0-eu.pooler.supabase.com:6543/db") == "require"

    def test_explicit_sslmode_in_dsn_is_left_alone(self):
        assert resolve_db_ssl("postgresql://u:p@db.example.com/db?sslmode=verify-full") is None

    def test_env_override_wins(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DB_SSL", "disable")
        assert resolve_db_ssl("postgresql://u:p@db.example.com/db") == "disable"

    def test_invalid_env_override_falls_back_to_autodetect(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DB_SSL", "bogus")
        assert resolve_db_ssl("postgresql://u:p@db.example.com/db") == "require"
        assert resolve_db_ssl("postgresql://u:p@localhost/db") == "prefer"
