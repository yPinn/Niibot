import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="?", intents=intents)


@bot.event
async def on_ready():
    print(f"目前登入身份 --> {bot.user}")
    activity = discord.Streaming(
        name="?help", url="https://twitch.tv/llazypilot")
    await bot.change_presence(status=discord.Status.online, activity=activity)


@bot.command(name="l", help="load")
async def load(ctx, extension):
    await bot.load_extension(f"cogs.{extension}")
    await ctx.send(f"L: {extension} done.")


@bot.command(name="u", help="unload")
async def unload(ctx, extension):
    await bot.unload_extension(f"cogs.{extension}")
    await ctx.send(f"U: {extension} done.")


@bot.command(name="rl", help="reload")
async def reload(ctx, extension):
    await bot.reload_extension(f"cogs.{extension}")
    await ctx.send(f"RL: {extension} done.")


async def load_extensions():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")


async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
