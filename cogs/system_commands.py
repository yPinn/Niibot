import subprocess
import discord
from datetime import datetime
from discord.ext import commands
from utils.util import get_deployment_info, get_version_info, get_uptime_info
from utils.logger import BotLogger
from utils.config_manager import config
from ui.components import EmbedBuilder


class SystemCommandsEmbeds:
    """SystemCommands 專用的 Embed 建立器"""
    
    @staticmethod
    def create_test_status(version_info: str, uptime_info: str, deployment_info: str, 
                          latency: int, guild_count: int, cog_count: int, author_name: str):
        """建立測試指令的 Embed"""
        embed = EmbedBuilder.success(
            title="🤖 機器人測試",
            description="機器人運行正常"
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
            value=f"延遲: {latency}ms\n伺服器數量: {guild_count}\n載入的 Cogs: {cog_count}",
            inline=True
        )
        
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text=f"請求者: {author_name}")
        
        return embed
    
    @staticmethod
    def create_system_status(environment: str, uptime_str: str, latency: int, 
                           guild_count: int, cog_count: int, python_version: str, 
                           commit_hash: str, author_name: str):
        """建立系統狀態的 Embed"""
        # 狀態顏色判斷
        if latency < 100:
            embed = EmbedBuilder.success(
                title="⚡ 系統狀態",
                description="機器人系統健康狀況"
            )
        elif latency < 300:
            embed = EmbedBuilder.warning(
                title="⚡ 系統狀態",
                description="機器人系統健康狀況"
            )
        else:
            embed = EmbedBuilder.error(
                title="⚡ 系統狀態",
                description="機器人系統健康狀況"
            )
        
        embed.add_field(
            name="🔄 運行狀態",
            value=f"環境: {environment}\n運行時間: {uptime_str}\n延遲: {latency}ms",
            inline=True
        )
        
        embed.add_field(
            name="📊 服務統計",
            value=f"伺服器: {guild_count}\nCogs: {cog_count}\nPython: {python_version}",
            inline=True
        )
        
        embed.add_field(
            name="📦 版本",
            value=f"Commit: {commit_hash}",
            inline=True
        )
        
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text=f"系統檢查 • 請求者: {author_name}")
        
        return embed


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
            
            embed = SystemCommandsEmbeds.create_test_status(
                version_info, uptime_info, deployment_info,
                round(self.bot.latency * 1000), len(self.bot.guilds), 
                len(self.bot.cogs), ctx.author.display_name
            )
            
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
            
            # 服務狀態
            deployment_info = get_deployment_info()
            try:
                python_version = deployment_info.split('Python: ')[1].split(' | ')[0] if 'Python:' in deployment_info else 'unknown'
            except (IndexError, AttributeError):
                python_version = 'unknown'
            
            # 版本資訊（簡化）
            try:
                result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], 
                                      capture_output=True, text=True, timeout=3)
                commit_hash = result.stdout.strip() if result.returncode == 0 else "unknown"
            except:
                commit_hash = "unknown"
            
            embed = SystemCommandsEmbeds.create_system_status(
                config.get('BOT_ENV', 'unknown'), uptime_str, latency,
                guild_count, cog_count, python_version, commit_hash,
                ctx.author.display_name
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            BotLogger.error("SystemStatus", "系統狀態查詢失敗", e)
            await ctx.send(f"⚡ 系統運行中\n環境: {config.get('BOT_ENV', 'unknown')}\n延遲: {round(self.bot.latency * 1000)}ms")


async def setup(bot):
    await bot.add_cog(SystemCommands(bot))