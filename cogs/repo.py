import discord
from discord.ext import commands
from utils.logger import BotLogger
from utils import util


class CrosshairView(discord.ui.View):
    """準心瀏覽界面 - 包含遊戲分類選擇和翻頁功能"""
    
    def __init__(self, all_crosshairs: list, user_id: int = None):
        super().__init__(timeout=180)  # 3分鐘超時
        self.all_crosshairs = all_crosshairs
        self.user_id = user_id
        
        # 建立遊戲分類字典
        self.games_dict = {}
        for ch in all_crosshairs:
            game = ch['game']
            if game not in self.games_dict:
                self.games_dict[game] = []
            self.games_dict[game].append(ch)
        
        # 當前狀態
        self.selected_game = None
        self.current_crosshairs = []
        self.current_page = 0
        
        # 如果只有一個遊戲，自動選中
        if len(self.games_dict) == 1:
            self.selected_game = list(self.games_dict.keys())[0]
            self.current_crosshairs = self.games_dict[self.selected_game]
        
        # 建立下拉選單選項
        self._setup_game_selector()
        self._update_buttons()
    
    def _setup_game_selector(self):
        """設置遊戲選擇下拉選單"""
        if hasattr(self, 'game_selector'):
            self.remove_item(self.game_selector)
        
        if len(self.games_dict) <= 1:
            return  # 只有一個或沒有遊戲時不顯示選單
        
        options = []
        for game, crosshairs in self.games_dict.items():
            emoji = "🎯" if game == "Valorant" else "🔫" if game == "CS2" else "⚡" if "Apex" in game else "🎮"
            options.append(discord.SelectOption(
                label=game,
                value=game,
                description=f"{len(crosshairs)} 個準心",
                emoji=emoji,
                default=(game == self.selected_game)
            ))
        
        self.game_selector = discord.ui.Select(
            placeholder="選擇遊戲分類",
            min_values=1,
            max_values=1,
            options=options,
            row=0  # 放在第一排
        )
        self.game_selector.callback = self._on_game_select
        self.add_item(self.game_selector)
    
    async def _on_game_select(self, interaction: discord.Interaction):
        """處理遊戲選擇"""
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 只有指令使用者可以操作此選單", ephemeral=True)
            return
        
        selected_game = self.game_selector.values[0]
        self.selected_game = selected_game
        self.current_crosshairs = self.games_dict[selected_game]
        self.current_page = 0  # 重置到第一頁
        
        # 更新選單的預設選項
        self._setup_game_selector()
        self._update_buttons()
        
        embed = self._create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    def _update_buttons(self):
        """更新按鈕的啟用/停用狀態"""
        max_page = len(self.current_crosshairs) - 1 if self.current_crosshairs else -1
        
        self.prev_button.disabled = (self.current_page <= 0 or not self.current_crosshairs)
        self.next_button.disabled = (self.current_page >= max_page or not self.current_crosshairs)
        
        # 更新頁數顯示
        if self.current_crosshairs:
            self.page_info.label = f"{self.current_page + 1}/{max_page + 1}"
        else:
            self.page_info.label = "0/0"
    
    def _create_embed(self) -> discord.Embed:
        """創建當前頁面的 embed"""
        # 如果沒有選擇遊戲，顯示選擇提示
        if not self.selected_game:
            embed = discord.Embed(
                title="🎯 準心代碼庫",
                description="請使用上方的下拉選單選擇遊戲分類",
                color=discord.Color.orange()
            )
            
            # 顯示可用遊戲統計
            game_stats = []
            for game, crosshairs in self.games_dict.items():
                emoji = "🎯" if game == "Valorant" else "🔫" if game == "CS2" else "⚡" if "Apex" in game else "🎮"
                game_stats.append(f"{emoji} **{game}**: {len(crosshairs)} 個準心")
            
            if game_stats:
                embed.add_field(
                    name="📊 可用分類",
                    value="\n".join(game_stats),
                    inline=False
                )
            
            return embed
        
        # 如果選中遊戲但沒有準心
        if not self.current_crosshairs:
            return discord.Embed(
                title=f"🎮 {self.selected_game}",
                description="此遊戲分類目前沒有準心資料",
                color=discord.Color.red()
            )
        
        # 檢查頁數範圍
        if self.current_page < 0 or self.current_page >= len(self.current_crosshairs):
            return discord.Embed(
                title="❌ 頁數錯誤",
                description="無法顯示此頁面",
                color=discord.Color.red()
            )
        
        crosshair = self.current_crosshairs[self.current_page]
        
        # 遊戲圖示映射
        game_emoji = "🎯" if crosshair['game'] == "Valorant" else "🔫" if crosshair['game'] == "CS2" else "⚡" if "Apex" in crosshair['game'] else "🎮"
        
        # 創建 embed
        embed = discord.Embed(
            title=f"{game_emoji} {crosshair['tag']}",
            description=f"**遊戲：** {crosshair['game']}\n**ID：** `{crosshair['id']}`",
            color=discord.Color.blue()
        )
        
        # 添加準心代碼
        embed.add_field(
            name="📋 準心代碼",
            value=f"```\n{crosshair['code']}\n```",
            inline=False
        )
        
        # 設定圖片（如果有的話）
        if crosshair.get('image_url'):
            embed.set_image(url=crosshair['image_url'])
        else:
            embed.add_field(
                name="🖼️ 預覽圖片",
                value="無預覽圖片",
                inline=True
            )
        
        # 添加頁數資訊
        embed.set_footer(text=f"第 {self.current_page + 1} 頁，共 {len(self.current_crosshairs)} 個 {self.selected_game} 準心")
        
        return embed
    
    async def _update_message(self, interaction: discord.Interaction):
        """更新訊息內容和按鈕"""
        self._update_buttons()
        embed = self._create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="上一個", style=discord.ButtonStyle.primary, emoji="⬅️", row=1)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 檢查權限
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 只有指令使用者可以操作此按鈕", ephemeral=True)
            return
        
        if not self.selected_game:
            await interaction.response.send_message("❌ 請先選擇遊戲分類", ephemeral=True)
            return
        
        if self.current_page > 0:
            self.current_page -= 1
            await self._update_message(interaction)
        else:
            await interaction.response.send_message("❌ 已經是第一個準心了", ephemeral=True)
    
    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True, row=1)
    async def page_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 這個按鈕只用於顯示頁數，不做任何操作
        current_game = self.selected_game or "未選擇"
        await interaction.response.send_message(f"ℹ️ 當前分類：{current_game}", ephemeral=True)
    
    @discord.ui.button(label="下一個", style=discord.ButtonStyle.primary, emoji="➡️", row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 檢查權限
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 只有指令使用者可以操作此按鈕", ephemeral=True)
            return
        
        if not self.selected_game:
            await interaction.response.send_message("❌ 請先選擇遊戲分類", ephemeral=True)
            return
        
        max_page = len(self.current_crosshairs) - 1
        if self.current_page < max_page:
            self.current_page += 1
            await self._update_message(interaction)
        else:
            await interaction.response.send_message("❌ 已經是最後一個準心了", ephemeral=True)
    
    async def on_timeout(self):
        """處理超時"""
        # 禁用所有按鈕
        for item in self.children:
            item.disabled = True


class Repo(commands.Cog):
    """準心代碼庫功能"""
    
    def __init__(self, bot):
        self.bot = bot
        self.data_file = "repo.json"
    
    async def _load_repo_data(self) -> dict:
        """載入準心資料和遊戲前綴"""
        try:
            file_path = util.get_data_file_path(self.data_file)
            data = await util.read_json(file_path)
            return {
                'crosshairs': data.get('crosshairs', []),
                'game_prefixes': data.get('game_prefixes', {})
            }
        except Exception as e:
            BotLogger.error("Repo", f"載入準心資料失敗: {e}")
            return {'crosshairs': [], 'game_prefixes': {}}
    
    async def _load_crosshairs(self) -> list:
        """載入準心資料（向後相容）"""
        data = await self._load_repo_data()
        return data['crosshairs']
    
    async def _save_repo_data(self, crosshairs: list, game_prefixes: dict):
        """儲存準心資料和遊戲前綴"""
        try:
            file_path = util.get_data_file_path(self.data_file)
            data = {
                "crosshairs": crosshairs,
                "game_prefixes": game_prefixes
            }
            await util.write_json(file_path, data)
            BotLogger.info("Repo", f"成功儲存 {len(crosshairs)} 個準心資料")
        except Exception as e:
            BotLogger.error("Repo", f"儲存準心資料失敗: {e}")
            raise
    
    def _generate_game_id(self, game: str, crosshairs: list, game_prefixes: dict) -> str:
        """為指定遊戲生成新的ID"""
        # 獲取或創建遊戲前綴
        if game in game_prefixes:
            prefix = game_prefixes[game]
        else:
            # 為新遊戲自動生成前綴（取前3個字母的小寫）
            prefix = ''.join(c.lower() for c in game if c.isalpha())[:3]
            game_prefixes[game] = prefix
        
        # 找出該遊戲現有的最大ID號碼
        max_num = 0
        for ch in crosshairs:
            ch_id = ch.get('id', '')
            if ch_id.startswith(f"{prefix}/"):
                try:
                    num = int(ch_id.split('/')[-1])
                    max_num = max(max_num, num)
                except ValueError:
                    continue
        
        return f"{prefix}/{max_num + 1}"
    
    @commands.command(name="repo", aliases=["準心", "crosshair"], help="瀏覽準心代碼庫")
    async def repo_browse(self, ctx, *, search_term: str = None):
        """
        瀏覽準心代碼庫
        
        Args:
            search_term: 可選的搜尋關鍵字（遊戲名稱或標籤）
        """
        try:
            crosshairs = await self._load_crosshairs()
            
            if not crosshairs:
                embed = discord.Embed(
                    title="📦 準心代碼庫",
                    description="目前沒有任何準心資料\n使用 `?repo_add` 來新增準心",
                    color=discord.Color.orange()
                )
                await ctx.send(embed=embed)
                return
            
            # 如果有搜尋關鍵字，進行過濾
            if search_term:
                search_term = search_term.lower()
                filtered_crosshairs = [
                    ch for ch in crosshairs 
                    if search_term in ch['game'].lower() or search_term in ch['tag'].lower()
                ]
                
                if not filtered_crosshairs:
                    embed = discord.Embed(
                        title="🔍 搜尋結果",
                        description=f"沒有找到包含 '{search_term}' 的準心",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
                    return
                
                crosshairs = filtered_crosshairs
            
            # 創建翻頁界面
            view = CrosshairView(crosshairs, user_id=ctx.author.id)
            embed = view._create_embed()
            
            # 發送訊息
            message = await ctx.send(embed=embed, view=view)
            
            # 記錄日誌
            search_info = f" (搜尋: {search_term})" if search_term else ""
            BotLogger.command_used(
                "repo", 
                ctx.author.id, 
                ctx.guild.id if ctx.guild else 0, 
                f"瀏覽準心庫{search_info} - 共 {len(crosshairs)} 個"
            )
            
        except Exception as e:
            error_msg = f"載入準心庫時發生錯誤: {str(e)}"
            BotLogger.error("Repo", error_msg, e)
            
            embed = discord.Embed(
                title="❌ 錯誤",
                description="載入準心庫時發生錯誤，請稍後再試",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
    
    @commands.command(name="repo_add", aliases=["新增準心"], help="新增準心到代碼庫")
    async def repo_add(self, ctx, game: str, tag: str, code: str, image_url: str = None):
        """
        新增準心到代碼庫
        
        Args:
            game: 遊戲名稱
            tag: 自訂標籤
            code: 準心代碼
            image_url: 可選的預覽圖片URL
        """
        try:
            crosshairs = await self._load_crosshairs()
            
            # 生成新的ID
            new_id = max([ch.get('id', 0) for ch in crosshairs], default=0) + 1
            
            # 創建新準心資料
            new_crosshair = {
                "id": new_id,
                "game": game,
                "code": code,
                "image_url": image_url,
                "tag": tag
            }
            
            # 添加到列表
            crosshairs.append(new_crosshair)
            
            # 儲存資料
            await self._save_crosshairs(crosshairs)
            
            # 創建確認 embed
            embed = discord.Embed(
                title="✅ 準心新增成功",
                color=discord.Color.green()
            )
            embed.add_field(name="遊戲", value=game, inline=True)
            embed.add_field(name="標籤", value=tag, inline=True)
            embed.add_field(name="ID", value=str(new_id), inline=True)
            embed.add_field(name="代碼", value=f"```\n{code}\n```", inline=False)
            
            if image_url:
                embed.set_thumbnail(url=image_url)
            
            await ctx.send(embed=embed)
            
            BotLogger.command_used(
                "repo_add", 
                ctx.author.id, 
                ctx.guild.id if ctx.guild else 0, 
                f"新增準心: {game} - {tag}"
            )
            
        except Exception as e:
            error_msg = f"新增準心失敗: {str(e)}"
            BotLogger.error("Repo", error_msg, e)
            await ctx.send(f"❌ {error_msg}")
    
    @repo_add.error
    async def repo_add_error(self, ctx, error):
        """處理 repo_add 指令錯誤"""
        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="❌ 參數錯誤",
                description="請提供完整的參數\n\n**用法：**\n`?repo_add <遊戲> <標籤> <代碼> [圖片URL]`\n\n**範例：**\n`?repo_add Valorant 精準型 0;P;c;5;... https://imgur.com/image.png`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        else:
            BotLogger.error("Repo", f"repo_add 指令錯誤: {error}")
    
    @commands.command(name="repo_del", aliases=["刪除準心"], help="刪除準心代碼")
    async def repo_delete(self, ctx, crosshair_id: int):
        """
        刪除指定ID的準心
        
        Args:
            crosshair_id: 要刪除的準心ID
        """
        try:
            crosshairs = await self._load_crosshairs()
            
            # 尋找要刪除的準心
            target_crosshair = None
            target_index = -1
            
            for i, ch in enumerate(crosshairs):
                if ch.get('id') == crosshair_id:
                    target_crosshair = ch
                    target_index = i
                    break
            
            if target_crosshair is None:
                embed = discord.Embed(
                    title="❌ 找不到準心",
                    description=f"ID {crosshair_id} 的準心不存在",
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
                description=f"已刪除 **{target_crosshair['tag']}** ({target_crosshair['game']})",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            
            BotLogger.command_used(
                "repo_del", 
                ctx.author.id, 
                ctx.guild.id if ctx.guild else 0, 
                f"刪除準心 ID {crosshair_id}: {target_crosshair['tag']}"
            )
            
        except Exception as e:
            error_msg = f"刪除準心失敗: {str(e)}"
            BotLogger.error("Repo", error_msg, e)
            await ctx.send(f"❌ {error_msg}")
    
    @repo_delete.error
    async def repo_delete_error(self, ctx, error):
        """處理 repo_del 指令錯誤"""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ 請提供要刪除的準心ID，例如：`?repo_del 1`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ 準心ID必須是數字，例如：`?repo_del 1`")
        else:
            BotLogger.error("Repo", f"repo_del 指令錯誤: {error}")
    
    @commands.command(name="repo_list", aliases=["準心列表"], help="顯示所有準心的簡要列表")
    async def repo_list(self, ctx):
        """顯示所有準心的簡要列表"""
        try:
            crosshairs = await self._load_crosshairs()
            
            if not crosshairs:
                embed = discord.Embed(
                    title="📦 準心代碼庫",
                    description="目前沒有任何準心資料",
                    color=discord.Color.orange()
                )
                await ctx.send(embed=embed)
                return
            
            # 創建列表 embed
            embed = discord.Embed(
                title="📋 準心代碼列表",
                description=f"共有 {len(crosshairs)} 個準心",
                color=discord.Color.blue()
            )
            
            # 按遊戲分組顯示
            games = {}
            for ch in crosshairs:
                game = ch['game']
                if game not in games:
                    games[game] = []
                games[game].append(f"`{ch['id']}` {ch['tag']}")
            
            for game, items in games.items():
                embed.add_field(
                    name=f"🎮 {game}",
                    value="\n".join(items),
                    inline=False
                )
            
            embed.set_footer(text="使用 ?repo [搜尋關鍵字] 來瀏覽詳細內容")
            
            await ctx.send(embed=embed)
            
            BotLogger.command_used(
                "repo_list", 
                ctx.author.id, 
                ctx.guild.id if ctx.guild else 0, 
                f"查看準心列表 - 共 {len(crosshairs)} 個"
            )
            
        except Exception as e:
            error_msg = f"載入準心列表失敗: {str(e)}"
            BotLogger.error("Repo", error_msg, e)
            await ctx.send(f"❌ {error_msg}")
    
    @commands.command(name="repo_help", aliases=["準心幫助"], help="顯示準心庫功能說明")
    async def repo_help(self, ctx):
        """顯示準心庫功能說明"""
        embed = discord.Embed(
            title="🎯 準心代碼庫功能說明",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📖 瀏覽指令",
            value="`?repo` - 瀏覽所有準心（翻頁模式）\n"
                  "`?repo <關鍵字>` - 搜尋特定準心\n"
                  "`?repo_list` - 顯示簡要列表",
            inline=False
        )
        
        embed.add_field(
            name="✏️ 管理指令",
            value="`?repo_add <遊戲> <標籤> <代碼> [圖片]` - 新增準心\n"
                  "`?repo_del <ID>` - 刪除指定準心",
            inline=False
        )
        
        embed.add_field(
            name="💡 使用範例",
            value="```\n"
                  "?repo Valorant          # 搜尋 Valorant 準心\n"
                  "?repo_add CS2 點狀型 CSGO_123... https://imgur.com/pic.png\n"
                  "?repo_del val/1         # 刪除 ID val/1 的準心\n"
                  "```",
            inline=False
        )
        
        embed.add_field(
            name="🎮 支援遊戲",
            value="Valorant, CS2, Apex Legends 等各種 FPS 遊戲",
            inline=False
        )
        
        embed.add_field(
            name="🆔 ID 格式說明",
            value="ID 採用 `遊戲前綴/編號` 格式\n"
                  "例如：`val/1`, `cs/2`, `apex/1`\n"
                  "每個遊戲的編號獨立計算",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
        BotLogger.command_used(
            "repo_help", 
            ctx.author.id, 
            ctx.guild.id if ctx.guild else 0, 
            "查看準心庫說明"
        )


async def setup(bot):
    await bot.add_cog(Repo(bot))