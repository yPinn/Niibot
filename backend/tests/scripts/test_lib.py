"""Tests for backend/scripts/_lib.py — env selection, db ctx, confirm."""

from __future__ import annotations

import argparse

import _lib
import pytest


class TestLoadEnv:
    def test_rejects_bad_env(self):
        with pytest.raises(ValueError, match="prod.*staging"):
            _lib.load_env("dev")

    def test_prod_loads_shared_env(self, tmp_path, monkeypatch):
        (tmp_path / "shared.env").write_text("DATABASE_URL=postgres://prod\n", encoding="utf-8")
        monkeypatch.setattr(_lib, "BACKEND_DIR", tmp_path)
        monkeypatch.delenv("DATABASE_URL", raising=False)

        _lib.load_env("prod")

        assert _lib.database_url() == "postgres://prod"

    def test_staging_uses_staging_file_set(self, tmp_path, monkeypatch):
        (tmp_path / "shared.env").write_text("DATABASE_URL=postgres://prod\n", encoding="utf-8")
        (tmp_path / "shared.staging.env").write_text(
            "DATABASE_URL=postgres://staging\n", encoding="utf-8"
        )
        monkeypatch.setattr(_lib, "BACKEND_DIR", tmp_path)
        monkeypatch.delenv("DATABASE_URL", raising=False)

        _lib.load_env("staging")

        assert _lib.database_url() == "postgres://staging"

    def test_local_override_and_service_file(self, tmp_path, monkeypatch):
        (tmp_path / "shared.env").write_text("A=base\nB=base\n", encoding="utf-8")
        (tmp_path / "shared.env.local").write_text("A=local\n", encoding="utf-8")
        (tmp_path / "twitch").mkdir()
        (tmp_path / "twitch" / ".env").write_text("B=svc\n", encoding="utf-8")
        monkeypatch.setattr(_lib, "BACKEND_DIR", tmp_path)
        monkeypatch.delenv("A", raising=False)
        monkeypatch.delenv("B", raising=False)

        _lib.load_env("prod", service="twitch")

        import os

        assert os.environ["A"] == "local"  # shared.env.local wins
        assert os.environ["B"] == "svc"  # service file wins over shared.env

    def test_missing_shared_env_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_lib, "BACKEND_DIR", tmp_path)
        with pytest.raises(FileNotFoundError, match="env init"):
            _lib.load_env("prod")

    def test_unknown_service_raises(self, tmp_path, monkeypatch):
        (tmp_path / "shared.env").write_text("X=1\n", encoding="utf-8")
        monkeypatch.setattr(_lib, "BACKEND_DIR", tmp_path)
        with pytest.raises(ValueError, match="unknown service"):
            _lib.load_env("prod", service="nope")


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
    def test_default_is_prod(self):
        p = argparse.ArgumentParser()
        _lib.add_env_arg(p)
        assert p.parse_args([]).env == "prod"
        assert p.parse_args(["--env", "staging"]).env == "staging"
