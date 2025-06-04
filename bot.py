import asyncio
import os
import config
from utils.util import create_activity
import discord
from discord.ext import commands

# 根據 BOT_ENV 匯入不同設定
ENV = os.getenv("BOT_ENV", "local")
if ENV == "prod":
    import config_prod as config
else:
    import config_local as config

if config.USE_KEEP_ALIVE:
    from keep_alive import keep_alive
    keep_alive()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents)


@bot.event
async def on_ready():
    print(f"使用者 --> {bot.user}")
    print(f"目前環境 --> {ENV}")
    activity = create_activity(config.ACTIVITY_TYPE, config.ACTIVITY_NAME, getattr(
        config, "ACTIVITY_URL", None))
    await bot.change_presence(status=getattr(discord.Status, config.STATUS), activity=activity)


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
            print(f"載入 {filename}")
            await bot.load_extension(f"cogs.{filename[:-3]}")
    print("----------------------------")


async def main():
    async with bot:
        await load_extensions()
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
