import asyncio
import random

import discord
from discord import ui
from discord.ext import commands

from utils import util
from ui.components import BaseView, EmbedBuilder

DRAW_COOLDOWN = util.Cooldown(30)
DRAW_HISTORY_PATH = "data/draw_history.json"


# Draw 模組專用的 Embed 建立器
class DrawEmbeds:
    """Draw 模組專用的 Embed 建立器"""
    
    @staticmethod
    def create_draw_announcement(prizes: dict[str, int], note: str, author_name: str):
        """創建抽獎公告的 Embed"""
        embed = discord.Embed(title="🎁 抽獎時間！", color=discord.Color.gold())
        embed.add_field(name="獎項內容", 
                       value="\n".join(f"{name} × {qty}" for name, qty in prizes.items()), 
                       inline=False)
        if note:
            embed.add_field(name="備註", value=note, inline=False)
        embed.set_footer(text=f"由 {author_name} 發起")
        return embed
    
    @staticmethod
    def create_draw_history(records: list):
        """創建抽獎紀錄的 Embed"""
        embed = EmbedBuilder.info(
            title="📜 抽獎紀錄（最近 20 筆）",
            description="顯示最近 5 筆紀錄"
        )
        
        for r in records[:5]:
            prizes_str = ", ".join(f"{k}×{v}" for k, v in r["prizes"].items())
            winners_str = ", ".join(
                f"{k}:{'、'.join(v)}" for k, v in r["winners"].items() if v
            )
            desc = f"🎁 {prizes_str}\n👑 {winners_str or '無'}\n🕒 {r['time']}"
            if r.get("note"):
                desc += f"\n📌 {r['note']}"
            embed.add_field(name=f"主持人：{r['host']}", value=desc, inline=False)
        
        return embed


class DrawView(BaseView):
    def __init__(self, author_user: discord.User, prizes: dict[str, int], note: str):
        # DrawView 需要永久存在，所以使用 None timeout
        super().__init__(author_user, timeout=None)
        self.author_id = author_user.id  # 保持向後相容
        self.prizes = prizes
        self.note = note
        self.participants: list[discord.Member] = []
        self.allow_duplicates = False

        self.join_button = ui.Button(
            label="參加抽獎", style=discord.ButtonStyle.green)
        self.draw_button = ui.Button(
            label="開始抽獎", style=discord.ButtonStyle.blurple)
        self.toggle_button = ui.Button(
            label="允許重複得獎 ❌", style=discord.ButtonStyle.gray)

        self.join_button.callback = self.join_callback
        self.draw_button.callback = self.draw_callback
        self.toggle_button.callback = self.toggle_callback

        self.add_item(self.join_button)
        self.add_item(self.draw_button)
        self.add_item(self.toggle_button)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """重寫互動檢查：抽獎系統有特殊的權限需求"""
        # 參加抽獎：任何人都可以
        if interaction.data.get('custom_id') == self.join_button.custom_id:
            return True
        
        # 切換設定：只有主持人可以
        if interaction.data.get('custom_id') == self.toggle_button.custom_id:
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("只有抽獎主持人可以切換設定。", ephemeral=True)
                return False
            return True
        
        # 開始抽獎：主持人或有管理權限的用戶
        if interaction.data.get('custom_id') == self.draw_button.custom_id:
            if (interaction.user.id == self.author_id or 
                interaction.user.guild_permissions.manage_messages):
                return True
            await interaction.response.send_message("你沒有權限進行抽獎。", ephemeral=True)
            return False
        
        return True

    async def join_callback(self, interaction: discord.Interaction):
        user = interaction.user
        if user not in self.participants:
            self.participants.append(user)
            await interaction.response.send_message(f"{user.mention} 已加入抽獎池！", ephemeral=True)
        else:
            await interaction.response.send_message("你已經加入抽獎池囉！", ephemeral=True)

    async def toggle_callback(self, interaction: discord.Interaction):
        # 權限檢查已在 interaction_check 中處理
        self.allow_duplicates = not self.allow_duplicates
        self.toggle_button.label = f"允許重複得獎 {'✅' if self.allow_duplicates else '❌'}"
        await interaction.response.edit_message(view=self)

    async def draw_callback(self, interaction: discord.Interaction):
        # 權限檢查已在 interaction_check 中處理
        if not self.participants:
            await interaction.response.send_message("抽獎池是空的，無法抽獎。", ephemeral=True)
            return

        winners: dict[str, list[str]] = {}
        pool = self.participants.copy()

        for prize, count in self.prizes.items():
            winners[prize] = []
            for _ in range(count):
                if not pool:
                    break
                winner = random.choice(pool)
                winners[prize].append(winner.mention)
                if not self.allow_duplicates:
                    pool.remove(winner)

        result_lines = ["🎉 抽獎結果如下："]
        for prize, names in winners.items():
            if names:
                result_lines.append(
                    f"**{prize}** × {len(names)}：{', '.join(names)}")
            else:
                result_lines.append(f"**{prize}** × 0：⚠️ 無人中獎")

        if self.note:
            result_lines.append(f"📌 備註：{self.note}")

        await interaction.response.edit_message(content="\n".join(result_lines), view=None)

        history = await util.read_json(DRAW_HISTORY_PATH)
        record = {
            "time": util.format_datetime(util.now_local()),
            "prizes": self.prizes,
            "note": self.note,
            "winners": winners,
            "host": interaction.user.name,
        }
        history.setdefault("records", []).insert(0, record)
        history["records"] = history["records"][:20]  # keep last 20
        await util.write_json(DRAW_HISTORY_PATH, history)


