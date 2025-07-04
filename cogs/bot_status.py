"""
Bot Status Management Cog - 機器人狀態管理模組
專門負責管理機器人的狀態和活動設定
"""

import asyncio
from datetime import datetime
import discord
from discord.ext import commands, tasks

from utils.logger import BotLogger
from utils.config_manager import config
from utils.util import create_activity


class BotStatus(commands.Cog):
    """機器人狀態管理器"""
    
    def __init__(self, bot):
        self.bot = bot
        self.status_set = False
        self.retry_count = 0
        self.max_retries = 3
        
        BotLogger.info("BotStatus", "狀態管理模組初始化")
    
    @commands.Cog.listener()
    async def on_ready(self):
        """當機器人準備就緒時設定狀態"""
        if not self.status_set:
            # 短暫延遲確保所有系統初始化完成
            await asyncio.sleep(0.5)
            await self.set_bot_status()
    
    async def set_bot_status(self):
        """設定機器人狀態和活動"""
        try:
            self.retry_count += 1
            
            BotLogger.warning("BotStatus", f"🎨 開始設定機器人狀態 - {self.bot.user}")
            
            # 建立活動
            activity = create_activity()
            status_obj = getattr(discord.Status, config.status, discord.Status.online)
            
            # 設定狀態
            await self.bot.change_presence(status=status_obj, activity=activity)
            
            self.status_set = True
            BotLogger.system_event(
                "狀態設定", 
                f"✅ 狀態: {config.status}, 活動: {config.activity_name}"
            )
            
            # 啟動狀態監控
            if not self.status_monitor.is_running():
                self.status_monitor.start()
                
        except Exception as e:
            BotLogger.error("BotStatus", f"狀態設定失敗 (嘗試 {self.retry_count}/{self.max_retries})", e)
            
            # 重試機制
            if self.retry_count < self.max_retries:
                await asyncio.sleep(2)
                await self.set_bot_status()
    
    @tasks.loop(minutes=30)
    async def status_monitor(self):
        """定期檢查和維護機器人狀態"""
        try:
            if not self.bot.is_ready():
                return
                
            # 檢查當前狀態是否正確
            current_status = self.bot.status
            expected_status = getattr(discord.Status, config.status, discord.Status.online)
            
            if current_status != expected_status:
                BotLogger.warning("BotStatus", f"狀態不符預期，重新設定: {current_status} -> {expected_status}")
                await self.set_bot_status()
                
        except Exception as e:
            BotLogger.error("BotStatus", "狀態監控錯誤", e)
    
    @status_monitor.before_loop
    async def before_status_monitor(self):
        """等待機器人準備就緒"""
        await self.bot.wait_until_ready()
    
    def cog_unload(self):
        """當模組卸載時停止監控"""
        if self.status_monitor.is_running():
            self.status_monitor.cancel()
        BotLogger.info("BotStatus", "狀態管理模組已卸載")
    
    @commands.command(name="status", help="手動設定機器人狀態")
    @commands.has_permissions(administrator=True)
    async def manual_status(self, ctx, status: str = None, *, activity: str = None):
        """手動設定機器人狀態
        
        Args:
            status: 狀態 (online, idle, dnd, invisible)
            activity: 活動名稱
        """
        try:
            if status:
                # 暫時更新配置
                if hasattr(discord.Status, status):
                    status_obj = getattr(discord.Status, status)
                    activity_obj = create_activity(name=activity) if activity else create_activity()
                    
                    await self.bot.change_presence(status=status_obj, activity=activity_obj)
                    
                    embed = discord.Embed(
                        title="✅ 狀態設定成功",
                        description=f"狀態: {status}\n活動: {activity or config.activity_name}",
                        color=discord.Color.green()
                    )
                    await ctx.send(embed=embed)
                    
                    BotLogger.command_used("status", ctx.author.id, ctx.guild.id if ctx.guild else 0, 
                                         f"手動設定狀態: {status}, 活動: {activity or config.activity_name}")
                else:
                    await ctx.send("❌ 無效的狀態，請使用: online, idle, dnd, invisible")
            else:
                # 顯示當前狀態
                embed = discord.Embed(
                    title="🤖 當前機器人狀態",
                    description=f"狀態: {self.bot.status}\n活動: {self.bot.activity.name if self.bot.activity else '無'}",
                    color=discord.Color.blue()
                )
                await ctx.send(embed=embed)
                
        except Exception as e:
            BotLogger.error("BotStatus", "手動狀態設定失敗", e)
            await ctx.send("❌ 狀態設定失敗")


async def setup(bot):
    """載入 Cog"""
    await bot.add_cog(BotStatus(bot))
    BotLogger.system_event("Cog載入", "BotStatus cog 已成功載入")