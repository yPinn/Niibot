import subprocess
import discord
from datetime import datetime
from discord.ext import commands
from utils.util import get_deployment_info, get_version_info, get_uptime_info
from utils.logger import BotLogger
from utils.config_manager import config


class SystemCommands(commands.Cog):
    """系統指令 - 機器人狀態檢查和系統資訊"""
    
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="test")
    async def test_command(self, ctx):
        """測試指令 - 顯示機器人狀態和部署信息"""
        BotLogger.info("TestCommand", f"測試指令執行 - 用戶: {ctx.author.id}")
        
        try:
            deployment_info = get_deployment_info()
            version_info = get_version_info()
            
            # 取得啟動時間
            startup_time = getattr(self.bot, '_startup_time', None)
            uptime_info = get_uptime_info(startup_time)
            
            embed = discord.Embed(
                title="🤖 機器人測試",
                description="機器人運行正常",
                color=0x00ff00
            )
            
            embed.add_field(
                name="📦 版本資訊",
                value=f"```{version_info}```",
                inline=False
            )
            
            embed.add_field(
                name="⏰ 運行資訊",
                value=f"```{uptime_info}```",
                inline=False
            )
            
            embed.add_field(
                name="📍 部署資訊",
                value=f"```{deployment_info}```",
                inline=False
            )
            
            embed.add_field(
                name="⚡ 即時狀態",
                value=f"延遲: {round(self.bot.latency * 1000)}ms\n伺服器數量: {len(self.bot.guilds)}\n載入的 Cogs: {len(self.bot.cogs)}",
                inline=True
            )
            
            embed.timestamp = discord.utils.utcnow()
            embed.set_footer(text=f"請求者: {ctx.author.display_name}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            BotLogger.error("TestCommand", "測試指令執行失敗", e)
            await ctx.send(f"✅ 測試完成（簡化模式）\n環境: {config.get('BOT_ENV', 'unknown')}")

    @commands.command(name="sys", aliases=["system"])
    async def system_status(self, ctx):
        """快速系統狀態檢查 - 精簡版機器人健康狀態"""
        BotLogger.info("SystemStatus", f"系統狀態查詢 - 用戶: {ctx.author.id}")
        
        try:
            # 計算運行時間
            uptime_str = ""
            startup_time = getattr(self.bot, '_startup_time', None)
            if startup_time:
                current_time = datetime.now(datetime.UTC)
                uptime = current_time - startup_time
                days = uptime.days
                hours, remainder = divmod(uptime.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                
                if days > 0:
                    uptime_str = f"{days}天 {hours}小時 {minutes}分鐘"
                elif hours > 0:
                    uptime_str = f"{hours}小時 {minutes}分鐘"
                else:
                    uptime_str = f"{minutes}分鐘"
            else:
                uptime_str = "未知"
            
            # 基本狀態檢查
            latency = round(self.bot.latency * 1000)
            guild_count = len(self.bot.guilds)
            cog_count = len(self.bot.cogs)
            
            # 狀態顏色判斷
            if latency < 100:
                color = 0x00ff00  # 綠色 - 良好
            elif latency < 300:
                color = 0xffff00  # 黃色 - 普通
            else:
                color = 0xff0000  # 紅色 - 較差
            
            embed = discord.Embed(
                title="⚡ 系統狀態",
                description="機器人系統健康狀況",
                color=color
            )
            
            # 核心狀態
            embed.add_field(
                name="🔄 運行狀態",
                value=f"環境: {config.get('BOT_ENV', 'unknown')}\n運行時間: {uptime_str}\n延遲: {latency}ms",
                inline=True
            )
            
            # 服務狀態
            deployment_info = get_deployment_info()
            try:
                python_version = deployment_info.split('Python: ')[1].split(' | ')[0] if 'Python:' in deployment_info else 'unknown'
            except (IndexError, AttributeError):
                python_version = 'unknown'
                
            embed.add_field(
                name="📊 服務統計",
                value=f"伺服器: {guild_count}\nCogs: {cog_count}\nPython: {python_version}",
                inline=True
            )
            
            # 版本資訊（簡化）
            try:
                result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], 
                                      capture_output=True, text=True, timeout=3)
                commit_hash = result.stdout.strip() if result.returncode == 0 else "unknown"
            except:
                commit_hash = "unknown"
            
            embed.add_field(
                name="📦 版本",
                value=f"Commit: {commit_hash}",
                inline=True
            )
            
            embed.timestamp = discord.utils.utcnow()
            embed.set_footer(text=f"系統檢查 • 請求者: {ctx.author.display_name}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            BotLogger.error("SystemStatus", "系統狀態查詢失敗", e)
            await ctx.send(f"⚡ 系統運行中\n環境: {config.get('BOT_ENV', 'unknown')}\n延遲: {round(self.bot.latency * 1000)}ms")


async def setup(bot):
    await bot.add_cog(SystemCommands(bot))