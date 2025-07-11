"""
統一 UI 組件庫
基於 Eat 模組的成功實踐，提供可重用的 Discord UI 組件

作者: Claude Code Assistant
日期: 2025-07-07
版本: v1.0
"""

from typing import Optional, Dict, List, Any, Union
import discord
from discord.ext import commands
from utils.logger import BotLogger


class BaseView(discord.ui.View):
    """統一的 View 基類 - 提供標準化的互動檢查和逾時處理
    
    特色：
    - 統一的用戶權限檢查
    - 優雅的逾時處理
    - 標準化的訊息管理
    """
    
    def __init__(self, user: discord.User, timeout: int = 60):
        """初始化 BaseView
        
        Args:
            user: 有權限操作此 View 的用戶
            timeout: 逾時時間（秒），預設 60 秒
        """
        super().__init__(timeout=timeout)
        self.user = user
        self.message: Optional[discord.Message] = None
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """統一的互動檢查邏輯
        
        只允許指定用戶操作 View 組件
        
        Args:
            interaction: Discord 互動事件
            
        Returns:
            bool: 是否允許此互動
        """
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ 只能由原始使用者操作", 
                ephemeral=True
            )
            return False
        return True
    
    async def on_timeout(self):
        """統一的逾時處理邏輯
        
        當 View 逾時時，移除互動組件但保留訊息內容
        """
        if self.message:
            try:
                # 只移除 view，保留原本的 embed 內容
                await self.message.edit(view=None)
            except (discord.NotFound, discord.HTTPException):
                # 訊息已被刪除或其他錯誤，忽略
                pass


class EmbedBuilder:
    """統一的 Embed 建構器 - 提供標準化的 Discord Embed 創建
    
    特色：
    - 一致的顏色主題
    - 標準化的格式
    - 常用的 Embed 模板
    """
    
    # 標準顏色主題
    class Colors:
        SUCCESS = discord.Color.green()
        INFO = discord.Color.blue()
        WARNING = discord.Color.orange()
        ERROR = discord.Color.red()
        PRIMARY = discord.Color.blurple()
        SECONDARY = discord.Color.greyple()
    
    @staticmethod
    def success(title: str, description: str = None, **kwargs) -> discord.Embed:
        """創建成功狀態的 Embed
        
        Args:
            title: 標題
            description: 描述（可選）
            **kwargs: 其他 Embed 參數
            
        Returns:
            discord.Embed: 成功狀態的 Embed
        """
        embed = discord.Embed(
            title=f"✅ {title}",
            description=description,
            color=EmbedBuilder.Colors.SUCCESS,
            **kwargs
        )
        return embed
    
    @staticmethod
    def error(title: str, description: str = None, **kwargs) -> discord.Embed:
        """創建錯誤狀態的 Embed
        
        Args:
            title: 標題
            description: 描述（可選）
            **kwargs: 其他 Embed 參數
            
        Returns:
            discord.Embed: 錯誤狀態的 Embed
        """
        embed = discord.Embed(
            title=f"❌ {title}",
            description=description,
            color=EmbedBuilder.Colors.ERROR,
            **kwargs
        )
        return embed
    
    @staticmethod
    def info(title: str, description: str = None, **kwargs) -> discord.Embed:
        """創建資訊狀態的 Embed
        
        Args:
            title: 標題
            description: 描述（可選）
            **kwargs: 其他 Embed 參數
            
        Returns:
            discord.Embed: 資訊狀態的 Embed
        """
        embed = discord.Embed(
            title=f"ℹ️ {title}",
            description=description,
            color=EmbedBuilder.Colors.INFO,
            **kwargs
        )
        return embed
    
    @staticmethod
    def warning(title: str, description: str = None, **kwargs) -> discord.Embed:
        """創建警告狀態的 Embed
        
        Args:
            title: 標題
            description: 描述（可選）
            **kwargs: 其他 Embed 參數
            
        Returns:
            discord.Embed: 警告狀態的 Embed
        """
        embed = discord.Embed(
            title=f"⚠️ {title}",
            description=description,
            color=EmbedBuilder.Colors.WARNING,
            **kwargs
        )
        return embed
    
    @staticmethod
    def list_display(title: str, items: List[str], 
                    color: discord.Color = None, **kwargs) -> discord.Embed:
        """創建列表顯示的 Embed
        
        Args:
            title: 標題
            items: 項目列表
            color: 顏色（可選）
            **kwargs: 其他 Embed 參數
            
        Returns:
            discord.Embed: 列表顯示的 Embed
        """
        if color is None:
            color = EmbedBuilder.Colors.INFO
            
        description = "\n".join(f"• {item}" for item in items) if items else "（無項目）"
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            **kwargs
        )
        return embed
    
    @staticmethod
    def selection_prompt(title: str, description: str = None, 
                        **kwargs) -> discord.Embed:
        """創建選擇提示的 Embed
        
        Args:
            title: 標題
            description: 描述（可選）
            **kwargs: 其他 Embed 參數
            
        Returns:
            discord.Embed: 選擇提示的 Embed
        """
        embed = discord.Embed(
            title=title,
            description=description or "請點選下方按鈕進行選擇。",
            color=EmbedBuilder.Colors.PRIMARY,
            **kwargs
        )
        return embed


