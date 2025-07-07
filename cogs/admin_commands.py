import os
import discord
from discord.ext import commands
from utils.logger import BotLogger
from ui.components import EmbedBuilder


class AdminCommandsEmbeds:
    """AdminCommands 專用的 Embed 建立器"""
    
    @staticmethod
    def create_cog_help():
        """建立 Cog 管理指令幫助的 Embed"""
        embed = EmbedBuilder.info(
            title="🔧 Cog 管理指令",
            description="管理機器人模組的載入、卸載和重載"
        )
        
        embed.add_field(
            name="📥 載入指令",
            value="`?cog load <名稱>` 或 `?l <名稱>`\n載入指定的 Cog 模組",
            inline=False
        )
        
        embed.add_field(
            name="📤 卸載指令", 
            value="`?cog unload <名稱>` 或 `?u <名稱>`\n卸載指定的 Cog 模組",
            inline=False
        )
        
        embed.add_field(
            name="🔄 重載指令",
            value="`?cog reload <名稱>` 或 `?rl <名稱>`\n重新載入指定的 Cog 模組",
            inline=False
        )
        
        embed.add_field(
            name="🔄 全部重載",
            value="`?cog reload_all` 或 `?rla`\n重新載入所有 Cog 模組",
            inline=False
        )
        
        embed.set_footer(text="💡 舊指令 ?l, ?u, ?rl, ?rla 仍可使用")
        
        return embed


class AdminCommands(commands.Cog):
    """管理員指令 - Cog 載入、卸載、重載功能"""
    
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="cog", invoke_without_subcommand=True)
    async def admin_cog_group(self, ctx):
        """Cog 管理指令群組"""
        if ctx.invoked_subcommand is None:
            embed = AdminCommandsEmbeds.create_cog_help()
            await ctx.send(embed=embed)

    @admin_cog_group.command(name="load", aliases=["l"])
    async def admin_cog_load(self, ctx, extension):
        """載入指定的 Cog 模組"""
        try:
            await self.bot.load_extension(f"cogs.{extension}")
            await ctx.send(f"✅ 載入: {extension}")
            BotLogger.command_used("cog.load", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"載入: {extension}")
        except Exception as e:
            error_msg = f"載入 {extension} 失敗: {str(e)}"
            await ctx.send(f"❌ {error_msg}")
            BotLogger.error("CogLoader", error_msg, e)

    @admin_cog_group.command(name="unload", aliases=["u"])
    async def admin_cog_unload(self, ctx, extension):
        """卸載指定的 Cog 模組"""
        try:
            await self.bot.unload_extension(f"cogs.{extension}")
            await ctx.send(f"✅ 卸載: {extension}")
            BotLogger.command_used("cog.unload", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"卸載: {extension}")
        except Exception as e:
            error_msg = f"卸載 {extension} 失敗: {str(e)}"
            await ctx.send(f"❌ {error_msg}")
            BotLogger.error("CogLoader", error_msg, e)

    @admin_cog_group.command(name="reload", aliases=["rl"])
    async def admin_cog_reload(self, ctx, extension):
        """重新載入指定的 Cog 模組"""
        try:
            await self.bot.reload_extension(f"cogs.{extension}")
            
            # 如果重載的不是 listener，且 listener 已載入，則重新觸發處理器註冊
            if extension != "listener" and "cogs.listener" in self.bot.extensions:
                listener_cog = self.bot.get_cog("Listener")
                if listener_cog and hasattr(listener_cog, 'wait_and_register_handlers'):
                    BotLogger.info("CogLoader", f"重新註冊 {extension} 的訊息處理器...")
                    self.bot.loop.create_task(listener_cog.wait_and_register_handlers())
            
            await ctx.send(f"✅ 重載: {extension}")
            BotLogger.command_used("cog.reload", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"重載: {extension}")
        except Exception as e:
            error_msg = f"重載 {extension} 失敗: {str(e)}"
            await ctx.send(f"❌ {error_msg}")
            BotLogger.error("CogLoader", error_msg, e)

    @admin_cog_group.command(name="reload_all", aliases=["rla"])
    async def admin_cog_reload_all(self, ctx):
        """重載所有 Cog 模組"""
        BotLogger.info("CogLoader", "🔄 開始重載所有 Cogs...")
        
        try:
            cogs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cogs")
            cog_files = [f[:-3] for f in os.listdir(cogs_dir) if f.endswith(".py")]
            
            reloaded = []
            failed = []
            
            for cog_name in cog_files:
                extension_name = f"cogs.{cog_name}"
                try:
                    if extension_name in self.bot.extensions:
                        await self.bot.reload_extension(extension_name)
                        BotLogger.info("CogLoader", f"✅ 重載: {cog_name}")
                    else:
                        await self.bot.load_extension(extension_name)
                        BotLogger.info("CogLoader", f"📥 載入: {cog_name}")
                    reloaded.append(cog_name)
                except Exception as e:
                    failed.append(f"{cog_name}: {e}")
                    BotLogger.error("CogLoader", f"❌ {cog_name} 失敗: {e}")
            
            result = f"✅ 完成: 成功 {len(reloaded)}, 失敗 {len(failed)}"
            if failed:
                result += f"\n❌ 失敗列表: {', '.join([f.split(':')[0] for f in failed])}"
            
            await ctx.send(result)
            BotLogger.command_used("cog.reload_all", ctx.author.id, ctx.guild.id if ctx.guild else 0, result)
            
        except Exception as e:
            await ctx.send(f"❌ 重載失敗: {e}")
            BotLogger.error("CogLoader", f"重載所有 Cogs 錯誤: {e}")

    # 向後相容的獨立指令
    @commands.command(name="l", help="load cog (alias for ?cog load)")
    async def load_compat(self, ctx, extension):
        """載入 Cog - 向後相容指令"""
        await self.admin_cog_load(ctx, extension)

    @commands.command(name="u", help="unload cog (alias for ?cog unload)")
    async def unload_compat(self, ctx, extension):
        """卸載 Cog - 向後相容指令"""
        await self.admin_cog_unload(ctx, extension)

    @commands.command(name="rl", help="reload cog (alias for ?cog reload)")
    async def reload_compat(self, ctx, extension):
        """重載 Cog - 向後相容指令"""
        await self.admin_cog_reload(ctx, extension)

    @commands.command(name="rla", help="reload all cogs (alias for ?cog reload_all)")
    async def reload_all_compat(self, ctx):
        """重載所有 Cogs - 向後相容指令"""
        await self.admin_cog_reload_all(ctx)


async def setup(bot):
    await bot.add_cog(AdminCommands(bot))