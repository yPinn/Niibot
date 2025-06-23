"""
準心代碼庫 - 實用的預覽和選擇功能
保留核心的翻頁預覽，移除過度複雜的分類系統
"""

import discord
from discord.ext import commands
from utils.logger import BotLogger
from utils import util


class CrosshairView(discord.ui.View):
    """準心瀏覽界面 - 支援遊戲分類和圖片預覽"""
    
    def __init__(self, all_crosshairs: list, user_id: int = None):
        super().__init__(timeout=300)  # 5分鐘超時
        self.all_crosshairs = all_crosshairs
        self.user_id = user_id
        self.current_page = 0
        
        # 建立遊戲分類
        self.games_dict = {}
        for ch in all_crosshairs:
            game = ch.get('game', '未知遊戲')
            if game not in self.games_dict:
                self.games_dict[game] = []
            self.games_dict[game].append(ch)
        
        # 當前選中的遊戲和準心列表
        self.selected_game = None
        self.current_crosshairs = []
        
        # 如果只有一個遊戲，自動選中
        if len(self.games_dict) == 1:
            self.selected_game = list(self.games_dict.keys())[0]
            self.current_crosshairs = self.games_dict[self.selected_game]
        else:
            # 多個遊戲時顯示所有準心
            self.current_crosshairs = all_crosshairs
        
        self.update_buttons()
        self.setup_game_selector()
    
    def _get_game_emoji(self, game: str) -> str:
        """根據遊戲名稱返回對應的表情符號"""
        game_lower = game.lower()
        if "valorant" in game_lower:
            return "🎯"
        elif "cs2" in game_lower or "counter-strike" in game_lower:
            return "🔫"
        elif "apex" in game_lower:
            return "⚡"
        elif "overwatch" in game_lower:
            return "🔶"
        elif "call of duty" in game_lower or "cod" in game_lower:
            return "💀"
        elif "rainbow" in game_lower or "siege" in game_lower:
            return "🌈"
        elif "pubg" in game_lower:
            return "🏗️"
        else:
            return "🎮"
    
    def setup_game_selector(self):
        """設置遊戲選擇下拉選單"""
        # 清除現有的選單
        for item in self.children[:]:
            if isinstance(item, discord.ui.Select):
                self.remove_item(item)
        
        # 如果只有一個遊戲或沒有遊戲，不顯示選單
        if len(self.games_dict) <= 1:
            return
        
        # 建立選項
        options = []
        
        # 添加 "全部" 選項
        options.append(discord.SelectOption(
            label="全部遊戲",
            value="all",
            description=f"顯示所有 {len(self.all_crosshairs)} 個準心",
            emoji="🎮",
            default=(self.selected_game is None)
        ))
        
        # 添加各遊戲選項
        for game, crosshairs in self.games_dict.items():
            emoji = self._get_game_emoji(game)
            options.append(discord.SelectOption(
                label=game,
                value=game,
                description=f"{len(crosshairs)} 個準心",
                emoji=emoji,
                default=(game == self.selected_game)
            ))
        
        # 創建選單
        game_selector = discord.ui.Select(
            placeholder="選擇遊戲分類",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )
        game_selector.callback = self.on_game_select
        self.add_item(game_selector)
    
    async def on_game_select(self, interaction: discord.Interaction):
        """處理遊戲選擇"""
        if not self.check_permission(interaction):
            await interaction.response.send_message("❌ 只有指令使用者可以操作", ephemeral=True)
            return
        
        selected_value = interaction.data['values'][0]
        
        if selected_value == "all":
            self.selected_game = None
            self.current_crosshairs = self.all_crosshairs
        else:
            self.selected_game = selected_value
            self.current_crosshairs = self.games_dict[selected_value]
        
        self.current_page = 0  # 重置到第一頁
        self.setup_game_selector()  # 更新選單狀態
        self.update_buttons()
        
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    def update_buttons(self):
        """更新按鈕狀態"""
        total_pages = len(self.current_crosshairs)
        
        self.prev_button.disabled = (self.current_page <= 0)
        self.next_button.disabled = (self.current_page >= total_pages - 1)
        
        # 更新頁數顯示
        if total_pages > 0:
            self.page_button.label = f"{self.current_page + 1}/{total_pages}"
        else:
            self.page_button.label = "0/0"
    
    def create_embed(self) -> discord.Embed:
        """創建當前頁面的 embed"""
        if not self.current_crosshairs:
            return discord.Embed(
                title="📦 準心代碼庫",
                description="沒有找到準心資料",
                color=discord.Color.orange()
            )
        
        if self.current_page < 0 or self.current_page >= len(self.current_crosshairs):
            return discord.Embed(
                title="❌ 頁面錯誤",
                description="無法顯示此頁面",
                color=discord.Color.red()
            )
        
        crosshair = self.current_crosshairs[self.current_page]
        
        # 遊戲圖示
        game = crosshair.get('game', '未知遊戲')
        emoji = self._get_game_emoji(game)
        
        # 建立標題
        title = f"{emoji} {crosshair.get('tag', '無標籤')}"
        
        # 建立描述
        description_parts = [
            f"**🎮 遊戲：** {game}",
            f"**🆔 ID：** `{crosshair.get('id', 'N/A')}`"
        ]
        
        if self.selected_game:
            description_parts.append(f"**📂 分類：** {self.selected_game}")
        
        embed = discord.Embed(
            title=title,
            description="\n".join(description_parts),
            color=discord.Color.blue()
        )
        
        # 準心代碼顯示 (改為始終顯示完整代碼)
        code = crosshair.get('code', '無代碼')
        
        # Discord embed field 最大長度是 1024，code block 佔用 6 個字符 (```)
        max_code_length = 1018
        
        if len(code) > max_code_length:
            # 如果代碼太長，分成多個field顯示
            embed.add_field(
                name="📋 準心代碼 (第1部分)",
                value=f"```\n{code[:max_code_length]}\n```",
                inline=False
            )
            remaining_code = code[max_code_length:]
            if len(remaining_code) > max_code_length:
                embed.add_field(
                    name="📋 準心代碼 (第2部分)",
                    value=f"```\n{remaining_code[:max_code_length]}\n```",
                    inline=False
                )
                if len(remaining_code) > max_code_length:
                    embed.add_field(
                        name="📋 準心代碼 (剩餘部分)",
                        value=f"```\n{remaining_code[max_code_length:]}\n```",
                        inline=False
                    )
            else:
                embed.add_field(
                    name="📋 準心代碼 (第2部分)",
                    value=f"```\n{remaining_code}\n```",
                    inline=False
                )
        else:
            embed.add_field(
                name="📋 準心代碼",
                value=f"```\n{code}\n```",
                inline=False
            )
        
        # 設定圖片預覽
        image_url = crosshair.get('image_url')
        if image_url and image_url.strip():
            embed.set_image(url=image_url)
            embed.add_field(
                name="🖼️ 預覽圖片",
                value="✅ 準心截圖如上所示",
                inline=True
            )
        else:
            embed.add_field(
                name="🖼️ 預覽圖片",
                value="❌ 無預覽圖片",
                inline=True
            )
        
        # 頁面資訊和使用提示
        if self.selected_game:
            footer_text = f"📄 第 {self.current_page + 1} 頁，共 {len(self.current_crosshairs)} 個 {self.selected_game} 準心 • 💡 直接複製上方代碼使用"
        else:
            footer_text = f"📄 第 {self.current_page + 1} 頁，共 {len(self.current_crosshairs)} 個準心 • 💡 直接複製上方代碼使用"
        
        embed.set_footer(text=footer_text)
        
        return embed
    
    def check_permission(self, interaction: discord.Interaction) -> bool:
        """檢查用戶權限"""
        if self.user_id and interaction.user.id != self.user_id:
            return False
        return True
    
    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.primary, row=1)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.check_permission(interaction):
            await interaction.response.send_message("❌ 只有指令使用者可以操作", ephemeral=True)
            return
        
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("❌ 已經是第一個了", ephemeral=True)
    
    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True, row=1)
    async def page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 顯示當前準心資訊
        if self.current_crosshairs and 0 <= self.current_page < len(self.current_crosshairs):
            current = self.current_crosshairs[self.current_page]
            category_info = f" (分類: {self.selected_game})" if self.selected_game else ""
            await interaction.response.send_message(
                f"📍 當前: {current.get('game', '未知')} - {current.get('tag', '無標籤')}{category_info}", 
                ephemeral=True
            )
        else:
            await interaction.response.send_message("ℹ️ 無資料", ephemeral=True)
    
    @discord.ui.button(label="➡️", style=discord.ButtonStyle.primary, row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.check_permission(interaction):
            await interaction.response.send_message("❌ 只有指令使用者可以操作", ephemeral=True)
            return
        
        if self.current_page < len(self.current_crosshairs) - 1:
            self.current_page += 1
            self.update_buttons()
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("❌ 已經是最後一個了", ephemeral=True)
    
    
    async def on_timeout(self):
        """處理超時"""
        for item in self.children:
            item.disabled = True


class Repo(commands.Cog):
    """準心代碼庫功能 - 實用預覽版"""
    
    def __init__(self, bot):
        self.bot = bot
        self.data_file = "repo.json"
    
    async def _load_crosshairs(self) -> list:
        """載入準心資料"""
        try:
            file_path = util.get_data_file_path(self.data_file)
            data = await util.read_json(file_path)
            if isinstance(data, dict):
                return data.get('crosshairs', [])
            return data or []
        except Exception as e:
            BotLogger.error("Repo", f"載入準心資料失敗: {e}")
            return []
    
    async def _save_crosshairs(self, crosshairs: list):
        """儲存準心資料"""
        try:
            file_path = util.get_data_file_path(self.data_file)
            await util.write_json(file_path, {"crosshairs": crosshairs})
            BotLogger.info("Repo", f"成功儲存 {len(crosshairs)} 個準心資料")
        except Exception as e:
            BotLogger.error("Repo", f"儲存準心資料失敗: {e}")
            raise

    def _generate_id(self, game: str, crosshairs: list) -> str:
        """為指定遊戲生成新的ID"""
        # 先檢查現有準心是否已有此遊戲的前綴
        existing_prefix = None
        for ch in crosshairs:
            if ch.get('game', '').lower() == game.lower():
                ch_id = str(ch.get('id', ''))
                if '/' in ch_id:
                    existing_prefix = ch_id.split('/')[0]
                    break
        
        # 如果找到現有前綴就使用，否則生成新的
        if existing_prefix:
            prefix = existing_prefix
        else:
            # 生成新前綴（取前3個字母）
            prefix = ''.join(c.lower() for c in game if c.isalpha())[:3]
        
        # 找出該遊戲現有的最大ID號碼
        max_num = 0
        for ch in crosshairs:
            ch_id = str(ch.get('id', ''))
            if ch_id.startswith(f"{prefix}/"):
                try:
                    num = int(ch_id.split('/')[-1])
                    max_num = max(max_num, num)
                except (ValueError, IndexError):
                    continue
        
        return f"{prefix}/{max_num + 1}"

    @commands.command(name="repo", aliases=["準心"], help="瀏覽準心代碼庫")
    async def repo_browse(self, ctx, *, search_term: str = None):
        """瀏覽準心代碼庫 - 支援搜尋和翻頁預覽"""
        try:
            crosshairs = await self._load_crosshairs()
            
            if not crosshairs:
                embed = discord.Embed(
                    title="📦 準心代碼庫", 
                    description="目前沒有準心資料\n使用 `?repo_add` 來新增準心",
                    color=discord.Color.orange()
                )
                await ctx.send(embed=embed)
                return
            
            # 搜尋過濾
            if search_term:
                search_term = search_term.lower()
                filtered = [
                    ch for ch in crosshairs 
                    if (search_term in ch.get('game', '').lower() or 
                        search_term in ch.get('tag', '').lower() or
                        search_term in str(ch.get('id', '')).lower())
                ]
                
                if not filtered:
                    embed = discord.Embed(
                        title="🔍 搜尋結果",
                        description=f"沒有找到包含 '{search_term}' 的準心",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
                    return
                
                crosshairs = filtered
            
            # 創建翻頁界面
            view = CrosshairView(crosshairs, user_id=ctx.author.id)
            embed = view.create_embed()
            
            # 添加搜尋資訊到embed
            if search_term:
                embed.title += f" - 搜尋: {search_term}"
            
            await ctx.send(embed=embed, view=view)
            
            # 記錄日誌
            search_info = f" (搜尋: {search_term})" if search_term else ""
            BotLogger.command_used(
                "repo", 
                ctx.author.id, 
                ctx.guild.id if ctx.guild else 0, 
                f"瀏覽準心庫{search_info} - 共 {len(crosshairs)} 個"
            )
            
        except Exception as e:
            BotLogger.error("Repo", f"瀏覽準心庫失敗: {e}")
            import traceback
            traceback.print_exc()
            
            # 提供更詳細的錯誤資訊
            error_msg = f"❌ 載入準心庫時發生錯誤: {str(e)[:100]}"
            await ctx.send(error_msg)

    @commands.command(name="repo_add", aliases=["新增準心"], help="新增準心到代碼庫")
    async def repo_add(self, ctx, game: str, tag: str, *, code_and_image: str):
        """新增準心到代碼庫"""
        try:
            crosshairs = await self._load_crosshairs()
            
            # 解析代碼和圖片URL
            parts = code_and_image.strip().split()
            
            # 如果最後一部分看起來像URL，就當作圖片
            image_url = None
            if parts and (parts[-1].startswith('http://') or parts[-1].startswith('https://')):
                image_url = parts[-1]
                code = ' '.join(parts[:-1])
            else:
                code = code_and_image
            
            # 生成新ID
            new_id = self._generate_id(game, crosshairs)
            
            # 建立新準心
            new_crosshair = {
                "id": new_id,
                "game": game,
                "tag": tag,
                "code": code.strip(),
                "image_url": image_url
            }
            
            # 新增並儲存
            crosshairs.append(new_crosshair)
            await self._save_crosshairs(crosshairs)
            
            # 確認訊息
            embed = discord.Embed(
                title="✅ 準心新增成功",
                color=discord.Color.green()
            )
            embed.add_field(name="遊戲", value=game, inline=True)
            embed.add_field(name="標籤", value=tag, inline=True)
            embed.add_field(name="ID", value=new_id, inline=True)
            embed.add_field(name="代碼長度", value=f"{len(code)} 字符", inline=False)
            
            if image_url:
                embed.add_field(name="預覽圖片", value="✅ 已設定", inline=True)
                embed.set_thumbnail(url=image_url)
            else:
                embed.add_field(name="預覽圖片", value="❌ 未設定", inline=True)
            
            await ctx.send(embed=embed)
            
            BotLogger.command_used("repo_add", ctx.author.id, ctx.guild.id if ctx.guild else 0, 
                                   f"新增準心: {new_id} - {game} {tag}")
            
        except Exception as e:
            BotLogger.error("Repo", f"新增準心失敗: {e}")
            await ctx.send("❌ 新增準心失敗")

    @repo_add.error
    async def repo_add_error(self, ctx, error):
        """處理新增準心指令錯誤"""
        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="❌ 參數錯誤",
                description="**用法：** `?repo_add <遊戲> <標籤> <準心代碼> [圖片URL]`\n\n"
                           "**範例：**\n"
                           "`?repo_add Valorant 精準型 0;P;c;5;h;0;m;1;0l;2;0o;2;0a;1;0f;0;1b;0`\n"
                           "`?repo_add CS2 點狀 CSGO_123... https://i.imgur.com/example.png`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(name="repo_del", aliases=["刪除準心"], help="刪除指定ID的準心")
    async def repo_delete(self, ctx, crosshair_id: str):
        """刪除指定ID的準心"""
        try:
            crosshairs = await self._load_crosshairs()
            
            # 尋找要刪除的準心
            target_index = -1
            target_crosshair = None
            
            for i, ch in enumerate(crosshairs):
                if str(ch.get('id', '')).lower() == crosshair_id.lower():
                    target_index = i
                    target_crosshair = ch
                    break
            
            if target_index == -1:
                embed = discord.Embed(
                    title="❌ 找不到準心",
                    description=f"ID `{crosshair_id}` 的準心不存在",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            
            # 刪除準心
            crosshairs.pop(target_index)
            await self._save_crosshairs(crosshairs)
            
            # 確認訊息
            embed = discord.Embed(
                title="✅ 準心刪除成功",
                description=f"已刪除 **{target_crosshair.get('tag', '未知')}** ({target_crosshair.get('game', '未知遊戲')})",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            
            BotLogger.command_used("repo_del", ctx.author.id, ctx.guild.id if ctx.guild else 0, 
                                   f"刪除準心: {crosshair_id}")
            
        except Exception as e:
            BotLogger.error("Repo", f"刪除準心失敗: {e}")
            await ctx.send("❌ 刪除準心失敗")

    @repo_delete.error
    async def repo_delete_error(self, ctx, error):
        """處理刪除準心指令錯誤"""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ 請提供要刪除的準心ID，例如：`?repo_del val/1`")


async def setup(bot):
    await bot.add_cog(Repo(bot))