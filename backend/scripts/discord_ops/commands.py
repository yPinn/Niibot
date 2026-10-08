"""Manage Discord slash commands: list, clear, sync, or diff.

    npm run nb -- discord {ls|diff|sync|rm} [--env dev|stg|prod] [--guild ID] [--global] [-y]
    uv run --directory backend python -m scripts.discord_ops.commands {ls|diff|sync|rm} [...]

    ls    list registered commands       diff  preview what sync would change
    sync  push the tree to Discord       rm    clear registered commands

`diff` compares full payloads (options, descriptions, permissions), not just
names. `sync --if-changed` runs the same diff first and skips the write when
Discord already matches — CD uses it so an unchanged deploy makes no write call.

Scope resolution: --global forces global; otherwise --guild overrides the
DISCORD_GUILD_ID from the env file; otherwise that env value is used.
(Run `... --help` for which flags each subcommand accepts.)
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from scripts._lib import ENV_CHOICES
from scripts._lib import load_env as load_runtime_env

BACKEND_DIR = Path(__file__).resolve().parents[2]
BASE_DIR = BACKEND_DIR / "discord"

# Make `core` / `cogs` (under discord/) and `shared` (under backend/) importable
# the same way the bot does.
for _p in (str(BASE_DIR), str(BACKEND_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core import COGS_DIR  # noqa: E402


def load_discord_env(env: str) -> tuple[str, str | None]:
    load_runtime_env(env, service="discord")
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("[ERROR] DISCORD_BOT_TOKEN not found")
        sys.exit(1)
    return token, os.getenv("DISCORD_GUILD_ID")


def resolve_guild(args: argparse.Namespace, env_guild_id: str | None) -> str | None:
    """Resolve the effective guild scope (None means global)."""
    if getattr(args, "force_global", False):
        return None
    return args.guild or env_guild_id


def _discover_extensions() -> list[str]:
    """Scan the cogs directory for loadable extensions (mirrors bot.py)."""
    if not COGS_DIR.exists():
        return []
    return [
        f"cogs.{item.stem if item.is_file() else item.name}"
        for item in COGS_DIR.iterdir()
        if not item.name.startswith(("_", "."))
        and (
            (item.is_file() and item.suffix == ".py")
            or (item.is_dir() and (item / "__init__.py").exists())
        )
    ]


# Keys Discord echoes back but that sync never sets — never part of the comparison.
_IGNORED_KEYS = frozenset({"id", "application_id", "version", "guild_id", "dm_permission"})
# Discord fills these in server-side when unset, so compare only when both sides have them.
_SERVER_DEFAULTED_KEYS = ("contexts", "integration_types")
# A global sync scans this many guilds for stale guild-scope commands.
STRAY_SCAN_GUILD_LIMIT = 200
_FALSY_DEFAULTS = {"required": False, "autocomplete": False, "nsfw": False}


def _canonical(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise a command/option payload so local and remote compare equal when in sync.

    Drops empty / default-valued keys (Discord omits them, discord.py emits them)
    and stringifies permission bitfields (Discord returns them as strings).
    """
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _IGNORED_KEYS or value is None or value == [] or value == {}:
            continue
        if _FALSY_DEFAULTS.get(key, object()) == value:
            continue
        if key == "options":
            value = [_canonical(opt) for opt in value]
        elif key == "choices":
            value = [{"name": c["name"], "value": c["value"]} for c in value]
        elif key in ("channel_types", *_SERVER_DEFAULTED_KEYS):
            value = sorted(value)
        elif key == "default_member_permissions":
            value = str(value)
        out[key] = value
    return out


def _command_key(payload: dict[str, Any]) -> str:
    """Slash and context-menu commands may share a name; key by type too."""
    kind = payload.get("type", 1)
    return payload["name"] if kind == 1 else f"{payload['name']} (type {kind})"


def _remote_payload(cmd: app_commands.AppCommand) -> dict[str, Any]:
    payload = dict(cmd.to_dict())
    # AppCommand.to_dict() leaves these out although sync sets them.
    perms = cmd.default_member_permissions
    payload["default_member_permissions"] = None if perms is None else perms.value
    payload["nsfw"] = cmd.nsfw
    return payload


def diff_commands(
    local: list[dict[str, Any]], remote: list[dict[str, Any]]
) -> tuple[list[str], list[str], list[str]]:
    """(added, removed, changed) top-level command keys between two payload lists."""
    local_by_key = {_command_key(p): _canonical(p) for p in local}
    remote_by_key = {_command_key(p): _canonical(p) for p in remote}

    changed: list[str] = []
    for key in local_by_key.keys() & remote_by_key.keys():
        mine, theirs = dict(local_by_key[key]), dict(remote_by_key[key])
        for field in _SERVER_DEFAULTED_KEYS:
            if field not in mine or field not in theirs:
                mine.pop(field, None)
                theirs.pop(field, None)
        if mine != theirs:
            changed.append(key)

    return (
        sorted(local_by_key.keys() - remote_by_key.keys()),
        sorted(remote_by_key.keys() - local_by_key.keys()),
        sorted(changed),
    )


