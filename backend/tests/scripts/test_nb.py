"""Tests for backend/scripts/nb.py — the dispatcher wiring (not the leaf logic)."""

from __future__ import annotations

import nb
import pytest


class TestParser:
    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as exc:
            nb.build_parser().parse_args(["--help"])
        assert exc.value.code == 0
        assert "Niibot operations CLI" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "group",
        [
            "db",
            "twitch",
            "discord",
            "checkin",
            "ai",
            "models",
            "assets",
            "env",
            "stack",
            "badges",
        ],
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
    def test_windows_shell_uses_git_bash_login_path(self, monkeypatch, tmp_path):
        bash = tmp_path / "Git" / "bin" / "bash.exe"
        bash.parent.mkdir(parents=True)
        bash.touch()
        calls = []
        monkeypatch.setattr(nb.sys, "platform", "win32")
        monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
        monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
        monkeypatch.setattr(
            nb.subprocess,
            "run",
            lambda cmd, cwd: calls.append((cmd, cwd)) or type("Result", (), {"returncode": 0})(),
        )

        assert nb._sh("bash", "scripts/stack.sh", "dev", "ps") == 0
        assert calls[0][0][:2] == [str(bash), "-l"]

    def test_db_migrate_calls_module_run(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(nb, "_call", lambda mod, a: (seen.update(mod=mod, args=a), 0)[1])

        rc = nb.main(["db", "migrate", "--dry", "--env", "stg"])

        assert rc == 0
        assert seen["mod"] == "scripts.db.migrate"
        assert seen["args"].dry is True
        assert seen["args"].env == "stg"

    def test_twitch_tokens_sets_tw_action(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(nb, "_call", lambda mod, a: (seen.update(mod=mod, args=a), 0)[1])

        nb.main(["twitch", "tokens"])

        assert seen["mod"] == "scripts.twitch_ops.diag"
        assert seen["args"].tw_action == "tokens"

    def test_discord_sync_sets_dc_action(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(nb, "_call", lambda mod, a: (seen.update(mod=mod, args=a), 0)[1])

        nb.main(["discord", "sync", "--env", "prod", "-y"])

        assert seen["mod"] == "scripts.discord_ops.commands"
        assert seen["args"].dc_action == "sync"
        assert seen["args"].env == "prod"
        assert seen["args"].yes is True

    @pytest.mark.parametrize("action", ["preview", "build"])
    def test_collection_assets_dispatches_catalog_action(self, monkeypatch, action):
        seen = {}
        monkeypatch.setattr(nb, "_call", lambda mod, a: (seen.update(mod=mod, args=a), 0)[1])

        nb.main(["assets", "collections", action])

        assert seen["mod"] == "scripts.assets.collections"
        assert seen["args"].action == action
        assert seen["args"].output_width is None
        assert seen["args"].output_height is None
        assert seen["args"].crop_warning_percent == 18.0

    def test_checkin_backfill_dispatches_module(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(nb, "_call", lambda mod, a: (seen.update(mod=mod, args=a), 0)[1])

        nb.main(["checkin", "backfill", "--env", "stg", "--dry-run"])

        assert seen["mod"] == "scripts.checkin.backfill"
        assert seen["args"].env == "stg"
        assert seen["args"].dry_run is True

    def test_ai_eval_dispatches_module(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(nb, "_call", lambda mod, a: (seen.update(mod=mod, args=a), 0)[1])

        nb.main(["ai", "eval", "--env", "dev", "--fixture", "rem", "--trials", "2"])

        assert seen["mod"] == "scripts.ai.eval"
        assert seen["args"].fixture == "rem"
        assert seen["args"].trials == 2

    def test_env_gen_shells_to_gen_env(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            nb, "_sh", lambda *p, passthrough=None: calls.append((p, passthrough)) or 0
        )

        nb.main(["env", "gen"])

        (parts, passthrough) = calls[0]
        assert "scripts/env/gen.py" in parts
        assert passthrough == []

    def test_env_check_passes_flag(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            nb, "_sh", lambda *p, passthrough=None: calls.append((p, passthrough)) or 0
        )

        nb.main(["env", "check"])

        assert calls[0][1] == ["--check"]

    @pytest.mark.parametrize(
        ("command", "parts", "passthrough"),
        [
            ("validate", ("scripts/env/check.py",), ["dev"]),
            ("sync", ("scripts/env/sync.py",), ["dev"]),
            ("push", ("bash", ".github/push.sh"), ["stg"]),
            ("pull", ("bash", ".github/pull.sh"), ["prod"]),
        ],
    )
    def test_env_operations_use_one_public_entry(self, monkeypatch, command, parts, passthrough):
        calls = []
        monkeypatch.setattr(
            nb, "_sh", lambda *p, passthrough=None: calls.append((p, passthrough)) or 0
        )

        nb.main(["env", command, *passthrough])

        actual_parts, actual_passthrough = calls[0]
        assert actual_parts[-len(parts) :] == parts
        assert actual_passthrough == passthrough

    def test_stack_passes_environment_and_command(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            nb, "_sh", lambda *p, passthrough=None: calls.append((p, passthrough)) or 0
        )

        nb.main(["stack", "stg", "logs", "api"])

        parts, passthrough = calls[0]
        assert parts == ("bash", "scripts/stack.sh", "stg", "logs")
        assert passthrough == ["api"]

    def test_stack_compose_passes_raw_dev_arguments_through_guard(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            nb, "_sh", lambda *p, passthrough=None: calls.append((p, passthrough)) or 0
        )

        nb.main(["stack", "dev", "compose", "--profile", "api", "config"])

        parts, passthrough = calls[0]
        assert parts == ("bash", "scripts/stack.sh", "dev", "compose")
        assert passthrough == ["--profile", "api", "config"]
