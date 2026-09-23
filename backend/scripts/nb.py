#!/usr/bin/env python3
"""Niibot dev CLI — one entry point for every script under scripts/.

    npm run nb -- <group> <command> [options]        # from repo root
    uv run --directory backend python scripts/nb.py <group> <command>

Groups: db · twitch · discord · models · assets · env · staging · badges
(`nb --help` / `nb <group> --help` for the full surface). The individual scripts
still run standalone; nb lazy-imports one per invocation so the api/twitch/discord
`core` packages never collide.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys

from _lib import REPO_ROOT, add_env_arg, ensure_backend_on_path, load_env, utf8_stdio

utf8_stdio()  # covers every lazy-imported script; standalone scripts call it themselves

# ── subprocess groups (bash / root-level python) ─────────────────────────────

_GEN_ENV_CMDS = {"gen", "check", "print"}

# Descriptions mirror the usage block in scripts/env.sh and scripts/staging.sh;
# anything not in _GEN_ENV_CMDS is dispatched to env.sh.
_ENV_CMDS: dict[str, str] = {
    "gen": "regenerate templates, docs and manifest from env.registry.toml",
    "check": "fail if any generated env file is out of sync",
    "print": "print one resolved KEY",
    "init": "copy every *.env.example → *.env (-f overwrites)",
    "snapshot": "snapshot live env files to data/env/YYYYMMDD/",
    "backup": "snapshot + compress to data/env-YYYYMMDD.tar.gz",
    "restore": "restore from a snapshot or .tar.gz (-f overwrites)",
    "diff": "diff current env files against a snapshot",
    "list": "list available snapshots and backups",
    "clean": "delete old snapshots/backups (default: keep 3)",
}

_STAGING_CMDS: dict[str, str] = {
    "up": "start staging (default profile: full)",
    "down": "stop containers, keep volumes",
    "reset": "stop and wipe volumes (postgres data included)",
    "build": "build one service, or all when none given",
    "logs": "stream logs; pass a service to tail just that one",
    "ps": "show this project's containers and health",
    "restart": "restart running containers without rebuilding",
    "migrate": "run migrations as a one-shot container",
    "exec": "run a command inside a staging container",
}


def _sh(*parts: str, passthrough: list[str] | None = None) -> int:
    cmd = list(parts) + (passthrough or [])
    # Resolve the executable through PATH ourselves. Windows CreateProcess
    # searches System32 before PATH, so a bare "bash" picks up the WSL stub
    # there instead of Git Bash and dies with execvpe(/bin/bash) — which broke
    # every env.sh and staging.sh command behind `npm run nb`.
    if resolved := shutil.which(cmd[0]):
        cmd[0] = resolved
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
    sub_parsers, name: str, help_text: str, commands: dict[str, str], handler
) -> None:
    """Add a group that forwards its subcommand to a shell/root script.

    Takes {subcommand: description} rather than a bare name list so these
    groups describe themselves like the natively-parsed ones do — otherwise
    `nb env --help` prints only a set of names and sends the reader to the
    README to find out what any of them do.
    """
    grp = sub_parsers.add_parser(name, help=help_text).add_subparsers(
        dest="sub", required=True, metavar="<command>"
    )
    for cmd, desc in commands.items():
        p = grp.add_parser(cmd, help=desc)
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

    # assets -------------------------------------------------------------------
    assets = groups.add_parser("assets", help="static asset build tools").add_subparsers(
        dest="cmd", required=True, metavar="<command>"
    )
    p = assets.add_parser(
        "collections", help="preview or build catalog-driven collection WebP derivatives"
    )
    p.add_argument("action", choices=("preview", "build"))
    p.add_argument("--catalog")
    p.add_argument("--source-root")
    p.add_argument("--output-dir")
    p.add_argument("--output-width", type=int)
    p.add_argument("--output-height", type=int)
    p.add_argument("--quality", type=int, default=85)
    p.add_argument("--method", type=int, default=6)
    p.add_argument("--max-megapixels", type=float, default=50.0)
    p.add_argument("--crop-warning-percent", type=float, default=18.0)
    p.add_argument("--upscale-warning-factor", type=float, default=1.15)
    p.set_defaults(_handler=_run_py("build_collection_assets"))

    # env / staging / badges (passthrough) -----------------------------------
    _add_passthrough_group(groups, "env", "env file management", _ENV_CMDS, _run_env)
    _add_passthrough_group(groups, "staging", "staging docker compose", _STAGING_CMDS, _run_staging)
    p = groups.add_parser("badges", help="download Twitch role badge images")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.set_defaults(_handler=_run_badges)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args._handler(args))


if __name__ == "__main__":
    sys.exit(main())