class ErrorHandler:
    """統一的錯誤處理器 - 提供標準化的錯誤處理和日誌記錄
    
    特色：
    - 一致的錯誤訊息格式
    - 自動日誌記錄
    - 常見錯誤的標準處理
    """
    
    @staticmethod
    async def handle_missing_argument(
        ctx: Union[commands.Context, discord.Interaction], 
        command_name: str, 
        example: str,
        is_slash: bool = False
    ):
        """處理缺少參數的錯誤
        
        Args:
            ctx: 指令上下文或互動事件
            command_name: 指令名稱
            example: 使用範例
            is_slash: 是否為斜線指令
        """
        prefix = "/" if is_slash else "?"
        message = f"❌ 請提供必要參數，例如：`{prefix}{command_name} {example}`"
        
        if is_slash and hasattr(ctx, 'response'):
            await ctx.response.send_message(message, ephemeral=True)
        else:
            await ctx.send(message)
    
    @staticmethod
    async def handle_permission_error(
        ctx: Union[commands.Context, discord.Interaction],
        required_permission: str = None,
        is_slash: bool = False
    ):
        """處理權限不足錯誤
        
        Args:
            ctx: 指令上下文或互動事件
            required_permission: 需要的權限名稱（可選）
            is_slash: 是否為斜線指令
        """
        message = "❌ 您沒有執行此指令的權限"
        if required_permission:
            message += f"（需要：{required_permission}）"
        
        if is_slash and hasattr(ctx, 'response'):
            await ctx.response.send_message(message, ephemeral=True)
        else:
            await ctx.send(message)
    
    @staticmethod
    async def handle_generic_error(
        ctx: Union[commands.Context, discord.Interaction],
        error_message: str = "系統發生錯誤，請稍後再試",
        is_slash: bool = False
    ):
        """處理一般性錯誤
        
        Args:
            ctx: 指令上下文或互動事件
            error_message: 錯誤訊息
            is_slash: 是否為斜線指令
        """
        message = f"❌ {error_message}"
        
        if is_slash and hasattr(ctx, 'response'):
            if ctx.response.is_done():
                await ctx.followup.send(message, ephemeral=True)
            else:
                await ctx.response.send_message(message, ephemeral=True)
        else:
            await ctx.send(message)
    
    @staticmethod
    def log_command_error(module_name: str, command_name: str, error: Exception):
        """記錄指令錯誤到日誌
        
        Args:
            module_name: 模組名稱
            command_name: 指令名稱
            error: 錯誤物件
        """
        BotLogger.error(module_name, f"{command_name} 指令錯誤: {error}", error)
    
    @staticmethod
    async def handle_command_error(
        ctx: Union[commands.Context, discord.Interaction],
        error: Exception,
        module_name: str,
        command_name: str,
        is_slash: bool = False
    ):
        """統一處理指令錯誤
        
        Args:
            ctx: 指令上下文或互動事件
            error: 錯誤物件
            module_name: 模組名稱
            command_name: 指令名稱
            is_slash: 是否為斜線指令
        """
        # 記錄錯誤
        ErrorHandler.log_command_error(module_name, command_name, error)
        
        # 根據錯誤類型提供適當回應
        if isinstance(error, commands.MissingRequiredArgument):
            await ErrorHandler.handle_missing_argument(
                ctx, command_name, "參數", is_slash
            )
        elif isinstance(error, commands.MissingPermissions):
            await ErrorHandler.handle_permission_error(ctx, None, is_slash)
        else:
            await ErrorHandler.handle_generic_error(ctx, is_slash=is_slash)


