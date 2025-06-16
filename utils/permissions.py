"""
統一的權限管理系統
支援 Discord 權限、自訂角色、速率限制等功能
"""
import asyncio
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Union
from functools import wraps

import discord
from discord.ext import commands

from utils.logger import BotLogger
from utils.config_manager import config


class PermissionLevel(Enum):
    """權限級別枚舉"""
    EVERYONE = 0        # 所有人
    MEMBER = 1          # 伺服器成員
    TRUSTED = 2         # 信任用戶（特定角色）
    MODERATOR = 3       # 版主
    ADMIN = 4           # 管理員
    OWNER = 5           # 機器人擁有者


class RateLimitBucket:
    """速率限制桶"""
    def __init__(self, rate: int, per: float):
        self.rate = rate  # 允許的請求數
        self.per = per    # 時間窗口（秒）
        self.tokens = rate  # 可用令牌數
        self.last_update = time.time()
    
    def can_consume(self, amount: int = 1) -> bool:
        """檢查是否可以消費指定數量的令牌"""
        now = time.time()
        # 補充令牌
        elapsed = now - self.last_update
        self.tokens = min(self.rate, self.tokens + elapsed * self.rate / self.per)
        self.last_update = now
        
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False
    
    def reset_time(self) -> float:
        """獲取下次可用的時間（秒）"""
        if self.tokens >= 1:
            return 0
        return (1 - self.tokens) * self.per / self.rate


class PermissionManager:
    """權限管理器"""
    
    def __init__(self):
        # 速率限制儲存 {user_id: {command_name: RateLimitBucket}}
        self._rate_limits: Dict[int, Dict[str, RateLimitBucket]] = {}
        
        # 自訂權限配置
        self._custom_permissions: Dict[str, Set[int]] = {
            'bot_admin': set(),      # 機器人管理員
            'trusted_users': set(),   # 信任用戶
            'banned_users': set(),    # 被禁用戶
        }
        
        # 載入配置
        self._load_permissions()
    
    def _load_permissions(self):
        """載入權限配置"""
        try:
            # 從配置中載入機器人管理員
            admin_ids = config.get('BOT_ADMIN_IDS', [])
            if isinstance(admin_ids, str):
                admin_ids = [int(x.strip()) for x in admin_ids.split(',') if x.strip()]
            elif isinstance(admin_ids, int):
                admin_ids = [admin_ids]
            
            self._custom_permissions['bot_admin'] = set(admin_ids)
            
            # 載入信任用戶
            trusted_ids = config.get('TRUSTED_USER_IDS', [])
            if isinstance(trusted_ids, str):
                trusted_ids = [int(x.strip()) for x in trusted_ids.split(',') if x.strip()]
            elif isinstance(trusted_ids, int):
                trusted_ids = [trusted_ids]
            
            self._custom_permissions['trusted_users'] = set(trusted_ids)
            
            BotLogger.info("PermissionManager", 
                          f"載入權限配置: 管理員 {len(self._custom_permissions['bot_admin'])} 人, "
                          f"信任用戶 {len(self._custom_permissions['trusted_users'])} 人")
                          
        except Exception as e:
            BotLogger.error("PermissionManager", "載入權限配置失敗", e)
    
    async def check_permission(self, ctx: commands.Context, level: PermissionLevel, 
                             required_discord_perms: List[str] = None) -> bool:
        """
        檢查用戶權限
        
        Args:
            ctx: Discord 指令上下文
            level: 所需權限級別
            required_discord_perms: 所需的 Discord 權限列表
            
        Returns:
            bool: 是否有權限
        """
        user = ctx.author
        
        # 檢查是否被禁用
        if user.id in self._custom_permissions['banned_users']:
            BotLogger.warning("PermissionCheck", f"被禁用戶嘗試執行指令: {user.id}")
            return False
        
        # 機器人擁有者擁有最高權限
        app_info = await ctx.bot.application_info()
        if user.id == app_info.owner.id:
            return True
        
        # 檢查自訂管理員
        if level >= PermissionLevel.ADMIN:
            if user.id in self._custom_permissions['bot_admin']:
                return True
            # 也可以是 Discord 伺服器擁有者
            if ctx.guild and user.id == ctx.guild.owner_id:
                return True
        
        # 檢查信任用戶
        if level >= PermissionLevel.TRUSTED:
            if user.id in self._custom_permissions['trusted_users']:
                return True
        
        # 檢查 Discord 權限
        if required_discord_perms and ctx.guild:
            member = ctx.guild.get_member(user.id)
            if member:
                for perm_name in required_discord_perms:
                    if not getattr(member.guild_permissions, perm_name, False):
                        return False
        
        # 基於權限級別的檢查
        if level == PermissionLevel.EVERYONE:
            return True
        elif level == PermissionLevel.MEMBER:
            return ctx.guild is not None
        elif level == PermissionLevel.MODERATOR:
            if ctx.guild:
                member = ctx.guild.get_member(user.id)
                return member and (
                    member.guild_permissions.manage_messages or
                    member.guild_permissions.kick_members or
                    member.guild_permissions.ban_members
                )
        elif level == PermissionLevel.ADMIN:
            if ctx.guild:
                member = ctx.guild.get_member(user.id)
                return member and member.guild_permissions.administrator
        
        return False
    
    async def check_rate_limit(self, user_id: int, command_name: str, 
                             rate: int = 1, per: float = 1.0) -> tuple[bool, float]:
        """
        檢查速率限制
        
        Args:
            user_id: 用戶 ID
            command_name: 指令名稱
            rate: 允許的請求數
            per: 時間窗口（秒）
            
        Returns:
            tuple[bool, float]: (是否允許, 下次可用時間)
        """
        # 機器人管理員不受速率限制
        if user_id in self._custom_permissions['bot_admin']:
            return True, 0.0
        
        if user_id not in self._rate_limits:
            self._rate_limits[user_id] = {}
        
        if command_name not in self._rate_limits[user_id]:
            self._rate_limits[user_id][command_name] = RateLimitBucket(rate, per)
        
        bucket = self._rate_limits[user_id][command_name]
        can_proceed = bucket.can_consume()
        reset_time = bucket.reset_time()
        
        if not can_proceed:
            BotLogger.info("RateLimit", 
                          f"用戶 {user_id} 在指令 {command_name} 上觸發速率限制")
        
        return can_proceed, reset_time
    
    def add_trusted_user(self, user_id: int):
        """添加信任用戶"""
        self._custom_permissions['trusted_users'].add(user_id)
        BotLogger.info("PermissionManager", f"添加信任用戶: {user_id}")
    
    def remove_trusted_user(self, user_id: int):
        """移除信任用戶"""
        self._custom_permissions['trusted_users'].discard(user_id)
        BotLogger.info("PermissionManager", f"移除信任用戶: {user_id}")
    
    def ban_user(self, user_id: int):
        """禁用用戶"""
        self._custom_permissions['banned_users'].add(user_id)
        BotLogger.warning("PermissionManager", f"禁用用戶: {user_id}")
    
    def unban_user(self, user_id: int):
        """解禁用戶"""
        self._custom_permissions['banned_users'].discard(user_id)
        BotLogger.info("PermissionManager", f"解禁用戶: {user_id}")
    
    def get_user_level(self, user_id: int, guild: discord.Guild = None) -> PermissionLevel:
        """獲取用戶權限級別"""
        if user_id in self._custom_permissions['banned_users']:
            return PermissionLevel.EVERYONE  # 實際會被阻擋
        
        if user_id in self._custom_permissions['bot_admin']:
            return PermissionLevel.ADMIN
        
        if user_id in self._custom_permissions['trusted_users']:
            return PermissionLevel.TRUSTED
        
        if guild:
            member = guild.get_member(user_id)
            if member:
                if member.guild_permissions.administrator:
                    return PermissionLevel.ADMIN
                elif (member.guild_permissions.manage_messages or 
                      member.guild_permissions.kick_members):
                    return PermissionLevel.MODERATOR
                else:
                    return PermissionLevel.MEMBER
        
        return PermissionLevel.EVERYONE
    
    def cleanup_rate_limits(self):
        """清理過期的速率限制記錄"""
        current_time = time.time()
        expired_users = []
        
        for user_id, commands in self._rate_limits.items():
            expired_commands = []
            for command_name, bucket in commands.items():
                # 如果超過5分鐘沒有活動，清理記錄
                if current_time - bucket.last_update > 300:
                    expired_commands.append(command_name)
            
            for command_name in expired_commands:
                del commands[command_name]
            
            if not commands:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            del self._rate_limits[user_id]
        
        if expired_users:
            BotLogger.debug("PermissionManager", f"清理了 {len(expired_users)} 個過期的速率限制記錄")


