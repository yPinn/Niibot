"""Tests for backend/scripts/nb.py — the dispatcher wiring (not the leaf logic)."""

from __future__ import annotations

import nb
import pytest


class TestParser:
    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as exc:
            nb.build_parser().parse_args(["--help"])
        assert exc.value.code == 0
        assert "Niibot dev CLI" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "group", ["db", "twitch", "discord", "models", "assets", "env", "staging", "badges"]
    )
    def test_every_group_listed_in_help(self, group, capsys):
        with pytest.raises(SystemExit):
            nb.build_parser().parse_args(["--help"])
        assert group in capsys.readouterr().out

    def test_unknown_group_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            nb.build_parser().parse_args(["frobnicate"])
        assert exc.value.code == 2

    def test_group_without_command_errors(self):
        with pytest.raises(SystemExit):
            nb.build_parser().parse_args(["db"])


class TestDispatch:
    def test_db_migrate_calls_module_run(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(nb, "_call", lambda mod, a: (seen.update(mod=mod, args=a), 0)[1])

        rc = nb.main(["db", "migrate", "--dry", "--env", "staging"])

        assert rc == 0
        assert seen["mod"] == "db_migrate"
        assert seen["args"].dry is True
        assert seen["args"].env == "staging"

    def test_twitch_tokens_sets_tw_action(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(nb, "_call", lambda mod, a: (seen.update(mod=mod, args=a), 0)[1])

        nb.main(["twitch", "tokens"])

        assert seen["mod"] == "twitch_diag"
        assert seen["args"].tw_action == "tokens"

    def test_discord_sync_sets_dc_action(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(nb, "_call", lambda mod, a: (seen.update(mod=mod, args=a), 0)[1])

        nb.main(["discord", "sync", "--prod", "-y"])

        assert seen["mod"] == "discord_cmds"
        assert seen["args"].dc_action == "sync"
        assert seen["args"].prod is True
        assert seen["args"].yes is True

    @pytest.mark.parametrize("action", ["preview", "build"])
    def test_collection_assets_dispatches_catalog_action(self, monkeypatch, action):
        seen = {}
        monkeypatch.setattr(nb, "_call", lambda mod, a: (seen.update(mod=mod, args=a), 0)[1])

        nb.main(["assets", "collections", action])

        assert seen["mod"] == "build_collection_assets"
        assert seen["args"].action == action
        assert seen["args"].output_width is None
        assert seen["args"].output_height is None
        assert seen["args"].crop_warning_percent == 18.0

    def test_env_gen_shells_to_gen_env(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            nb, "_sh", lambda *p, passthrough=None: calls.append((p, passthrough)) or 0
        )

        nb.main(["env", "gen"])

        (parts, passthrough) = calls[0]
        assert "scripts/gen_env.py" in parts
        assert passthrough == []

    def test_env_check_passes_flag(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            nb, "_sh", lambda *p, passthrough=None: calls.append((p, passthrough)) or 0
        )

        nb.main(["env", "check"])

        assert calls[0][1] == ["--check"]

    def test_staging_passes_through(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            nb, "_sh", lambda *p, passthrough=None: calls.append((p, passthrough)) or 0
        )

        nb.main(["staging", "logs", "api"])

        parts, passthrough = calls[0]
        assert parts == ("bash", "scripts/staging.sh", "logs")
        assert passthrough == ["api"]
