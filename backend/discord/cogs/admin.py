"""Bot administration commands"""

import logging
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_check(self, ctx: commands.Context) -> bool:
        return ctx.author.id == self.bot.owner_id if self.bot.owner_id else False

    async def cog_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        cogs = [ext.split(".")[-1] for ext in self.bot.extensions.keys() if "cogs" in ext]
        return [
            app_commands.Choice(name=cog, value=cog)
            for cog in cogs
            if current.lower() in cog.lower()
        ][:25]

    async def all_cog_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        # admin.py 位於 cogs/ 內，使用 __file__.parent 取得 cogs 目錄
        p = Path(__file__).parent
        all_cogs = []

        for item in p.iterdir():
            # 排除緩存、私有檔案與 __init__.py
            if item.name.startswith(("_", ".")):
                continue

            if item.is_file() and item.suffix == ".py":
                all_cogs.append(item.stem)
            elif item.is_dir():
                # 檢查是否為有效的 Python Package (含有 __init__.py)
                if (item / "__init__.py").exists():
                    all_cogs.append(item.name)

        return [
            app_commands.Choice(name=cog, value=cog)
            for cog in sorted(set(all_cogs))
            if current.lower() in cog.lower()
        ][:25]

    @app_commands.command(name="reload", description="重載 Cog")
    @app_commands.describe(cog="Cog 名稱（例如：fortune, games）")
    @app_commands.autocomplete(cog=cog_autocomplete)
    async def reload_cog(self, interaction: discord.Interaction, cog: str) -> None:
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("權限不足", ephemeral=True)
            logger.warning(
                f"Unauthorized reload attempt: {interaction.user} (ID: {interaction.user.id})"
            )
            return

        cog_path = f"cogs.{cog}"

        try:
            await self.bot.reload_extension(cog_path)

            guild_id = os.getenv("DISCORD_GUILD_ID")
            if guild_id:
                guild = discord.Object(id=int(guild_id))
                self.bot.tree.copy_global_to(guild=guild)
                await self.bot.tree.sync(guild=guild)
                sync_msg = "已同步到測試伺服器"
            else:
                await self.bot.tree.sync()
                sync_msg = "已全域同步"

            await interaction.response.send_message(f"已重載：{cog}\n{sync_msg}", ephemeral=True)
            logger.info(f"Reloaded cog: {cog_path} (by {interaction.user})")

        except commands.ExtensionNotLoaded:
            await interaction.response.send_message(f"Cog 未載入：{cog}", ephemeral=True)
        except commands.ExtensionNotFound:
            await interaction.response.send_message(f"找不到 Cog：{cog}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"重載失敗：{type(e).__name__}", ephemeral=True)
            logger.exception(f"Error reloading {cog_path}: {e}")

    @app_commands.command(name="load", description="載入 Cog")
    @app_commands.describe(cog="Cog 名稱")
    @app_commands.autocomplete(cog=all_cog_autocomplete)
    async def load_cog(self, interaction: discord.Interaction, cog: str) -> None:
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("權限不足", ephemeral=True)
            logger.warning(
                f"Unauthorized load attempt: {interaction.user} (ID: {interaction.user.id})"
            )
            return

        cog_path = f"cogs.{cog}"

        try:
            await self.bot.load_extension(cog_path)
            await interaction.response.send_message(f"已載入：{cog}", ephemeral=True)
            logger.info(f"Loaded cog: {cog_path} (by {interaction.user})")
        except commands.ExtensionAlreadyLoaded:
            await interaction.response.send_message(f"Cog 已載入：{cog}", ephemeral=True)
        except commands.ExtensionNotFound:
            await interaction.response.send_message(f"找不到 Cog：{cog}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"載入失敗：{type(e).__name__}", ephemeral=True)
            logger.exception(f"Error loading {cog_path}: {e}")

    @app_commands.command(name="unload", description="卸載 Cog")
    @app_commands.describe(cog="Cog 名稱")
    @app_commands.autocomplete(cog=cog_autocomplete)
    async def unload_cog(self, interaction: discord.Interaction, cog: str) -> None:
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("權限不足", ephemeral=True)
            logger.warning(
                f"Unauthorized unload attempt: {interaction.user} (ID: {interaction.user.id})"
            )
            return

        if cog.lower() == "admin":
            await interaction.response.send_message("無法卸載 Admin Cog", ephemeral=True)
            return

        cog_path = f"cogs.{cog}"

        try:
            await self.bot.unload_extension(cog_path)
            await interaction.response.send_message(f"已卸載：{cog}", ephemeral=True)
            logger.info(f"Unloaded cog: {cog_path} (by {interaction.user})")
        except commands.ExtensionNotLoaded:
            await interaction.response.send_message(f"Cog 未載入：{cog}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"卸載失敗：{type(e).__name__}", ephemeral=True)
            logger.exception(f"Error unloading {cog_path}: {e}")

    @app_commands.command(name="cogs", description="Cog 列表")
    async def list_cogs(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("權限不足", ephemeral=True)
            return

        cogs = [ext.split(".")[-1] for ext in self.bot.extensions.keys() if "cogs" in ext]

        if cogs:
            cog_list = "\n".join([f"• {cog}" for cog in sorted(cogs)])
            await interaction.response.send_message(
                f"已載入的 Cog ({len(cogs)})：\n{cog_list}", ephemeral=True
            )
        else:
            await interaction.response.send_message("沒有已載入的 Cog", ephemeral=True)

    @app_commands.command(name="sync", description="同步指令")
    async def sync_commands(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("權限不足", ephemeral=True)
            logger.warning(
                f"Unauthorized sync attempt: {interaction.user} (ID: {interaction.user.id})"
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)
            synced = await self.bot.tree.sync()
            await interaction.followup.send(f"已同步 {len(synced)} 個指令", ephemeral=True)
            logger.info(f"Synced {len(synced)} commands (by {interaction.user})")
        except Exception as e:
            await interaction.followup.send(f"同步失敗：{type(e).__name__}", ephemeral=True)
            logger.exception(f"Error syncing commands: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