class Draw(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["抽"], help="抽獎：輸入獎品名稱 數量，可加 --note 備註")
    async def draw(self, ctx: commands.Context, *, raw: str = None):
        if DRAW_COOLDOWN.is_on_cooldown(ctx.author.id):
            await ctx.send("⏳ 抽獎指令冷卻中，請稍後再試。")
            return
        DRAW_COOLDOWN.update_timestamp(ctx.author.id)

        if not raw:
            await ctx.send("❌ 請提供獎品與數量，例如：`!draw A獎 1 B獎 2 --note 新年快樂`")
            return

        tokens = raw.split()
        prizes: dict[str, int] = {}
        note = ""
        i = 0
        while i < len(tokens):
            if tokens[i] == "--note":
                note = " ".join(tokens[i+1:])
                break
            if i + 1 < len(tokens) and tokens[i+1].isdigit():
                prizes[tokens[i]] = int(tokens[i+1])
                i += 2
            else:
                await ctx.send("❌ 格式錯誤，請提供獎品名稱與數量。")
                return

        if not prizes:
            await ctx.send("❌ 請輸入至少一個獎項與數量。")
            return

        embed = DrawEmbeds.create_draw_announcement(prizes, note, ctx.author.display_name)
        view = DrawView(ctx.author, prizes, note)
        await ctx.send(embed=embed, view=view)

    @commands.command(aliases=["抽獎紀錄"], help="查看最近的抽獎紀錄")
    async def drawlog(self, ctx: commands.Context):
        data = await util.read_json(DRAW_HISTORY_PATH)
        records = data.get("records", [])
        if not records:
            await ctx.send("目前沒有抽獎紀錄。")
            return

        embed = DrawEmbeds.create_draw_history(records)
        await ctx.send(embed=embed)
    
    @commands.command(name="choose", aliases=["選擇"], help="從選項中隨機選擇，支援權重設定")
    async def choose_command(self, ctx, *, args: str = None):
        """
        從提供的選項中隨機選擇，使用冒號語法設定權重
        
        使用方式:
        ?choose 蘋果:2 橘子:7 香蕉 2    - 權重比例 2:7:1，選2個
        ?choose A B C                 - 等權重，選1個  
        ?choose 選項1:10 選項2         - 部分權重，選1個
        """
        if not args:
            await ctx.send("❌ 請提供選項，例如：`?choose 蘋果:2 橘子:7 香蕉` 或 `?choose A B C 2`")
            return
        
        try:
            # 解析輸入 - 簡化版邏輯
            tokens = args.split()
            count = 1
            
            # 檢查最後一個是否為選擇數量
            if len(tokens) > 1:
                try:
                    count = int(tokens[-1])
                    tokens = tokens[:-1]  # 移除數量參數
                except ValueError:
                    pass
            
            # 使用冒號語法解析
            options_with_weights = self._parse_colon_syntax_options(tokens)
            
            if not options_with_weights:
                await ctx.send("❌ 請提供至少一個選項")
                return
            
            # 驗證選擇數量
            if count <= 0:
                await ctx.send("❌ 選擇數量必須大於 0")
                return
            
            if count > len(options_with_weights):
                await ctx.send(f"❌ 選擇數量 ({count}) 不能超過總選項數量 ({len(options_with_weights)})")
                return
            
            # 根據權重進行選擇
            selected = self._weighted_choose(options_with_weights, count)
            
            # 建立回覆訊息 (簡化版)
            message = self._create_choose_message(ctx, options_with_weights, selected)
            await ctx.send(message)
            
        except Exception as e:
            await ctx.send(f"❌ 處理選項時發生錯誤: {str(e)}")
    
    # 移除複雜的舊解析函數 - 現在只使用冒號語法
    
    def _parse_colon_syntax_options(self, options_list: list[str]) -> list[tuple[str, float]]:
        """
        解析冒號語法的選項
        
        格式: "選項名:權重" 或 "選項名" (無權重時等權重)
        例如: ["蘋果:2", "橘子:7", "香蕉"] -> [(蘋果, 0.2), (橘子, 0.7), (香蕉, 0.1)]
        """
        options_with_weights = []
        
        for option in options_list:
            if ':' in option:
                # 有冒號，分離選項名和權重
                parts = option.split(':', 1)  # 只分割第一個冒號
                name = parts[0].strip()
                try:
                    weight = float(parts[1].strip())
                    if weight > 0:
                        options_with_weights.append((name, weight))
                    else:
                        # 權重無效，當作無權重處理
                        options_with_weights.append((name, None))
                except ValueError:
                    # 權重解析失敗，當作無權重處理
                    options_with_weights.append((name, None))
            else:
                # 無冒號，無權重
                options_with_weights.append((option.strip(), None))
        
        # 使用與舊邏輯相同的權重計算
        specified_weights = [w for _, w in options_with_weights if w is not None]
        unspecified_count = len([w for _, w in options_with_weights if w is None])
        
        if specified_weights:
            # 檢查是否為整數比例模式 (任何權重 > 1)
            is_ratio_mode = any(w > 1 for w in specified_weights)
            
            if is_ratio_mode:
                # 整數比例模式：所有權重按比例正規化
                if unspecified_count > 0:
                    # 未指定的選項預設權重為1
                    default_ratio = 1.0
                    options_with_weights = [(name, w if w is not None else default_ratio) 
                                          for name, w in options_with_weights]
                
                # 正規化為機率
                total_ratio = sum(w for _, w in options_with_weights)
                options_with_weights = [(name, w/total_ratio) for name, w in options_with_weights]
            else:
                # 小數模式：權重總和不超過1
                total_specified = sum(specified_weights)
                if total_specified > 1:
                    # 權重總和超過1，正規化
                    options_with_weights = [(name, w/total_specified if w is not None else None) 
                                          for name, w in options_with_weights]
                    remaining_weight = 0
                else:
                    remaining_weight = 1 - total_specified
                
                # 為未設定權重的選項分配權重
                if unspecified_count > 0:
                    default_weight = remaining_weight / unspecified_count
                    options_with_weights = [(name, w if w is not None else default_weight) 
                                          for name, w in options_with_weights]
        else:
            # 所有選項等權重
            equal_weight = 1.0 / len(options_with_weights)
            options_with_weights = [(name, equal_weight) for name, _ in options_with_weights]
        
        return options_with_weights
    
    def _weighted_choose(self, options_with_weights: list[tuple[str, float]], count: int) -> list[str]:
        """根據權重進行選擇"""
        if count == 1:
            # 單選情況
            return [random.choices([name for name, _ in options_with_weights], 
                                 weights=[weight for _, weight in options_with_weights])[0]]
        else:
            # 多選情況，不重複選擇
            selected = []
            available_options = options_with_weights.copy()
            
            for _ in range(count):
                if not available_options:
                    break
                    
                names, weights = zip(*available_options)
                chosen = random.choices(list(names), weights=list(weights))[0]
                selected.append(chosen)
                
                # 移除已選中的選項
                available_options = [(name, weight) for name, weight in available_options if name != chosen]
            
            return selected
    
    def _create_choose_message(self, ctx, options_with_weights: list[tuple[str, float]], selected: list[str]) -> str:
        """建立簡化的選擇結果訊息"""
        
        # 簡化的結果顯示
        if len(selected) == 1:
            result = f"🎯 **{selected[0]}**"
        else:
            result = "、".join(f"**{item}**" for item in selected)
        
        # 顯示權重資訊（如果有非等權重）
        weights = [weight for _, weight in options_with_weights]
        has_custom_weights = len(set(weights)) > 1  # 檢查是否有不同權重
        
        message_parts = [f"🎲 {ctx.author.display_name} 的選擇結果：{result}"]
        
        if has_custom_weights:
            weight_info = "、".join(f"{name}({weight:.1%})" for name, weight in options_with_weights)
            message_parts.append(f"📋 權重設定：{weight_info}")
        
        return "\n".join(message_parts)
    
    def _create_choose_message_for_slash(self, interaction: discord.Interaction, 
                                       options_with_weights: list[tuple[str, float]], 
                                       selected: list[str]) -> str:
        """為slash指令建立選擇結果訊息"""
        
        # 簡化的結果顯示
        if len(selected) == 1:
            result = f"🎯 **{selected[0]}**"
        else:
            result = "、".join(f"**{item}**" for item in selected)
        
        # 顯示權重資訊（如果有非等權重）
        weights = [weight for _, weight in options_with_weights]
        has_custom_weights = len(set(weights)) > 1  # 檢查是否有不同權重
        
        message_parts = [f"🎲 {interaction.user.display_name} 的選擇結果：{result}"]
        
        if has_custom_weights:
            weight_info = "、".join(f"{name}({weight:.1%})" for name, weight in options_with_weights)
            message_parts.append(f"📋 權重設定：{weight_info}")
        
        return "\n".join(message_parts)
    
    @discord.app_commands.command(name="choose", description="從選項中隨機選擇，支援權重設定")
    @discord.app_commands.describe(
        option1="選項1 (可用 選項名:權重 格式，如: 蘋果:2)",
        option2="選項2 (可用 選項名:權重 格式，如: 橘子:7)",
        option3="選項3 (可用 選項名:權重 格式)",
        option4="選項4 (可用 選項名:權重 格式)",
        option5="選項5 (可用 選項名:權重 格式)",
        count="要選擇的數量 (預設1個)"
    )
    async def choose_slash(self, interaction: discord.Interaction, 
                          option1: str,
                          option2: str = None,
                          option3: str = None,
                          option4: str = None,
                          option5: str = None,
                          count: int = 1):
        """Slash指令版本的選擇器"""
        
        # 收集所有非空選項
        options_list = [opt for opt in [option1, option2, option3, option4, option5] if opt]
        
        if not options_list:
            await interaction.response.send_message("❌ 請至少提供一個選項", ephemeral=True)
            return
        
        try:
            # 使用冒號語法解析
            options_with_weights = self._parse_colon_syntax_options(options_list)
            
            if not options_with_weights:
                await interaction.response.send_message("❌ 請至少提供一個選項", ephemeral=True)
                return
            
            if count <= 0:
                await interaction.response.send_message("❌ 選擇數量必須大於 0", ephemeral=True)
                return
            
            if count > len(options_with_weights):
                await interaction.response.send_message(
                    f"❌ 選擇數量 ({count}) 不能超過總選項數量 ({len(options_with_weights)})",
                    ephemeral=True)
                return
            
            # 進行選擇
            selected = self._weighted_choose(options_with_weights, count)
            
            # 建立回覆訊息
            message = self._create_choose_message_for_slash(interaction, options_with_weights, selected)
            await interaction.response.send_message(message)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ 處理選項時發生錯誤: {str(e)}", ephemeral=True)

    @choose_command.error
    async def choose_error(self, ctx, error):
        """處理 choose 指令錯誤"""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ 請提供選項，例如：`?choose 蘋果:2 橘子:7 香蕉` 或 `?choose A B C 2`")
        else:
            await ctx.send("❌ 指令執行時發生錯誤")


async def setup(bot):
    await bot.add_cog(Draw(bot))
