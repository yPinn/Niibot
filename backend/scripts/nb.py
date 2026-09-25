#!/usr/bin/env python3
"""Niibot CLI — one entry point for repository operations.

    npm run nb -- <group> <command> [options]        # from repo root
    uv run --directory backend python scripts/nb.py <group> <command>

Groups: db · twitch · discord · checkin · ai · models · assets · env · stack · badges
(`nb --help` / `nb <group> --help` for the full surface). The individual scripts
still run standalone; nb lazy-imports one per invocation so the api/twitch/discord
`core` packages never collide.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from _lib import (
    ENV_CHOICES,
    REPO_ROOT,
    add_env_arg,
    confirm,
    ensure_backend_on_path,
    load_env,
    utf8_stdio,
)

utf8_stdio()  # covers every lazy-imported script; standalone scripts call it themselves

# ── subprocess groups (bash / root-level python) ─────────────────────────────

_GEN_ENV_CMDS = {"gen", "check", "print"}

_ENV_CMDS: dict[str, str] = {
    "gen": "regenerate templates, docs and manifest from env.registry.toml",
    "check": "fail if any generated env file is out of sync",
    "print": "print one resolved KEY",
    "validate": "validate one live env set against generated examples",
    "init": "create one explicit env set from templates (default: dev)",
    "migrate": "rename legacy env files into one explicit env set",
    "sync": "reorder runtime or GitHub env files and preserve known values",
    "snapshot": "snapshot live env files to data/env/YYYYMMDD/",
    "backup": "snapshot + compress to data/env-YYYYMMDD.tar.gz",
    "restore": "restore from a snapshot or .tar.gz (-f overwrites)",
    "diff": "diff current env files against a snapshot",
    "list": "list available snapshots and backups",
    "clean": "delete old snapshots/backups (default: keep 3)",
    "push": "push local GitHub variables and secrets for prod or stg",
    "pull": "pull GitHub variables and report secret presence",
}

_STACK_CMDS: dict[str, str] = {
    "up": "start an environment (default profile: full)",
    "down": "stop containers, keep volumes",
    "reset": "stop and wipe PostgreSQL state (prod disabled)",
    "build": "build one service, or all when none given",
    "logs": "stream logs; pass a service to tail just that one",
    "ps": "show this project's containers and health",
    "restart": "restart running containers without rebuilding",
    "migrate": "run migrations as a one-shot container",
    "exec": "run a command inside an environment container",
    "config": "validate Compose without printing resolved env values",
    "compose": "pass raw arguments through the environment guard",
}


def _sh(*parts: str, passthrough: list[str] | None = None) -> int:
    cmd = list(parts) + (passthrough or [])
    if cmd[0] == "bash" and sys.platform == "win32":
        roots = (os.getenv("PROGRAMFILES"), os.getenv("PROGRAMFILES(X86)"))
        candidates = [Path(root) / "Git" / "bin" / "bash.exe" for root in roots if root]
        git_bash = next((path for path in candidates if path.is_file()), None)
        if git_bash is not None:
            cmd[:1] = [str(git_bash), "-l"]
        elif resolved := shutil.which(cmd[0]):
            cmd[0] = resolved
    elif resolved := shutil.which(cmd[0]):
        cmd[0] = resolved
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


def _run_env(args: argparse.Namespace) -> int:
    if args.sub in _GEN_ENV_CMDS:
        flag = [] if args.sub == "gen" else [f"--{args.sub}"]
        return _sh(sys.executable, "scripts/env/gen.py", passthrough=flag + args.rest)
    if args.sub == "validate":
        return _sh(sys.executable, "scripts/env/check.py", passthrough=args.rest)
    if args.sub == "sync":
        return _sh(sys.executable, "scripts/env/sync.py", passthrough=args.rest)
    if args.sub in {"push", "pull"}:
        return _sh("bash", f".github/{args.sub}.sh", passthrough=args.rest)
    return _sh("bash", "scripts/env/manage.sh", args.sub, passthrough=args.rest)


def _run_stack(args: argparse.Namespace) -> int:
    return _sh("bash", "scripts/stack.sh", args.env, args.cmd, passthrough=args.rest)


def _run_twitch_invite(args: argparse.Namespace) -> int:
    if args.env == "prod" and not confirm(
        "Create a one-time system Bot invite in production?", assume_yes=args.yes
    ):
        return 1
    command = [
        "api",
        "python",
        "-m",
        "scripts.twitch_ops.invite",
        "--env",
        args.env,
    ]
    if args.env == "prod":
        command.append("--yes")
    return _sh("bash", "scripts/stack.sh", args.env, "exec", passthrough=command)


def _run_discord(args: argparse.Namespace) -> int:
    if args.env == "dev":
        return _call("scripts.discord_ops.commands", args)

    action = args.dc_action
    if action in {"sync", "rm"}:
        scope = "global" if args.force_global or not args.guild else f"guild {args.guild}"
        prompt = f"{action} Discord commands in {args.env} ({scope})?"
        if not confirm(prompt, assume_yes=args.yes):
            return 1

    command = [
        "discord-bot",
        "python",
        "-m",
        "scripts.discord_ops.commands",
        action,
        "--env",
        args.env,
    ]
    if args.guild:
        command.extend(("--guild", args.guild))
    if args.force_global:
        command.append("--global")
    if action in {"sync", "rm"}:
        command.append("--yes")

    return _sh("bash", "scripts/stack.sh", args.env, "exec", passthrough=command)


def _run_badges(args: argparse.Namespace) -> int:
    load_env(args.env)
    return _sh(sys.executable, "scripts/assets/badges.py", passthrough=args.rest)


# ── python groups (lazy import, call module.run) ────────────────────────────


def _call(module_name: str, args: argparse.Namespace) -> int:
    ensure_backend_on_path()
    module = __import__(module_name, fromlist=["run"])
    return int(module.run(args))


def _run_py(module_name: str):
    def handler(args: argparse.Namespace) -> int:
        return _call(module_name, args)

    return handler


def _number(value: str, *, minimum: float, integer: bool = False):
    try:
        parsed = int(value) if integer else float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if parsed < minimum:
        raise argparse.ArgumentTypeError(f"must be at least {minimum:g}")
    return parsed


# ── parser ──────────────────────────────────────────────────────────────────


def _add_passthrough_group(
    sub_parsers, name: str, help_text: str, commands: dict[str, str], handler
) -> None:
    """Add a documented passthrough command group."""
    grp = sub_parsers.add_parser(name, help=help_text).add_subparsers(
        dest="sub", required=True, metavar="<command>"
    )
    for cmd, desc in commands.items():
        p = grp.add_parser(cmd, help=desc)
        p.add_argument("rest", nargs=argparse.REMAINDER, help="args passed through verbatim")
        p.set_defaults(_handler=handler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nb", description="Niibot operations CLI")
    groups = parser.add_subparsers(dest="group", required=True, metavar="<group>")

    # db ---------------------------------------------------------------------
    db = groups.add_parser("db", help="database tools").add_subparsers(
        dest="cmd", required=True, metavar="<command>"
    )
    p = db.add_parser("migrate", help="run pending migrations")
    p.add_argument("--dry", action="store_true", help="show pending, don't apply")
    add_env_arg(p)
    p.set_defaults(_handler=_run_py("scripts.db.migrate"))
    p = db.add_parser("check", help="verify DB triggers / schema")
    add_env_arg(p)
    p.set_defaults(_handler=_run_py("scripts.db.check"))
    p = db.add_parser("seed", help="[dev] generate fake session/viewer data")
    p.add_argument("channel_id", nargs="?")
    p.add_argument("n_sessions", nargs="?", type=int, default=15)
    p.set_defaults(_handler=_run_py("scripts.db.seed"))
    p = db.add_parser("clear", help="[dev] wipe analytics/session tables")
    p.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
    p.set_defaults(_handler=_run_py("scripts.db.clear"))
    p = db.add_parser("backup", help="pg_dump through the selected Compose project")
    add_env_arg(p)
    p.set_defaults(_handler=lambda a: _sh("bash", "backend/scripts/db/backup.sh", a.env))

    # twitch ---------------------------------------------------------------------
    tw = groups.add_parser("twitch", help="Twitch token / OAuth / backfill tools").add_subparsers(
        dest="cmd", required=True, metavar="<command>"
    )
    p = tw.add_parser("oauth", help="generate a bot/broadcaster token")
    p.add_argument("--role", choices=("bot", "broadcaster"))
    p.add_argument("--env", choices=("dev",))
    p.set_defaults(_handler=_run_py("scripts.twitch_ops.oauth"))
    p = tw.add_parser("invite", help="create a deployed system Bot reset invite")
    p.add_argument("env", choices=("stg", "prod"))
    p.add_argument("-y", "--yes", action="store_true", help="skip production confirmation")
    p.set_defaults(_handler=_run_twitch_invite)
    for name, helptext in (
        ("tokens", "list stored tokens + scopes"),
        ("emotes", "bot emote access per channel"),
    ):
        p = tw.add_parser(name, help=helptext)
        add_env_arg(p)
        p.set_defaults(_handler=_run_py("scripts.twitch_ops.diag"), tw_action=name)
    p = tw.add_parser("backfill-sessions", help="backfill sessions from VODs")
    p.add_argument("--keep-existing", action="store_true")
    p.add_argument("--limit", type=int, default=20)
    add_env_arg(p)
    p.set_defaults(_handler=_run_py("scripts.twitch_ops.backfill_sessions"))
    p = tw.add_parser("backfill-matches", help="backfill overlap tables from chatter_stats")
    p.add_argument("--days", default="7,30,90", help="comma-separated windows")
    p.add_argument("--dry-run", action="store_true")
    add_env_arg(p)
    p.set_defaults(_handler=_run_py("scripts.twitch_ops.backfill_matches"))
    p = tw.add_parser("credentials", help="encrypt or repair stored credentials")
    p.add_argument(
        "--batch-size", type=lambda value: _number(value, minimum=1, integer=True), default=100
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--repair-missing-envelopes", action="store_true")
    add_env_arg(p)
    p.set_defaults(_handler=_run_py("scripts.twitch_ops.credentials"))

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
        add_env_arg(p)
        p.add_argument("--guild", metavar="ID", help="override DISCORD_GUILD_ID")
        p.add_argument("--global", dest="force_global", action="store_true", help="force global")
        p.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
        p.set_defaults(_handler=_run_discord, dc_action=name)

    # check-in ----------------------------------------------------------------
    checkin = groups.add_parser("checkin", help="check-in maintenance").add_subparsers(
        dest="cmd", required=True, metavar="<command>"
    )
    p = checkin.add_parser("backfill", help="backfill missing historical collection draws")
    p.add_argument("--batch-size", type=int, default=100)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    p.add_argument("-y", "--yes", action="store_true")
    add_env_arg(p)
    p.set_defaults(_handler=_run_py("scripts.checkin.backfill"))

    # ai ----------------------------------------------------------------------
    ai = groups.add_parser("ai", help="AI evaluation tools").add_subparsers(
        dest="cmd", required=True, metavar="<command>"
    )
    p = ai.add_parser("eval", help="run the role-play prompt evaluation gate")
    add_env_arg(p)
    p.add_argument("--fixture", choices=("original", "rem"), default="original")
    p.add_argument(
        "--trials", type=lambda value: _number(value, minimum=1, integer=True), default=1
    )
    p.add_argument("--timeout", type=lambda value: _number(value, minimum=0.001), default=15.0)
    p.add_argument("--delay", type=lambda value: _number(value, minimum=0), default=15.0)
    p.add_argument("--output", type=Path)
    p.add_argument("--resume", type=Path)
    p.add_argument("--case", dest="case_ids", action="append")
    p.set_defaults(_handler=_run_py("scripts.ai.eval"))

    # models -------------------------------------------------------------------
    md = groups.add_parser("models", help="OpenRouter free-model list").add_subparsers(
        dest="cmd", required=True, metavar="<command>"
    )
    p = md.add_parser("update", help="refresh data/free_models.json")
    p.add_argument("--with-uptime", action="store_true")
    p.set_defaults(_handler=_run_py("scripts.models.update"))

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
    p.set_defaults(_handler=_run_py("scripts.assets.collections"))

    # env / stack / badges ---------------------------------------------------
    _add_passthrough_group(groups, "env", "env file management", _ENV_CMDS, _run_env)
    stack = groups.add_parser("stack", help="environment-scoped Docker Compose")
    stack.add_argument("env", choices=ENV_CHOICES)
    stack.add_argument("cmd", choices=tuple(_STACK_CMDS))
    stack.add_argument("rest", nargs=argparse.REMAINDER, help="arguments passed to Compose")
    stack.set_defaults(_handler=_run_stack)
    p = groups.add_parser("badges", help="download Twitch role badge images")
    add_env_arg(p)
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.set_defaults(_handler=_run_badges)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args._handler(args))


if __name__ == "__main__":
    sys.exit(main())
