"""
管理功能 Cog
提供 Bot 管理和維護指令
"""

import logging
import os

from discord.ext import commands

import discord
from discord import app_commands

logger = logging.getLogger(__name__)


class Admin(commands.Cog):
    """管理功能指令"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_check(self, ctx: commands.Context) -> bool:
        """僅允許 Bot 擁有者使用此 Cog 的指令"""
        return ctx.author.id == self.bot.owner_id if self.bot.owner_id else False

    async def cog_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """已載入 Cog 名稱自動完成（用於 reload/unload）"""
        # 獲取所有已載入的 Cog 名稱
        cogs = [
            ext.split(".")[-1]
            for ext in self.bot.extensions.keys()
            if "cogs" in ext
        ]
        # 過濾符合輸入的 Cog
        return [
            app_commands.Choice(name=cog, value=cog)
            for cog in cogs
            if current.lower() in cog.lower()
        ][:25]  # Discord 限制最多 25 個選項

    async def all_cog_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """所有可用 Cog 名稱自動完成（用於 load）"""
        # 定義所有可用的 Cog（與 bot.py 中的列表對應）
        all_cogs = ["admin", "moderation", "utility", "events", "fortune", "giveaway", "games"]
        # 過濾符合輸入的 Cog
        return [
            app_commands.Choice(name=cog, value=cog)
            for cog in all_cogs
            if current.lower() in cog.lower()
        ][:25]

    @app_commands.command(name="reload", description="重載指定的 Cog")
    @app_commands.describe(cog="Cog 名稱（例如：fortune, games）")
    @app_commands.autocomplete(cog=cog_autocomplete)
    async def reload_cog(self, interaction: discord.Interaction, cog: str):
        """重載指定的 Cog"""
        # 檢查權限
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("權限不足", ephemeral=True)
            logger.warning(
                f"未授權的重載嘗試：用戶 {interaction.user} (ID: {interaction.user.id})"
            )
            return

        cog_path = f"cogs.{cog}"

        try:
            # 嘗試重載
            await self.bot.reload_extension(cog_path)

            # 同步指令到 Discord（確保新的指令變更生效）
            guild_id = os.getenv("DISCORD_GUILD_ID")
            if guild_id:
                # 同步到測試伺服器
                guild = discord.Object(id=int(guild_id))
                self.bot.tree.copy_global_to(guild=guild)
                await self.bot.tree.sync(guild=guild)
                sync_msg = "已同步到測試伺服器"
            else:
                # 全域同步
                await self.bot.tree.sync()
                sync_msg = "已全域同步"

            await interaction.response.send_message(
                f"✅ 已重載：{cog}\n📡 {sync_msg}", ephemeral=True
            )
            logger.info(f"成功重載 Cog: {cog_path} (執行者: {interaction.user})")

        except commands.ExtensionNotLoaded:
            await interaction.response.send_message(f"Cog 未載入：{cog}", ephemeral=True)
            logger.error(f"重載失敗：Cog {cog_path} 未載入")

        except commands.ExtensionNotFound:
            await interaction.response.send_message(f"找不到 Cog：{cog}", ephemeral=True)
            logger.error(f"重載失敗：找不到 Cog {cog_path}")

        except Exception as e:
            await interaction.response.send_message(
                f"重載失敗：{type(e).__name__}", ephemeral=True
            )
            logger.exception(f"重載 Cog {cog_path} 時發生錯誤：{e}")

    @app_commands.command(name="load", description="載入指定的 Cog")
    @app_commands.describe(cog="Cog 名稱")
    @app_commands.autocomplete(cog=all_cog_autocomplete)
    async def load_cog(self, interaction: discord.Interaction, cog: str):
        """載入指定的 Cog"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("權限不足", ephemeral=True)
            logger.warning(
                f"未授權的載入嘗試：用戶 {interaction.user} (ID: {interaction.user.id})"
            )
            return

        cog_path = f"cogs.{cog}"

        try:
            await self.bot.load_extension(cog_path)
            await interaction.response.send_message(f"已載入：{cog}", ephemeral=True)
            logger.info(f"成功載入 Cog: {cog_path} (執行者: {interaction.user})")

        except commands.ExtensionAlreadyLoaded:
            await interaction.response.send_message(f"Cog 已載入：{cog}", ephemeral=True)
            logger.warning(f"載入失敗：Cog {cog_path} 已經載入")

        except commands.ExtensionNotFound:
            await interaction.response.send_message(f"找不到 Cog：{cog}", ephemeral=True)
            logger.error(f"載入失敗：找不到 Cog {cog_path}")

        except Exception as e:
            await interaction.response.send_message(
                f"載入失敗：{type(e).__name__}", ephemeral=True
            )
            logger.exception(f"載入 Cog {cog_path} 時發生錯誤：{e}")

    @app_commands.command(name="unload", description="卸載指定的 Cog")
    @app_commands.describe(cog="Cog 名稱")
    @app_commands.autocomplete(cog=cog_autocomplete)
    async def unload_cog(self, interaction: discord.Interaction, cog: str):
        """卸載指定的 Cog"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("權限不足", ephemeral=True)
            logger.warning(
                f"未授權的卸載嘗試：用戶 {interaction.user} (ID: {interaction.user.id})"
            )
            return

        # 防止卸載 admin 自己
        if cog.lower() == "admin":
            await interaction.response.send_message(
                "無法卸載 Admin Cog", ephemeral=True
            )
            logger.warning(f"嘗試卸載 Admin Cog (執行者: {interaction.user})")
            return

        cog_path = f"cogs.{cog}"

        try:
            await self.bot.unload_extension(cog_path)
            await interaction.response.send_message(f"已卸載：{cog}", ephemeral=True)
            logger.info(f"成功卸載 Cog: {cog_path} (執行者: {interaction.user})")

        except commands.ExtensionNotLoaded:
            await interaction.response.send_message(f"Cog 未載入：{cog}", ephemeral=True)
            logger.error(f"卸載失敗：Cog {cog_path} 未載入")

        except Exception as e:
            await interaction.response.send_message(
                f"卸載失敗：{type(e).__name__}", ephemeral=True
            )
            logger.exception(f"卸載 Cog {cog_path} 時發生錯誤：{e}")

    @app_commands.command(name="cogs", description="列出所有已載入的 Cog")
    async def list_cogs(self, interaction: discord.Interaction):
        """列出所有已載入的 Cog"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("權限不足", ephemeral=True)
            return

        cogs = [
            ext.split(".")[-1] for ext in self.bot.extensions.keys() if "cogs" in ext
        ]

        if cogs:
            cog_list = "\n".join([f"• {cog}" for cog in sorted(cogs)])
            await interaction.response.send_message(
                f"已載入的 Cog ({len(cogs)}):\n{cog_list}", ephemeral=True
            )
            logger.info(f"列出 Cog 清單 (執行者: {interaction.user})")
        else:
            await interaction.response.send_message("沒有已載入的 Cog", ephemeral=True)

    @app_commands.command(name="sync", description="同步指令樹到 Discord")
    async def sync_commands(self, interaction: discord.Interaction):
        """同步指令樹到 Discord"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("權限不足", ephemeral=True)
            logger.warning(
                f"未授權的同步嘗試：用戶 {interaction.user} (ID: {interaction.user.id})"
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)
            synced = await self.bot.tree.sync()
            await interaction.followup.send(f"已同步 {len(synced)} 個指令", ephemeral=True)
            logger.info(
                f"成功同步 {len(synced)} 個指令到 Discord (執行者: {interaction.user})"
            )

        except Exception as e:
            await interaction.followup.send(
                f"同步失敗：{type(e).__name__}", ephemeral=True
            )
            logger.exception(f"同步指令時發生錯誤：{e}")


async def setup(bot: commands.Bot):
    """載入 Cog"""
    await bot.add_cog(Admin(bot))