class _Runner(commands.Bot):
    """Minimal bot that performs one command-management action then exits.

    Provides the ``db_pool`` attribute some cogs read at load time, so
    ``sync``/``diff`` can load the full cog set without a database or gateway.
    """

    def __init__(
        self, action: str, guild_id: str | None, *, if_changed: bool = False, env: str = "dev"
    ) -> None:
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.action = action
        self.guild_id = guild_id
        self.if_changed = if_changed
        self.env = env
        self.exit_code = 0
        # Shim so every cog loads identically to production (no DB needed).
        self.db_pool = None

    async def setup_hook(self) -> None:
        try:
            print(f"Bot: {self.user} (ID: {self.user.id})")  # type: ignore[union-attr]
            await {"ls": self._ls, "rm": self._rm, "sync": self._sync, "diff": self._diff}[
                self.action
            ]()
        except discord.Forbidden:
            print("[ERROR] Permission denied")
            self.exit_code = 1
        except Exception as e:
            print(f"[ERROR] {e}")
            self.exit_code = 1
        finally:
            await self.close()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _guild_obj(self) -> discord.Object | None:
        return discord.Object(id=int(self.guild_id)) if self.guild_id else None

    async def _fetch(self) -> tuple[list, list]:
        global_cmds = await self.tree.fetch_commands()
        guild = self._guild_obj()
        guild_cmds = await self.tree.fetch_commands(guild=guild) if guild else []
        return global_cmds, guild_cmds

    def _display(self, global_cmds: list, guild_cmds: list) -> None:
        print(f"\nGlobal ({len(global_cmds)}):")
        for cmd in global_cmds:
            print(f"  /{cmd.name:<15} </{cmd.name}:{cmd.id}>")
        if not global_cmds:
            print("  (none)")
        if self.guild_id:
            print(f"\nGuild {self.guild_id} ({len(guild_cmds)}):")
            for cmd in guild_cmds:
                print(f"  /{cmd.name:<15} </{cmd.name}:{cmd.id}>")
            if not guild_cmds:
                print("  (none)")

    async def _load_tree(self) -> bool:
        """Load all cogs to populate the command tree. False if any failed."""
        loaded: list[str] = []
        failed: list[str] = []
        for ext in _discover_extensions():
            try:
                await self.load_extension(ext)
                loaded.append(ext.split(".")[-1])
            except Exception as e:
                failed.append(f"{ext.split('.')[-1]}: {type(e).__name__}: {e}")
        print(f"\nLoaded cogs ({len(loaded)}): {', '.join(loaded)}")
        if failed:
            # A missing cog would make sync delete its commands from Discord.
            print(f"\n[ERROR] {len(failed)} cog(s) failed to load — aborting:")
            for f in failed:
                print(f"  {f}")
            self.exit_code = 1
            return False
        return True

    # ── actions ──────────────────────────────────────────────────────────────

    async def _ls(self) -> None:
        global_cmds, guild_cmds = await self._fetch()
        self._display(global_cmds, guild_cmds)
        print(f"\nTotal: {len(global_cmds) + len(guild_cmds)}")

    async def _rm(self) -> None:
        global_cmds, guild_cmds = await self._fetch()
        guild = self._guild_obj()
        registered = guild_cmds if guild else global_cmds
        scope = f"guild {self.guild_id}" if guild else "global"
        if not registered:
            print(f"\nNo {scope} commands to clear.")
            return

        print(f"\n{scope.title()} ({len(registered)}):")
        for cmd in registered:
            print(f"  /{cmd.name:<15} </{cmd.name}:{cmd.id}>")
        print(f"\nClearing {len(registered)} commands...")
        self.tree.clear_commands(guild=guild)
        if guild:
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        print("Done.")

    async def _compare(self) -> tuple[list[str], list[str], list[str]]:
        """Diff the loaded tree against what Discord has for the selected scope."""
        guild = self._guild_obj()
        if guild:
            self.tree.copy_global_to(guild=guild)
        local = [cmd.to_dict(self.tree) for cmd in self.tree.get_commands(guild=guild)]
        remote = [_remote_payload(cmd) for cmd in await self.tree.fetch_commands(guild=guild)]
        added, removed, changed = diff_commands(local, remote)

        scope = f"guild {self.guild_id}" if guild else "global"
        print(f"\nDiff vs {scope}:")
        if not (added or removed or changed):
            print("  (no changes — already in sync)")
        for marker, names in (("+", added), ("-", removed), ("~", changed)):
            for name in names:
                print(f"  {marker} /{name}")
        unchanged = len(local) - len(added) - len(changed)
        print(
            f"\n{len(added)} added, {len(removed)} removed, "
            f"{len(changed)} changed, {unchanged} unchanged"
        )
        return added, removed, changed

    async def _sync(self) -> None:
        if not await self._load_tree():
            return
        if self.if_changed and not any(await self._compare()):
            print("\nSkipping sync — Discord already matches the local tree.")
        else:
            guild = self._guild_obj()
            if guild:
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                print(f"\nSynced {len(synced)} commands to guild {self.guild_id}.")
            else:
                synced = await self.tree.sync()
                print(f"\nSynced {len(synced)} commands globally (Discord read-repair enabled).")
        # Leftovers in the other scope survive any sync, changed or not.
        await self._warn_other_scope()

    async def _warn_other_scope(self) -> None:
        """Warn (never delete) about commands registered in the scope not being synced.

        A sync is a bulk overwrite of ONE scope: renamed or removed commands vanish
        from that scope, but a stale guild set survives a global sync (members see
        duplicates) and stale global commands survive a guild sync. Clearing the
        wrong scope is costly, so this only reports, as a GitHub annotation in CD.
        """
        strays: list[tuple[str, str, list[str]]] = []  # (scope label, rm flag, names)
        if self.guild_id:
            names = [c.name for c in await self.tree.fetch_commands()]
            if names:
                strays.append(("global", "--global", names))
        else:
            async for g in self.fetch_guilds(limit=STRAY_SCAN_GUILD_LIMIT):
                try:
                    cmds = await self.tree.fetch_commands(guild=discord.Object(id=g.id))
                except discord.HTTPException:
                    continue  # no applications.commands scope there — nothing registered
                if cmds:
                    strays.append(
                        (f"guild {g.id} ({g.name})", f"--guild {g.id}", [c.name for c in cmds])
                    )

        if not strays:
            print("No stale commands in the other scope.")
            return
        for scope, flag, names in strays:
            listed = ", ".join(f"/{n}" for n in sorted(names))
            print(
                f"::warning title=Stale Discord commands::{scope} still has {len(names)} "
                f"command(s) outside this sync ({listed}). Clear with: "
                f"npm run nb -- discord rm --env {self.env} {flag}"
            )

    async def _diff(self) -> None:
        if not await self._load_tree():
            return
        await self._compare()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Discord slash commands.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--env", choices=ENV_CHOICES, default="dev")
    common.add_argument("--guild", metavar="ID", help="Override DISCORD_GUILD_ID")

    sub = parser.add_subparsers(required=True)

    p_ls = sub.add_parser("ls", parents=[common], help="List registered commands")
    # Accepted like every other action: `nb discord ... --global` forwards it to all.
    p_ls.add_argument("--global", dest="force_global", action="store_true", help="Global only")
    p_ls.set_defaults(action="ls")

    p_diff = sub.add_parser("diff", parents=[common], help="Preview what sync would change")
    p_diff.add_argument("--global", dest="force_global", action="store_true", help="Force global")
    p_diff.set_defaults(action="diff")

    p_sync = sub.add_parser(
        "sync", parents=[common], aliases=["init"], help="Sync the command tree to Discord"
    )
    p_sync.add_argument("--global", dest="force_global", action="store_true", help="Force global")
    p_sync.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    p_sync.add_argument(
        "--if-changed", action="store_true", help="Only sync when the tree differs from Discord"
    )
    p_sync.set_defaults(action="sync")

    p_rm = sub.add_parser("rm", parents=[common], help="Clear registered commands")
    p_rm.add_argument("--global", dest="force_global", action="store_true", help="Force global")
    p_rm.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    p_rm.set_defaults(action="rm")

    return parser


