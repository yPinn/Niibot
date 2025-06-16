"""
權限管理指令模組
提供管理權限系統的指令
"""
import discord
from discord.ext import commands

from utils.permissions import (
    permission_manager, PermissionLevel, 
    admin_only, moderator_only, require_permission
)
from utils.logger import BotLogger


class PermissionsAdmin(commands.Cog):
    """權限管理指令"""
    
    def __init__(self, bot):
        self.bot = bot
        # 設定訊息處理器優先級
        self.message_handler_priority = -10  # 低優先級，不需要處理一般訊息
    
    async def handle_on_message(self, message: discord.Message):
        """權限模組不需要處理一般訊息"""
        pass
    
    @commands.group(name="perm", help="權限管理指令")
    @admin_only()
    async def permission_group(self, ctx):
        """權限管理指令群組"""
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(
                title="🔐 權限管理系統",
                description="管理機器人權限和用戶等級",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="📋 可用指令",
                value=(
                    "`?perm info [@用戶]` - 查看用戶權限資訊\n"
                    "`?perm admin <@用戶>` - 設為機器人管理員\n"
                    "`?perm unadmin <@用戶>` - 移除管理員身份\n"
                    "`?perm trust <@用戶>` - 設為信任用戶\n"
                    "`?perm untrust <@用戶>` - 取消信任用戶\n"
                    "`?perm ban <@用戶>` - 禁用用戶\n"
                    "`?perm unban <@用戶>` - 解禁用戶\n"
                    "`?perm list` - 列出特殊權限用戶\n"
                    "`?perm cleanup` - 清理速率限制記錄"
                ),
                inline=False
            )
            
            embed.add_field(
                name="📊 權限等級",
                value=(
                    "🔴 `OWNER` - 機器人擁有者\n"
                    "🟠 `ADMIN` - 管理員\n"
                    "🟡 `MODERATOR` - 版主\n"
                    "🟢 `TRUSTED` - 信任用戶\n"
                    "🔵 `MEMBER` - 伺服器成員\n"
                    "⚪ `EVERYONE` - 所有人"
                ),
                inline=True
            )
            
            await ctx.send(embed=embed)
    
    @permission_group.command(name="info")
    @moderator_only()
    async def permission_info(self, ctx, user: discord.User = None):
        """查看用戶權限資訊"""
        if user is None:
            user = ctx.author
        
        user_level = permission_manager.get_user_level(user.id, ctx.guild)
        
        embed = discord.Embed(
            title=f"🔍 權限資訊 - {user.display_name}",
            color=discord.Color.green()
        )
        
        # 權限等級
        level_emoji = {
            PermissionLevel.OWNER: "🔴",
            PermissionLevel.ADMIN: "🟠", 
            PermissionLevel.MODERATOR: "🟡",
            PermissionLevel.TRUSTED: "🟢",
            PermissionLevel.MEMBER: "🔵",
            PermissionLevel.EVERYONE: "⚪"
        }
        
        embed.add_field(
            name="📊 權限等級",
            value=f"{level_emoji.get(user_level, '❓')} {user_level.name}",
            inline=True
        )
        
        # 特殊權限
        special_perms = []
        if user.id in permission_manager._custom_permissions['bot_admin']:
            special_perms.append("🔧 機器人管理員")
        if user.id in permission_manager._custom_permissions['trusted_users']:
            special_perms.append("✅ 信任用戶")
        if user.id in permission_manager._custom_permissions['banned_users']:
            special_perms.append("❌ 被禁用戶")
        
        embed.add_field(
            name="🏷️ 特殊權限",
            value="\n".join(special_perms) if special_perms else "無",
            inline=True
        )
        
        # Discord 權限（如果在伺服器中）
        if ctx.guild:
            member = ctx.guild.get_member(user.id)
            if member:
                key_perms = []
                if member.guild_permissions.administrator:
                    key_perms.append("👑 管理員")
                if member.guild_permissions.manage_messages:
                    key_perms.append("📝 管理訊息")
                if member.guild_permissions.kick_members:
                    key_perms.append("👢 踢出成員")
                if member.guild_permissions.ban_members:
                    key_perms.append("🔨 封鎖成員")
                
                embed.add_field(
                    name="🎭 Discord 權限",
                    value="\n".join(key_perms) if key_perms else "基本權限",
                    inline=False
                )
        
        # 速率限制資訊
        if user.id in permission_manager._rate_limits:
            rate_info = permission_manager._rate_limits[user.id]
            if rate_info:
                embed.add_field(
                    name="⏱️ 速率限制",
                    value=f"正在追蹤 {len(rate_info)} 個指令的使用頻率",
                    inline=True
                )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"用戶 ID: {user.id}")
        
        await ctx.send(embed=embed)
        BotLogger.command_used("perm info", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"查看: {user.id}")
    
    @permission_group.command(name="trust")
    @admin_only()
    async def add_trusted(self, ctx, user: discord.User):
        """添加信任用戶"""
        if user.id in permission_manager._custom_permissions['trusted_users']:
            await ctx.send(f"❌ {user.mention} 已經是信任用戶")
            return
        
        permission_manager.add_trusted_user(user.id)
        await ctx.send(f"✅ {user.mention} 已設為信任用戶")
        BotLogger.command_used("perm trust", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"添加: {user.id}")
    
    @permission_group.command(name="untrust")
    @admin_only()
    async def remove_trusted(self, ctx, user: discord.User):
        """移除信任用戶"""
        if user.id not in permission_manager._custom_permissions['trusted_users']:
            await ctx.send(f"❌ {user.mention} 不是信任用戶")
            return
        
        permission_manager.remove_trusted_user(user.id)
        await ctx.send(f"✅ 已移除 {user.mention} 的信任用戶身份")
        BotLogger.command_used("perm untrust", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"移除: {user.id}")
    
    @permission_group.command(name="admin")
    @admin_only()
    async def add_admin(self, ctx, user: discord.User):
        """添加機器人管理員"""
        if user.id in permission_manager._custom_permissions['bot_admin']:
            await ctx.send(f"❌ {user.mention} 已經是機器人管理員")
            return
        
        permission_manager._custom_permissions['bot_admin'].add(user.id)
        await ctx.send(f"👑 {user.mention} 已設為機器人管理員")
        BotLogger.command_used("perm admin", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"添加管理員: {user.id}")
    
    @permission_group.command(name="unadmin")
    @admin_only()
    async def remove_admin(self, ctx, user: discord.User):
        """移除機器人管理員"""
        if user.id not in permission_manager._custom_permissions['bot_admin']:
            await ctx.send(f"❌ {user.mention} 不是機器人管理員")
            return
        
        # 防止移除自己（避免沒有管理員的情況）
        if user.id == ctx.author.id:
            await ctx.send(f"❌ 不能移除自己的管理員權限")
            return
        
        permission_manager._custom_permissions['bot_admin'].discard(user.id)
        await ctx.send(f"👑 已移除 {user.mention} 的機器人管理員身份")
        BotLogger.command_used("perm unadmin", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"移除管理員: {user.id}")

    @permission_group.command(name="ban")
    @admin_only()
    async def ban_user(self, ctx, user: discord.User):
        """禁用用戶"""
        if user.id in permission_manager._custom_permissions['banned_users']:
            await ctx.send(f"❌ {user.mention} 已經被禁用")
            return
        
        # 不能禁用管理員
        if user.id in permission_manager._custom_permissions['bot_admin']:
            await ctx.send(f"❌ 無法禁用機器人管理員")
            return
        
        permission_manager.ban_user(user.id)
        await ctx.send(f"🔒 {user.mention} 已被禁用機器人功能")
        BotLogger.command_used("perm ban", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"禁用: {user.id}")
    
    @permission_group.command(name="unban")
    @admin_only()
    async def unban_user(self, ctx, user: discord.User):
        """解禁用戶"""
        if user.id not in permission_manager._custom_permissions['banned_users']:
            await ctx.send(f"❌ {user.mention} 沒有被禁用")
            return
        
        permission_manager.unban_user(user.id)
        await ctx.send(f"🔓 {user.mention} 已解除禁用")
        BotLogger.command_used("perm unban", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"解禁: {user.id}")
    
    @permission_group.command(name="list")
    @moderator_only()
    async def list_special_users(self, ctx):
        """列出特殊權限用戶"""
        embed = discord.Embed(
            title="👥 特殊權限用戶列表",
            color=discord.Color.blue()
        )
        
        # 管理員
        admins = permission_manager._custom_permissions['bot_admin']
        if admins:
            admin_mentions = []
            for user_id in list(admins)[:10]:  # 最多顯示10個
                try:
                    user = await self.bot.fetch_user(user_id)
                    admin_mentions.append(f"• {user.mention} (`{user_id}`)")
                except:
                    admin_mentions.append(f"• 未知用戶 (`{user_id}`)")
            
            if len(admins) > 10:
                admin_mentions.append(f"• ... 及其他 {len(admins) - 10} 人")
            
            embed.add_field(
                name=f"🔧 機器人管理員 ({len(admins)})",
                value="\n".join(admin_mentions),
                inline=False
            )
        
        # 信任用戶
        trusted = permission_manager._custom_permissions['trusted_users']
        if trusted:
            trusted_mentions = []
            for user_id in list(trusted)[:10]:
                try:
                    user = await self.bot.fetch_user(user_id)
                    trusted_mentions.append(f"• {user.mention} (`{user_id}`)")
                except:
                    trusted_mentions.append(f"• 未知用戶 (`{user_id}`)")
            
            if len(trusted) > 10:
                trusted_mentions.append(f"• ... 及其他 {len(trusted) - 10} 人")
            
            embed.add_field(
                name=f"✅ 信任用戶 ({len(trusted)})",
                value="\n".join(trusted_mentions),
                inline=False
            )
        
        # 被禁用戶
        banned = permission_manager._custom_permissions['banned_users']
        if banned:
            banned_mentions = []
            for user_id in list(banned)[:10]:
                try:
                    user = await self.bot.fetch_user(user_id)
                    banned_mentions.append(f"• {user.mention} (`{user_id}`)")
                except:
                    banned_mentions.append(f"• 未知用戶 (`{user_id}`)")
            
            if len(banned) > 10:
                banned_mentions.append(f"• ... 及其他 {len(banned) - 10} 人")
            
            embed.add_field(
                name=f"❌ 被禁用戶 ({len(banned)})",
                value="\n".join(banned_mentions),
                inline=False
            )
        
        if not any([admins, trusted, banned]):
            embed.description = "目前沒有設定任何特殊權限用戶"
        
        await ctx.send(embed=embed)
        BotLogger.command_used("perm list", ctx.author.id, ctx.guild.id if ctx.guild else 0)
    
    @permission_group.command(name="cleanup")
    @admin_only()
    async def cleanup_rate_limits(self, ctx):
        """清理速率限制記錄"""
        old_count = len(permission_manager._rate_limits)
        permission_manager.cleanup_rate_limits()
        new_count = len(permission_manager._rate_limits)
        
        cleaned = old_count - new_count
        await ctx.send(f"🧹 清理完成，移除了 {cleaned} 個過期的速率限制記錄")
        BotLogger.command_used("perm cleanup", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"清理: {cleaned}")
    
    @commands.command(name="whoami")
    async def whoami(self, ctx):
        """查看自己的權限資訊"""
        await self.permission_info(ctx, ctx.author)


async def setup(bot):
    await bot.add_cog(PermissionsAdmin(bot))