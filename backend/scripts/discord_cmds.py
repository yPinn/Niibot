"""Manage Discord slash commands: list, clear, sync, or diff.

    python scripts/discord_cmds.py ls    [--prod] [--guild ID]
    python scripts/discord_cmds.py diff  [--prod] [--guild ID] [--global]
    python scripts/discord_cmds.py sync  [--prod] [--guild ID] [--global] [--yes]
    python scripts/discord_cmds.py rm    [--prod] [--guild ID] [--global] [--yes]
    npm run nb -- discord sync --prod

Scope resolution: --global forces global; otherwise --guild overrides the
DISCORD_GUILD_ID from the env file; otherwise that env value is used.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = BACKEND_DIR / "discord"

# Make `core` / `cogs` (under discord/) and `shared` (under backend/) importable
# the same way the bot does.
for _p in (str(BASE_DIR), str(BACKEND_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core import COGS_DIR, RateLimitMonitor  # noqa: E402

_SUBCOMMAND_TYPES = (
    discord.AppCommandOptionType.subcommand,
    discord.AppCommandOptionType.subcommand_group,
)


def load_env(prod: bool) -> tuple[str, str | None]:
    env_file = BASE_DIR / (".env.production" if prod else ".env")
    if not env_file.exists():
        print(f"[ERROR] {env_file} not found")
        sys.exit(1)
    load_dotenv(dotenv_path=env_file, encoding="utf-8", override=True)
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


def _flatten_local(cmds: list) -> set[str]:
    """Qualified leaf-command names from the local app_commands tree."""
    out: set[str] = set()
    for cmd in cmds:
        if isinstance(cmd, app_commands.Group):
            for sub in cmd.walk_commands():
                if not isinstance(sub, app_commands.Group):
                    out.add(sub.qualified_name)
        else:
            out.add(cmd.qualified_name)
    return out


def _flatten_registered(cmds: list) -> set[str]:
    """Qualified leaf-command names from commands fetched off Discord."""
    out: set[str] = set()

    def walk(node, prefix: str) -> None:
        name = f"{prefix} {node.name}".strip()
        subs = [o for o in (getattr(node, "options", None) or []) if o.type in _SUBCOMMAND_TYPES]
        if subs:
            for s in subs:
                walk(s, name)
        else:
            out.add(name)

    for cmd in cmds:
        walk(cmd, "")
    return out


class _Runner(commands.Bot):
    """Minimal bot that performs one command-management action then exits.

    Provides the ``rate_limiter`` / ``db_pool`` attributes some cogs read at load
    time, so ``sync``/``diff`` can load the full cog set without a database or
    gateway.
    """

    def __init__(self, action: str, guild_id: str | None) -> None:
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.action = action
        self.guild_id = guild_id
        self.exit_code = 0
        # Shims so every cog loads identically to production (no DB needed).
        self.rate_limiter = RateLimitMonitor(self)
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
        if not global_cmds and not guild_cmds:
            print("\nNo commands to clear.")
            return
        self._display(global_cmds, guild_cmds)
        print(f"\nClearing {len(global_cmds) + len(guild_cmds)} commands...")
        self.tree.clear_commands(guild=None)
        await self.tree.sync()
        guild = self._guild_obj()
        if guild:
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
        print("Done.")

    async def _sync(self) -> None:
        if not await self._load_tree():
            return
        guild = self._guild_obj()
        if guild:
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"\nSynced {len(synced)} commands to guild {self.guild_id}.")
        else:
            synced = await self.tree.sync()
            print(f"\nSynced {len(synced)} commands globally (propagation up to ~1h).")

    async def _diff(self) -> None:
        if not await self._load_tree():
            return
        local = _flatten_local(self.tree.get_commands())
        guild = self._guild_obj()
        registered = _flatten_registered(await self.tree.fetch_commands(guild=guild))
        scope = f"guild {self.guild_id}" if guild else "global"

        added = sorted(local - registered)
        removed = sorted(registered - local)
        unchanged = len(local & registered)

        print(f"\nDiff vs {scope} (command names; sync would apply these):")
        if not added and not removed:
            print("  (no changes — already in sync)")
        for n in added:
            print(f"  + {n}")
        for n in removed:
            print(f"  - {n}")
        print(f"\n{len(added)} added, {len(removed)} removed, {unchanged} unchanged")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Discord slash commands.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--prod", action="store_true", help="Use .env.production")
    common.add_argument("--guild", metavar="ID", help="Override DISCORD_GUILD_ID")

    sub = parser.add_subparsers(required=True)

    p_ls = sub.add_parser("ls", parents=[common], help="List registered commands")
    p_ls.set_defaults(action="ls")

    p_diff = sub.add_parser("diff", parents=[common], help="Preview what sync would change")
    p_diff.add_argument("--global", dest="force_global", action="store_true", help="Force global")
    p_diff.set_defaults(action="diff")

    p_sync = sub.add_parser(
        "sync", parents=[common], aliases=["init"], help="Sync the command tree to Discord"
    )
    p_sync.add_argument("--global", dest="force_global", action="store_true", help="Force global")
    p_sync.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
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
        target = "global" + (f" + guild {guild_id}" if guild_id else "")
        prompt = f"Clear ALL commands ({target})?"
    else:  # sync
        prompt = f"Sync command tree to {f'guild {guild_id}' if guild_id else 'global'}?"
    if not sys.stdin.isatty():
        print(f"[ERROR] {prompt} Refusing without --yes in a non-interactive shell.")
        return False
    return input(f"{prompt} [y/N] ").strip().lower() == "y"


async def _run(args: argparse.Namespace) -> int:
    action = getattr(args, "action", None) or getattr(args, "dc_action", "")
    assert action in ("ls", "diff", "sync", "rm"), f"unknown action {action!r}"

    label = "PRODUCTION" if args.prod else "DEV"
    env_file = ".env.production" if args.prod else ".env"
    verb = {"ls": "Listing", "rm": "Clearing", "sync": "Syncing", "diff": "Diffing"}[action]
    print(f"[{label}] {verb} commands...")
    print(f"Config: {env_file}")

    token, env_guild_id = load_env(args.prod)
    guild_id = resolve_guild(args, env_guild_id)

    if action in ("rm", "sync") and not _confirm(action, guild_id, getattr(args, "yes", False)):
        print("Aborted.")
        return 0

    bot = _Runner(action, guild_id)
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
