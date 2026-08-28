#!/usr/bin/env python3
"""Niibot dev CLI — one entry point for every script under scripts/.

    npm run nb -- <group> <command> [options]        # from repo root
    uv run --directory backend python scripts/nb.py <group> <command>

Groups: db · twitch · discord · models · env · staging · badges
(`nb --help` / `nb <group> --help` for the full surface). The individual scripts
still run standalone; nb lazy-imports one per invocation so the api/twitch/discord
`core` packages never collide.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from _lib import REPO_ROOT, add_env_arg, ensure_backend_on_path, load_env, utf8_stdio

utf8_stdio()  # covers every lazy-imported script; standalone scripts call it themselves

# ── subprocess groups (bash / root-level python) ─────────────────────────────

_ENV_SH_CMDS = {"init", "snapshot", "backup", "restore", "diff", "list", "clean"}
_GEN_ENV_CMDS = {"gen", "check", "print"}


def _sh(*parts: str, passthrough: list[str] | None = None) -> int:
    cmd = list(parts) + (passthrough or [])
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


def _run_env(args: argparse.Namespace) -> int:
    # `sub` is choices-constrained, so anything not in _GEN_ENV_CMDS is an env.sh cmd
    if args.sub in _GEN_ENV_CMDS:
        flag = [] if args.sub == "gen" else [f"--{args.sub}"]
        return _sh(sys.executable, "scripts/gen_env.py", passthrough=flag + args.rest)
    return _sh("bash", "scripts/env.sh", args.sub, passthrough=args.rest)


def _run_staging(args: argparse.Namespace) -> int:
    return _sh("bash", "scripts/staging.sh", args.sub, passthrough=args.rest)


def _run_badges(args: argparse.Namespace) -> int:
    load_env("prod")
    return _sh(sys.executable, "scripts/badges.py", passthrough=args.rest)


# ── python groups (lazy import, call module.run) ────────────────────────────


def _call(module_name: str, args: argparse.Namespace) -> int:
    ensure_backend_on_path()
    module = __import__(module_name, fromlist=["run"])
    return int(module.run(args))


def _run_py(module_name: str):
    def handler(args: argparse.Namespace) -> int:
        return _call(module_name, args)

    return handler


# ── parser ──────────────────────────────────────────────────────────────────


def _add_passthrough_group(
    sub_parsers, name: str, help_text: str, choices: list[str], handler
) -> None:
    p = sub_parsers.add_parser(name, help=help_text)
    p.add_argument("sub", choices=choices, help="subcommand")
    p.add_argument("rest", nargs=argparse.REMAINDER, help="args passed through verbatim")
    p.set_defaults(_handler=handler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nb", description="Niibot dev CLI")
    groups = parser.add_subparsers(dest="group", required=True, metavar="<group>")

    # db ---------------------------------------------------------------------
    db = groups.add_parser("db", help="database tools").add_subparsers(
        dest="cmd", required=True, metavar="<command>"
    )
    p = db.add_parser("migrate", help="run pending migrations")
    p.add_argument("--dry", action="store_true", help="show pending, don't apply")
    add_env_arg(p)
    p.set_defaults(_handler=_run_py("db_migrate"))
    p = db.add_parser("check", help="verify DB triggers / schema")
    add_env_arg(p)
    p.set_defaults(_handler=_run_py("db_check"))
    p = db.add_parser("seed", help="[dev] generate fake session/viewer data")
    p.add_argument("channel_id", nargs="?")
    p.add_argument("n_sessions", nargs="?", type=int, default=15)
    p.set_defaults(_handler=_run_py("dev.db_seed"))
    p = db.add_parser("clear", help="[dev] wipe analytics/session tables")
    p.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
    p.set_defaults(_handler=_run_py("dev.db_clear"))
    db.add_parser("backup", help="pg_dump via docker").set_defaults(
        _handler=lambda a: _sh("bash", "backend/scripts/db_backup.sh")
    )

    # twitch ---------------------------------------------------------------------
    tw = groups.add_parser("twitch", help="Twitch token / OAuth / backfill tools").add_subparsers(
        dest="cmd", required=True, metavar="<command>"
    )
    p = tw.add_parser("oauth", help="generate a bot/broadcaster token")
    p.add_argument("--role", choices=("bot", "broadcaster"))
    p.add_argument("--env", choices=("prod", "staging"))
    p.set_defaults(_handler=_run_py("twitch_oauth"))
    for name, helptext in (
        ("tokens", "list stored tokens + scopes"),
        ("emotes", "bot emote access per channel"),
    ):
        p = tw.add_parser(name, help=helptext)
        add_env_arg(p)
        p.set_defaults(_handler=_run_py("twitch_diag"), tw_action=name)
    p = tw.add_parser("backfill-sessions", help="backfill sessions from VODs")
    p.add_argument("--keep-existing", action="store_true")
    p.add_argument("--limit", type=int, default=20)
    add_env_arg(p)
    p.set_defaults(_handler=_run_py("twitch_backfill_sessions"))
    p = tw.add_parser("backfill-matcher", help="backfill overlap tables from chatter_stats")
    p.add_argument("--days", default="7,30,90", help="comma-separated windows")
    p.add_argument("--dry-run", action="store_true")
    add_env_arg(p)
    p.set_defaults(_handler=_run_py("twitch_backfill_matcher"))

    # discord ------------------------------------------------------------------
    dc = groups.add_parser("discord", help="Discord slash-command management").add_subparsers(
        dest="cmd", required=True, metavar="<command>"
    )
    for name, helptext in (
        ("ls", "list registered commands"),
        ("diff", "preview what sync would change"),
        ("sync", "sync the command tree to Discord"),
        ("rm", "clear registered commands"),
    ):
        p = dc.add_parser(name, help=helptext)
        p.add_argument("--prod", action="store_true", help="use .env.production")
        p.add_argument("--guild", metavar="ID", help="override DISCORD_GUILD_ID")
        p.add_argument("--global", dest="force_global", action="store_true", help="force global")
        p.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
        p.set_defaults(_handler=_run_py("discord_cmds"), dc_action=name)

    # models -------------------------------------------------------------------
    md = groups.add_parser("models", help="OpenRouter free-model list").add_subparsers(
        dest="cmd", required=True, metavar="<command>"
    )
    p = md.add_parser("update", help="refresh data/free_models.json")
    p.add_argument("--with-uptime", action="store_true")
    p.set_defaults(_handler=_run_py("models_update"))

    # env / staging / badges (passthrough) -----------------------------------
    _add_passthrough_group(
        groups,
        "env",
        "env file management",
        sorted(_ENV_SH_CMDS | _GEN_ENV_CMDS),
        _run_env,
    )
    _add_passthrough_group(
        groups,
        "staging",
        "staging docker compose",
        ["up", "down", "reset", "build", "logs", "ps", "restart", "migrate", "exec"],
        _run_staging,
    )
    p = groups.add_parser("badges", help="download Twitch role badge images")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.set_defaults(_handler=_run_badges)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args._handler(args))


if __name__ == "__main__":
    sys.exit(main())
