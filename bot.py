import os
import asyncio
import discord
from discord.ext import commands

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="$", intents=intents)


@bot.event
async def on_ready():
    print(f"目前登入身份 --> {bot.user}")
    game = discord.Game("$help")
    await bot.change_presence(status=discord.Status.online, activity=game)


@bot.command()
async def load(ctx, extension):
    await bot.load_extension(f"cogs.{extension}")
    await ctx.send(f"Loaded {extension} done.")


@bot.command()
async def unload(ctx, extension):
    await bot.unload_extension(f"cogs.{extension}")
    await ctx.send(f"UnLoaded {extension} done.")


@bot.command()
async def reload(ctx, extension):
    await bot.reload_extension(f"cogs.{extension}")
    await ctx.send(f"ReLoaded {extension} done.")


async def load_extensions():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")


async def main():
    async with bot:
        await load_extensions()
        await bot.start("MTM2NDEwMzgxODMyMDgwNTkxOA.GfuAe_.fE6_EXgaIm663NsMwRna8_QvB-yivw02TOJ3zI")

if __name__ == "__main__":
    asyncio.run(main())
