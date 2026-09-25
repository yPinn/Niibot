"""Tests for backend/scripts/_lib.py — env selection, db ctx, confirm."""

from __future__ import annotations

import argparse

import _lib
import pytest


class TestLoadEnv:
    def test_rejects_bad_env(self):
        with pytest.raises(ValueError, match="dev.*stg.*prod"):
            _lib.load_env("staging")

    def test_dev_loads_explicit_shared_env(self, tmp_path, monkeypatch):
        (tmp_path / "shared.dev.env").write_text("DATABASE_URL=postgres://dev\n", encoding="utf-8")
        monkeypatch.setattr(_lib, "BACKEND_DIR", tmp_path)
        monkeypatch.delenv("DATABASE_URL", raising=False)

        _lib.load_env("dev")

        assert _lib.database_url() == "postgres://dev"

    def test_stg_uses_stg_file_set(self, tmp_path, monkeypatch):
        (tmp_path / "shared.dev.env").write_text("DATABASE_URL=postgres://dev\n", encoding="utf-8")
        (tmp_path / "shared.stg.env").write_text("DATABASE_URL=postgres://stg\n", encoding="utf-8")
        monkeypatch.setattr(_lib, "BACKEND_DIR", tmp_path)
        monkeypatch.delenv("DATABASE_URL", raising=False)

        _lib.load_env("stg")

        assert _lib.database_url() == "postgres://stg"

    def test_local_override_and_service_file(self, tmp_path, monkeypatch):
        (tmp_path / "shared.dev.env").write_text("A=base\nB=base\n", encoding="utf-8")
        (tmp_path / "shared.dev.local.env").write_text("A=local\n", encoding="utf-8")
        (tmp_path / "twitch").mkdir()
        (tmp_path / "twitch" / ".env.dev").write_text("B=svc\n", encoding="utf-8")
        monkeypatch.setattr(_lib, "BACKEND_DIR", tmp_path)
        monkeypatch.delenv("A", raising=False)
        monkeypatch.delenv("B", raising=False)

        _lib.load_env("dev", service="twitch")

        import os

        assert os.environ["A"] == "local"
        assert os.environ["B"] == "svc"

    def test_missing_shared_env_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_lib, "BACKEND_DIR", tmp_path)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(FileNotFoundError, match="env init"):
            _lib.load_env("dev")

    def test_missing_shared_env_tolerated_when_env_provisioned(self, tmp_path, monkeypatch):
        # Containers / CI inject DATABASE_URL as a real env var, no file on disk.
        monkeypatch.setattr(_lib, "BACKEND_DIR", tmp_path)
        monkeypatch.setenv("DATABASE_URL", "postgres://from-env")

        _lib.load_env("prod")

        assert _lib.database_url() == "postgres://from-env"

    def test_rejects_selector_runtime_mismatch_before_loading_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_lib, "BACKEND_DIR", tmp_path)
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DATABASE_URL", "postgres://prod")

        with pytest.raises(SystemExit, match="does not match"):
            _lib.load_env("dev")

    def test_unknown_service_raises(self, tmp_path, monkeypatch):
        (tmp_path / "shared.dev.env").write_text("X=1\n", encoding="utf-8")
        monkeypatch.setattr(_lib, "BACKEND_DIR", tmp_path)
        with pytest.raises(ValueError, match="unknown service"):
            _lib.load_env("dev", service="nope")


class TestConfirm:
    def test_assume_yes_short_circuits(self):
        assert _lib.confirm("wipe everything?", assume_yes=True) is True

    def test_no_input_refuses(self, monkeypatch, capsys):
        def _eof(_):
            raise EOFError

        monkeypatch.setattr("builtins.input", _eof)
        assert _lib.confirm("wipe everything?") is False
        assert "Refusing" in capsys.readouterr().out

    def test_interactive_yes(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "y")
        assert _lib.confirm("go?") is True

    def test_interactive_no(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "")
        assert _lib.confirm("go?") is False


class TestAddEnvArg:
    def test_default_is_dev(self, monkeypatch):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        p = argparse.ArgumentParser()
        _lib.add_env_arg(p)
        assert p.parse_args([]).env == "dev"
        assert p.parse_args(["--env", "stg"]).env == "stg"
        assert p.parse_args(["--env", "prod"]).env == "prod"

    @pytest.mark.parametrize(
        ("runtime", "expected"),
        [("development", "dev"), ("staging", "stg"), ("production", "prod")],
    )
    def test_default_follows_runtime_environment(self, runtime, expected, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", runtime)
        p = argparse.ArgumentParser()
        _lib.add_env_arg(p)
        assert p.parse_args([]).env == expected


class TestDatabaseContext:
    def test_dev_allows_host_access(self, monkeypatch):
        monkeypatch.delenv("NIIBOT_RUNTIME_CONTEXT", raising=False)
        _lib.require_db_context("dev")

    @pytest.mark.parametrize("env", ["stg", "prod"])
    def test_deployed_env_requires_container(self, env, monkeypatch):
        monkeypatch.delenv("NIIBOT_RUNTIME_CONTEXT", raising=False)
        with pytest.raises(SystemExit, match="container"):
            _lib.require_db_context(env)

    @pytest.mark.parametrize("env", ["stg", "prod"])
    def test_deployed_env_allows_container_access(self, env, monkeypatch):
        monkeypatch.setenv("NIIBOT_RUNTIME_CONTEXT", "container")
        monkeypatch.setenv("ENVIRONMENT", {"stg": "staging", "prod": "production"}[env])
        _lib.require_db_context(env)

    def test_container_rejects_selector_runtime_mismatch(self, monkeypatch):
        monkeypatch.setenv("NIIBOT_RUNTIME_CONTEXT", "container")
        monkeypatch.setenv("ENVIRONMENT", "production")

        with pytest.raises(SystemExit, match="does not match"):
            _lib.require_db_context("dev")


class TestDevDatabase:
    def test_allows_loopback_host(self, monkeypatch):
        monkeypatch.delenv("NIIBOT_RUNTIME_CONTEXT", raising=False)
        _lib.require_dev_database("postgresql://user:pass@127.0.0.1:5432/dev")

    def test_rejects_remote_host(self, monkeypatch):
        monkeypatch.delenv("NIIBOT_RUNTIME_CONTEXT", raising=False)
        with pytest.raises(SystemExit, match="local dev database"):
            _lib.require_dev_database("postgresql://user:pass@db.example.com/dev")

    def test_dev_container_allows_service_dns(self, monkeypatch):
        monkeypatch.setenv("NIIBOT_RUNTIME_CONTEXT", "container")
        monkeypatch.setenv("ENVIRONMENT", "development")
        _lib.require_dev_database("postgresql://user:pass@postgres:5432/dev")