class PaginationView(BaseView):
    """分頁 View 組件 - 提供標準化的分頁功能
    
    特色：
    - 標準化的分頁按鈕
    - 自動頁數計算
    - 支援自訂分頁內容
    """
    
    def __init__(self, user: discord.User, pages: List[discord.Embed], 
                 timeout: int = 300):
        """初始化分頁 View
        
        Args:
            user: 有權限操作的用戶
            pages: 頁面列表
            timeout: 逾時時間（秒），預設 5 分鐘
        """
        super().__init__(user, timeout)
        self.pages = pages
        self.current_page = 0
        self.max_pages = len(pages)
        
        # 根據頁數決定是否顯示按鈕
        if self.max_pages > 1:
            self.update_buttons()
    
    def update_buttons(self):
        """更新按鈕狀態"""
        # 清除現有按鈕
        self.clear_items()
        
        if self.max_pages <= 1:
            return
        
        # 上一頁按鈕
        prev_button = discord.ui.Button(
            label="⬅️",
            style=discord.ButtonStyle.secondary,
            disabled=self.current_page == 0
        )
        prev_button.callback = self.prev_page
        self.add_item(prev_button)
        
        # 頁數顯示
        page_button = discord.ui.Button(
            label=f"{self.current_page + 1}/{self.max_pages}",
            style=discord.ButtonStyle.primary,
            disabled=True
        )
        self.add_item(page_button)
        
        # 下一頁按鈕
        next_button = discord.ui.Button(
            label="➡️",
            style=discord.ButtonStyle.secondary,
            disabled=self.current_page == self.max_pages - 1
        )
        next_button.callback = self.next_page
        self.add_item(next_button)
    
    async def prev_page(self, interaction: discord.Interaction):
        """上一頁"""
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(
                embed=self.pages[self.current_page], 
                view=self
            )
    
    async def next_page(self, interaction: discord.Interaction):
        """下一頁"""
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(
                embed=self.pages[self.current_page], 
                view=self
            )
    
    def get_current_embed(self) -> discord.Embed:
        """獲取當前頁面的 Embed"""
        return self.pages[self.current_page] if self.pages else discord.Embed()


# 便利函數
def create_confirmation_view(user: discord.User, 
                           on_confirm: callable = None,
                           on_cancel: callable = None,
                           timeout: int = 60) -> BaseView:
    """創建確認對話框 View
    
    Args:
        user: 有權限操作的用戶
        on_confirm: 確認時的回調函數
        on_cancel: 取消時的回調函數
        timeout: 逾時時間（秒）
        
    Returns:
        BaseView: 確認對話框 View
    """
    view = BaseView(user, timeout)
    
    # 確認按鈕
    confirm_button = discord.ui.Button(
        label="✅ 確認",
        style=discord.ButtonStyle.success
    )
    
    async def confirm_callback(interaction: discord.Interaction):
        if on_confirm:
            await on_confirm(interaction)
        else:
            await interaction.response.edit_message(
                content="✅ 已確認", 
                view=None
            )
    
    confirm_button.callback = confirm_callback
    view.add_item(confirm_button)
    
    # 取消按鈕
    cancel_button = discord.ui.Button(
        label="❌ 取消",
        style=discord.ButtonStyle.danger
    )
    
    async def cancel_callback(interaction: discord.Interaction):
        if on_cancel:
            await on_cancel(interaction)
        else:
            await interaction.response.edit_message(
                content="❌ 已取消", 
                view=None
            )
    
    cancel_button.callback = cancel_callback
    view.add_item(cancel_button)
    
    return view