# 全域權限管理器實例
permission_manager = PermissionManager()


# 權限檢查裝飾器
def require_permission(level: PermissionLevel, 
                      discord_perms: List[str] = None,
                      rate_limit: tuple = None):
    """
    權限檢查裝飾器
    
    Args:
        level: 所需權限級別
        discord_perms: 所需 Discord 權限列表
        rate_limit: 速率限制 (rate, per) 元組
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 找到 Context 參數
            ctx = None
            for arg in args:
                if isinstance(arg, commands.Context):
                    ctx = arg
                    break
            
            if not ctx:
                raise ValueError("找不到 commands.Context 參數")
            
            # 檢查權限
            has_permission = await permission_manager.check_permission(
                ctx, level, discord_perms
            )
            
            if not has_permission:
                await ctx.send("❌ 您沒有執行此指令的權限")
                BotLogger.warning("PermissionDenied", 
                                f"用戶 {ctx.author.id} 嘗試執行需要 {level.name} 權限的指令")
                return
            
            # 檢查速率限制
            if rate_limit:
                rate, per = rate_limit
                can_proceed, reset_time = await permission_manager.check_rate_limit(
                    ctx.author.id, func.__name__, rate, per
                )
                
                if not can_proceed:
                    minutes = int(reset_time // 60)
                    seconds = int(reset_time % 60)
                    time_str = f"{minutes}分{seconds}秒" if minutes > 0 else f"{seconds}秒"
                    await ctx.send(f"⏳ 指令冷卻中，請等待 {time_str}")
                    return
            
            # 執行原函數
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def guild_only():
    """僅伺服器可用裝飾器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            ctx = None
            for arg in args:
                if isinstance(arg, commands.Context):
                    ctx = arg
                    break
            
            if not ctx or not ctx.guild:
                await ctx.send("❌ 此指令僅能在伺服器中使用")
                return
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# 常用權限組合的便捷裝飾器
def admin_only(rate_limit: tuple = None):
    """僅管理員可用"""
    return require_permission(PermissionLevel.ADMIN, rate_limit=rate_limit)


def moderator_only(rate_limit: tuple = None):
    """僅版主可用"""
    return require_permission(PermissionLevel.MODERATOR, rate_limit=rate_limit)


def trusted_only(rate_limit: tuple = None):
    """僅信任用戶可用"""
    return require_permission(PermissionLevel.TRUSTED, rate_limit=rate_limit)


def with_rate_limit(rate: int, per: float):
    """僅速率限制"""
    return require_permission(PermissionLevel.EVERYONE, rate_limit=(rate, per))