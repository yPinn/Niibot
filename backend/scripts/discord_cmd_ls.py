"""List registered Discord slash commands."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent / "discord"


def load_env(env: str) -> tuple[str, str | None]:
    env_file = BASE_DIR / (".env.production" if env == "prod" else ".env")
    if not env_file.exists():
        print(f"[ERROR] {env_file} not found")
        sys.exit(1)
    load_dotenv(dotenv_path=env_file, encoding="utf-8", override=True)
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("[ERROR] DISCORD_BOT_TOKEN not found")
        sys.exit(1)
    return token, os.getenv("DISCORD_GUILD_ID")


class Bot(commands.Bot):
    def __init__(self, guild_id: str | None):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.guild_id = guild_id

    async def setup_hook(self) -> None:
        try:
            print(f"Bot: {self.user} (ID: {self.user.id})")  # type: ignore

            # Fetch commands
            global_cmds = await self.tree.fetch_commands()
            guild_cmds = []
            if self.guild_id:
                guild_cmds = await self.tree.fetch_commands(
                    guild=discord.Object(id=int(self.guild_id))
                )

            # Display
            print(f"\nGlobal ({len(global_cmds)}):")
            for cmd in global_cmds:
                print(f"  /{cmd.name:<15} </{cmd.name}:{cmd.id}>")
            if not global_cmds:
                print("  (none)")

            if self.guild_id:
                print(f"\nGuild ({len(guild_cmds)}):")
                for cmd in guild_cmds:
                    print(f"  /{cmd.name:<15} </{cmd.name}:{cmd.id}>")
                if not guild_cmds:
                    print("  (none)")

            print(f"\nTotal: {len(global_cmds) + len(guild_cmds)}")

        except Exception as e:
            print(f"[ERROR] {e}")
        finally:
            await self.close()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prod", action="store_true", help="Use .env.production")
    args = parser.parse_args()

    env = "prod" if args.prod else "dev"
    env_file = ".env.production" if args.prod else ".env"
    label = "PRODUCTION" if args.prod else "DEV"
    print(f"[{label}] Listing commands...")
    print(f"Config: {env_file}")

    token, guild_id = load_env(env)
    async with Bot(guild_id) as bot:
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
