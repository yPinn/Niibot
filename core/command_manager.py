import discord
from discord.ext import commands
from utils.logger import BotLogger
from utils import util


class CommandManager:
    """指令禁用管理系統"""
    
    def __init__(self, bot):
        self.bot = bot
        self._disabled_commands = {}  # {指令名稱: 禁用原因}
        self._disabled_commands_file = "disabled_commands.json"
        self._loaded = False
    
    async def load_disabled_commands(self):
        """載入禁用指令列表"""
        if self._loaded:
            return
            
        try:
            file_path = util.get_data_file_path(self._disabled_commands_file)
            self._disabled_commands = await util.read_json(file_path)
            if not isinstance(self._disabled_commands, dict):
                self._disabled_commands = {}
            BotLogger.info("CommandDisable", f"載入 {len(self._disabled_commands)} 個禁用指令")
            self._loaded = True
        except Exception as e:
            BotLogger.warning("CommandDisable", f"載入禁用指令列表失敗: {e}")
            self._disabled_commands = {}
            self._loaded = True

    async def save_disabled_commands(self):
        """儲存禁用指令列表"""
        try:
            file_path = util.get_data_file_path(self._disabled_commands_file)
            await util.write_json(file_path, self._disabled_commands)
        except Exception as e:
            BotLogger.error("CommandDisable", f"儲存禁用指令列表失敗: {e}")

    async def check_command_enabled(self, ctx):
        """檢查指令是否被禁用"""
        # 確保已載入禁用指令列表
        await self.load_disabled_commands()
        
        if ctx.command is None:
            return True
        
        command_name = ctx.command.qualified_name
        if command_name in self._disabled_commands:
            reason = self._disabled_commands[command_name]
            
            # 創建更詳細的禁用提示 embed
            embed = discord.Embed(
                title="🚫 指令被禁用",
                description=f"指令 `{command_name}` 目前無法使用",
                color=discord.Color.red()
            )
            
            embed.add_field(
                name="📝 禁用原因",
                value=reason,
                inline=False
            )
            
            embed.add_field(
                name="💡 說明",
                value="如需啟用此指令，請聯繫管理員",
                inline=False
            )
            
            embed.set_footer(text=f"請求者: {ctx.author.display_name}")
            
            try:
                await ctx.send(embed=embed)
            except discord.HTTPException:
                # 如果 embed 發送失敗，使用簡單訊息
                await ctx.send(f"❌ 指令 `{command_name}` 目前被禁用\n原因: {reason}")
            
            BotLogger.info("CommandDisable", f"用戶 {ctx.author.display_name} ({ctx.author.id}) 嘗試使用被禁用的指令: {command_name}")
            return False
        return True

    async def disable_command(self, ctx: commands.Context, command_name: str, reason: str = "管理員禁用"):
        """禁用指定指令"""
        # 確保已載入禁用指令列表
        await self.load_disabled_commands()
        
        # 防止禁用關鍵管理指令
        protected_commands = ["disable", "enable", "sys"]
        if command_name in protected_commands:
            embed = discord.Embed(
                title="🛡️ 受保護指令",
                description=f"指令 `{command_name}` 是系統核心指令，無法被禁用",
                color=discord.Color.orange()
            )
            embed.add_field(
                name="🔒 受保護指令列表",
                value="• `disable` - 禁用指令管理\n• `enable` - 啟用指令管理\n• `sys` - 系統狀態檢查",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        # 檢查指令是否存在
        command = self.bot.get_command(command_name)
        if not command:
            # 提供相似指令建議
            all_commands = [cmd.name for cmd in self.bot.commands]
            suggestions = [cmd for cmd in all_commands if command_name.lower() in cmd.lower() or cmd.lower() in command_name.lower()]
            
            embed = discord.Embed(
                title="❌ 指令不存在",
                description=f"找不到指令: `{command_name}`",
                color=discord.Color.red()
            )
            
            if suggestions:
                embed.add_field(
                    name="💡 相似指令建議",
                    value="\n".join([f"• `{cmd}`" for cmd in suggestions[:5]]),
                    inline=False
                )
            
            embed.add_field(
                name="📝 提示",
                value="使用 `?help` 查看所有可用指令",
                inline=False
            )
            
            await ctx.send(embed=embed)
            return
        
        # 檢查指令是否已被禁用
        if command_name in self._disabled_commands:
            embed = discord.Embed(
                title="⚠️ 指令已被禁用",
                description=f"指令 `{command_name}` 已經被禁用",
                color=discord.Color.orange()
            )
            embed.add_field(
                name="📝 當前禁用原因",
                value=self._disabled_commands[command_name],
                inline=False
            )
            embed.add_field(
                name="💡 操作選項",
                value=f"如需修改原因，請先使用 `?enable {command_name}` 然後重新禁用",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        # 禁用指令
        self._disabled_commands[command_name] = reason
        await self.save_disabled_commands()
        
        embed = discord.Embed(
            title="✅ 指令已禁用",
            description=f"成功禁用指令 `{command_name}`",
            color=discord.Color.green()
        )
        embed.add_field(
            name="📝 禁用原因",
            value=reason,
            inline=False
        )
        embed.add_field(
            name="🔄 恢復方式",
            value=f"使用 `?enable {command_name}` 重新啟用",
            inline=False
        )
        embed.set_footer(text=f"操作者: {ctx.author.display_name}")
        
        await ctx.send(embed=embed)
        BotLogger.command_used("disable", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"禁用指令: {command_name} - 原因: {reason}")

    async def enable_command(self, ctx: commands.Context, command_name: str):
        """啟用指定指令"""
        # 確保已載入禁用指令列表
        await self.load_disabled_commands()
        
        if command_name not in self._disabled_commands:
            embed = discord.Embed(
                title="ℹ️ 指令狀態",
                description=f"指令 `{command_name}` 目前未被禁用",
                color=discord.Color.blue()
            )
            
            # 檢查指令是否存在
            command = self.bot.get_command(command_name)
            if command:
                embed.add_field(
                    name="✅ 指令狀態",
                    value="此指令正常可用，無需啟用",
                    inline=False
                )
            else:
                embed.add_field(
                    name="❌ 指令狀態", 
                    value="此指令不存在於系統中",
                    inline=False
                )
                
            embed.add_field(
                name="📋 查看禁用列表",
                value="使用 `?disabled` 查看所有被禁用的指令",
                inline=False
            )
            
            await ctx.send(embed=embed)
            return
        
        # 記錄原因用於日誌
        original_reason = self._disabled_commands[command_name]
        
        # 啟用指令
        del self._disabled_commands[command_name]
        await self.save_disabled_commands()
        
        embed = discord.Embed(
            title="✅ 指令已啟用",
            description=f"成功啟用指令 `{command_name}`",
            color=discord.Color.green()
        )
        embed.add_field(
            name="📝 原禁用原因",
            value=original_reason,
            inline=False
        )
        embed.add_field(
            name="🎯 當前狀態",
            value="指令現在可以正常使用",
            inline=False
        )
        embed.set_footer(text=f"操作者: {ctx.author.display_name}")
        
        await ctx.send(embed=embed)
        BotLogger.command_used("enable", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"啟用指令: {command_name} - 原因: {original_reason}")

    async def list_disabled_commands(self, ctx: commands.Context):
        """查看當前被禁用的指令列表"""
        # 確保已載入禁用指令列表
        await self.load_disabled_commands()
        
        if not self._disabled_commands:
            embed = discord.Embed(
                title="✅ 指令狀態良好",
                description="目前沒有被禁用的指令",
                color=discord.Color.green()
            )
            embed.add_field(
                name="🎯 系統狀態",
                value="所有指令都正常可用",
                inline=False
            )
            embed.add_field(
                name="🔧 管理指令",
                value="• `?disable <指令名> [原因]` - 禁用指令\n• `?enable <指令名>` - 啟用指令",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title="🚫 被禁用的指令",
            description=f"共有 {len(self._disabled_commands)} 個指令被禁用",
            color=discord.Color.red()
        )
        
        # 按字母順序排序
        sorted_commands = sorted(self._disabled_commands.items())
        
        for cmd_name, reason in sorted_commands:
            embed.add_field(
                name=f"🔒 `{cmd_name}`",
                value=f"**原因:** {reason}\n**啟用:** `?enable {cmd_name}`",
                inline=False
            )
        
        embed.add_field(
            name="💡 批量管理",
            value="如需啟用多個指令，請逐一使用 `?enable` 指令",
            inline=False
        )
        
        embed.set_footer(text=f"查詢者: {ctx.author.display_name}")
        
        await ctx.send(embed=embed)
        BotLogger.command_used("disabled", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"查看 {len(self._disabled_commands)} 個禁用指令")


def setup_command_manager(bot):
    """設置指令管理器並註冊指令"""
    command_manager = CommandManager(bot)
    
    # 添加全域指令檢查
    bot.add_check(command_manager.check_command_enabled)
    
    @bot.command(name="disable", help="禁用指令")
    async def disable_command(ctx: commands.Context, command_name: str, *, reason: str = "管理員禁用"):
        await command_manager.disable_command(ctx, command_name, reason)

    @bot.command(name="enable", help="啟用指令")
    async def enable_command(ctx: commands.Context, command_name: str):
        await command_manager.enable_command(ctx, command_name)

    @bot.command(name="disabled", help="查看被禁用的指令")
    async def list_disabled_commands(ctx: commands.Context):
        await command_manager.list_disabled_commands(ctx)
    
    return command_manager