def _confirm(action: str, guild_id: str | None, assume_yes: bool) -> bool:
    """Confirm a destructive action; True to proceed."""
    if assume_yes:
        return True
    if action == "rm":
        target = f"guild {guild_id}" if guild_id else "global"
        prompt = f"Clear ALL commands ({target})?"
    else:  # sync
        prompt = f"Sync command tree to {f'guild {guild_id}' if guild_id else 'global'}?"
    if not sys.stdin.isatty():
        print(f"[ERROR] {prompt} Refusing without --yes in a non-interactive shell.")
        return False
    return input(f"{prompt} [y/N] ").strip().lower() == "y"


async def _run(args: argparse.Namespace) -> int:
    # standalone parser sets `action`; nb sets `dc_action`
    action = getattr(args, "action", None) or getattr(args, "dc_action", "")
    assert action in ("ls", "diff", "sync", "rm"), f"unknown action {action!r}"

    verb = {"ls": "Listing", "rm": "Clearing", "sync": "Syncing", "diff": "Diffing"}[action]
    print(f"[{args.env.upper()}] {verb} commands...")

    token, env_guild_id = load_discord_env(args.env)
    guild_id = resolve_guild(args, env_guild_id)

    if action in ("rm", "sync") and not _confirm(action, guild_id, getattr(args, "yes", False)):
        print("Aborted.")
        return 0

    bot = _Runner(action, guild_id, if_changed=getattr(args, "if_changed", False), env=args.env)
    async with bot:
        await bot.start(token)
    return bot.exit_code


def run(args: argparse.Namespace) -> int:
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 130


def main() -> int:
    return run(_build_parser().parse_args())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass
