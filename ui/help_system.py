import discord
from typing import Dict, List
from utils.logger import BotLogger


class HelpPaginationView(discord.ui.View):
    """幫助系統分頁介面"""
    
    def __init__(self, categories: Dict[str, List[Dict[str, str]]], bot_instance, timeout=300):
        super().__init__(timeout=timeout)
        self.categories = categories
        self.bot = bot_instance
        self.current_page = 0
        self.category_names = list(categories.keys())
        self.max_pages = len(self.category_names)
        
        # 更新按鈕狀態
        self.update_buttons()
    
    def update_buttons(self):
        """更新按鈕的啟用/禁用狀態"""
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= self.max_pages - 1
        
        # 更新頁面顯示按鈕的標籤
        self.page_button.label = f"{self.current_page + 1}/{self.max_pages}"
    
    def create_embed(self) -> discord.Embed:
        """創建當前頁面的embed"""
        if not self.category_names or self.current_page >= len(self.category_names):
            return self.create_overview_embed()
        
        category_name = self.category_names[self.current_page]
        commands = self.categories[category_name]
        
        # 轉換cog名稱為中文顯示名稱
        display_names = {
            'Reply': '🎭 回覆系統',
            'Party': '👥 分隊系統', 
            'Eat': '🍽️ 用餐推薦',
            'Draw': '🎲 抽獎系統',
            'Clock': '⏰ 打卡系統',
            'Clear': '🧹 清理工具',
            'Emojitool': '😊 表情工具',
            'Repo': '🎯 準心庫',
            'Tinder': '💕 配對系統',
            'TwitterMonitor': '🐦 Twitter監控',
            '系統指令': '⚙️ 系統指令'
        }
        
        display_name = display_names.get(category_name, f"📦 {category_name}")
        
        embed = discord.Embed(
            title=f"📚 {display_name}",
            description=f"第 {self.current_page + 1} 頁，共 {self.max_pages} 頁",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        # 添加指令列表
        if commands:
            commands_text = []
            for cmd in commands:
                commands_text.append(f"`/{cmd['name']}` - {cmd['description']}")
            
            embed.add_field(
                name="📋 可用指令",
                value="\n".join(commands_text) if commands_text else "此分類暫無可用指令",
                inline=False
            )
        
        # 添加特殊說明
        special_info = self.get_category_special_info(category_name)
        if special_info:
            embed.add_field(
                name="💡 特殊說明",
                value=special_info,
                inline=False
            )
        
        embed.set_footer(
            text="Niibot • 使用導覽按鈕瀏覽不同功能分類",
            icon_url=self.bot.user.display_avatar.url if self.bot.user else None
        )
        
        return embed
    
    def get_category_special_info(self, category_name: str) -> str:
        """獲取分類的特殊說明信息"""
        special_info = {
            'Reply': "• copycat指令可複製用戶頭像、橫幅和主題顏色\n• 支援切換伺服器專用設定和全域設定\n• 別名：`cc`、`複製`、`ditto`",
            'Party': "• 快速建立分隊並管理成員\n• 支援語音頻道連動功能",
            'Eat': "• 隨機推薦餐廳或食物\n• 可按分類篩選（如日式、中式等）",
            'Clock': "• 記錄每日打卡時間\n• 統計個人和團體數據",
            'Draw': "• 支援多種抽獎模式\n• 可設定獎品和中獎機率",
            'Clear': "• 批量刪除訊息功能\n• 支援按用戶、時間範圍篩選"
        }
        return special_info.get(category_name, "")
    
    def create_overview_embed(self) -> discord.Embed:
        """創建總覽頁面"""
        embed = discord.Embed(
            title="📚 Niibot 指令總覽",
            description="選擇下方按鈕瀏覽各功能分類，或使用導覽按鈕切換頁面",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        
        # 統計信息
        total_commands = sum(len(cmds) for cmds in self.categories.values())
        embed.add_field(
            name="📊 統計信息",
            value=f"• 功能分類：{len(self.categories)} 個\n• 指令總數：{total_commands} 個",
            inline=False
        )
        
        # 快速導覽
        category_list = []
        for i, category_name in enumerate(self.category_names):
            display_names = {
                'Reply': '🎭 回覆系統',
                'Party': '👥 分隊系統', 
                'Eat': '🍽️ 用餐推薦',
                'Draw': '🎲 抽獎系統',
                'Clock': '⏰ 打卡系統',
                'Clear': '🧹 清理工具',
                'Emojitool': '😊 表情工具',
                'Repo': '🎯 準心庫',
                'Tinder': '💕 配對系統',
                'TwitterMonitor': '🐦 Twitter監控',
                '系統指令': '⚙️ 系統指令'
            }
            display_name = display_names.get(category_name, f"📦 {category_name}")
            cmd_count = len(self.categories[category_name])
            category_list.append(f"{i+1}. {display_name} ({cmd_count} 個指令)")
        
        embed.add_field(
            name="🗂️ 功能分類",
            value="\n".join(category_list),
            inline=False
        )
        
        embed.add_field(
            name="💡 使用提示",
            value="• 斜線指令以 `/` 開頭\n• 傳統指令以 `?` 開頭\n• 使用 `?help` 查看傳統指令\n• 點擊下方按鈕快速跳轉到特定分類",
            inline=False
        )
        
        embed.set_footer(
            text="Niibot • 點擊導覽按鈕開始探索",
            icon_url=self.bot.user.display_avatar.url if self.bot.user else None
        )
        
        return embed
    
    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.secondary, disabled=True)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """上一頁按鈕"""
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="1/1", style=discord.ButtonStyle.primary, disabled=True)
    async def page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """頁面顯示按鈕（點擊返回總覽）"""
        embed = self.create_overview_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """下一頁按鈕"""
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            self.update_buttons()
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.select(
        placeholder="🔍 快速跳轉到功能分類...",
        options=[
            discord.SelectOption(label="總覽頁面", value="overview", emoji="📚"),
        ]
    )
    async def category_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """分類選擇下拉選單"""
        selected_value = select.values[0]
        
        if selected_value == "overview":
            embed = self.create_overview_embed()
        else:
            # 找到對應的分類索引
            try:
                category_index = int(selected_value)
                if 0 <= category_index < len(self.category_names):
                    self.current_page = category_index
                    self.update_buttons()
                    embed = self.create_embed()
                else:
                    embed = self.create_overview_embed()
            except (ValueError, IndexError):
                embed = self.create_overview_embed()
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    def update_select_options(self):
        """更新下拉選單選項"""
        options = [discord.SelectOption(label="📚 總覽頁面", value="overview", emoji="🏠")]
        
        display_names = {
            'Reply': '🎭 回覆系統',
            'Party': '👥 分隊系統', 
            'Eat': '🍽️ 用餐推薦',
            'Draw': '🎲 抽獎系統',
            'Clock': '⏰ 打卡系統',
            'Clear': '🧹 清理工具',
            'Emojitool': '😊 表情工具',
            'Repo': '🎯 準心庫',
            'Tinder': '💕 配對系統',
            'TwitterMonitor': '🐦 Twitter監控',
            '系統指令': '⚙️ 系統指令'
        }
        
        for i, category_name in enumerate(self.category_names):
            if len(options) >= 25:  # Discord限制最多25個選項
                break
            display_name = display_names.get(category_name, category_name)
            cmd_count = len(self.categories[category_name])
            options.append(
                discord.SelectOption(
                    label=f"{display_name} ({cmd_count}個)",
                    value=str(i),
                    description=f"查看{display_name}的所有指令"
                )
            )
        
        self.category_select.options = options
    
    async def on_timeout(self):
        """View逾時處理"""
        for item in self.children:
            item.disabled = True
        
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except:
            pass