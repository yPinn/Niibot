import asyncio
import random

import discord
from discord import ui
from discord.ext import commands

from utils import util

DRAW_COOLDOWN = util.Cooldown(30)
DRAW_HISTORY_PATH = "data/draw_history.json"


class DrawView(ui.View):
    def __init__(self, author_id: int, prizes: dict[str, int], note: str):
        super().__init__(timeout=None)
        self.author_id = author_id
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

    async def join_callback(self, interaction: discord.Interaction):
        user = interaction.user
        if user not in self.participants:
            self.participants.append(user)
            await interaction.response.send_message(f"{user.mention} 已加入抽獎池！", ephemeral=True)
        else:
            await interaction.response.send_message("你已經加入抽獎池囉！", ephemeral=True)

    async def toggle_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("只有抽獎主持人可以切換設定。", ephemeral=True)
            return
        self.allow_duplicates = not self.allow_duplicates
        self.toggle_button.label = f"允許重複得獎 {'✅' if self.allow_duplicates else '❌'}"
        await interaction.response.edit_message(view=self)

    async def draw_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id and not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("你沒有權限進行抽獎。", ephemeral=True)
            return

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

        embed = discord.Embed(title="🎁 抽獎時間！", color=discord.Color.gold())
        embed.add_field(name="獎項內容", value="\n".join(
            f"{name} × {qty}" for name, qty in prizes.items()), inline=False)
        if note:
            embed.add_field(name="備註", value=note, inline=False)
        embed.set_footer(text=f"由 {ctx.author.display_name} 發起")

        view = DrawView(ctx.author.id, prizes, note)
        await ctx.send(embed=embed, view=view)

    @commands.command(aliases=["抽獎紀錄"], help="查看最近的抽獎紀錄")
    async def drawlog(self, ctx: commands.Context):
        data = await util.read_json(DRAW_HISTORY_PATH)
        records = data.get("records", [])
        if not records:
            await ctx.send("目前沒有抽獎紀錄。")
            return

        embed = discord.Embed(title="📜 抽獎紀錄（最近 20 筆）",
                              color=discord.Color.blue())
        for r in records[:5]:
            prizes_str = ", ".join(f"{k}×{v}" for k, v in r["prizes"].items())
            winners_str = ", ".join(
                f"{k}:{'、'.join(v)}" for k, v in r["winners"].items() if v
            )
            desc = f"🎁 {prizes_str}\n👑 {winners_str or '無'}\n🕒 {r['time']}"
            if r.get("note"):
                desc += f"\n📌 {r['note']}"
            embed.add_field(name=f"主持人：{r['host']}", value=desc, inline=False)

        await ctx.send(embed=embed)
    
    @commands.command(name="choose", aliases=["選擇"], help="從選項中隨機選擇")
    async def choose_command(self, ctx, *, args: str = None):
        """
        從提供的選項中隨機選擇
        
        使用方式:
        ?choose A,B,C          - 從 A,B,C 中選1個
        ?choose A,B,C,D 2      - 從 A,B,C,D 中選2個
        ?choose "選項1,有逗號" "選項2" "選項3" 1  - 使用引號包含複雜選項
        """
        if not args:
            await ctx.send("❌ 請提供選項，例如：`?choose A,B,C` 或 `?choose A,B,C 2`")
            return
        
        try:
            # 解析輸入
            options, count = self._parse_choose_args(args)
            
            if not options:
                await ctx.send("❌ 請提供至少一個選項")
                return
            
            # 驗證選擇數量
            if count <= 0:
                await ctx.send("❌ 選擇數量必須大於 0")
                return
            
            if count > len(options):
                await ctx.send(f"❌ 選擇數量 ({count}) 不能超過總選項數量 ({len(options)})")
                return
            
            # 隨機選擇
            selected = random.sample(options, count)
            
            # 建立回覆 embed
            embed = self._create_choose_embed(ctx, options, selected, count)
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ 處理選項時發生錯誤: {str(e)}")
    
    def _parse_choose_args(self, args: str) -> tuple[list[str], int]:
        """
        解析 choose 指令的參數
        
        支援格式:
        1. "A,B,C" -> 選項用逗號分隔，預設選1個
        2. "A,B,C 2" -> 最後的數字為選擇數量
        3. "選項1" "選項2" "選項3" 2 -> 用引號包含複雜選項
        """
        import shlex
        
        # 先嘗試用 shlex 解析（處理引號）
        try:
            parsed_args = shlex.split(args)
        except ValueError:
            # shlex 解析失敗，回退到空格分割
            parsed_args = args.split()
        
        count = 1  # 預設選擇1個
        
        # 檢查最後一個參數是否為數字
        if len(parsed_args) > 1:
            try:
                count = int(parsed_args[-1])
                # 移除數字參數
                options_args = parsed_args[:-1]
            except ValueError:
                # 最後一個不是數字，全部都是選項
                options_args = parsed_args
        else:
            options_args = parsed_args
        
        # 解析選項
        if len(options_args) == 1:
            # 只有一個參數，檢查是否包含逗號
            single_arg = options_args[0]
            if ',' in single_arg:
                # 用逗號分割
                options = [opt.strip() for opt in single_arg.split(',') if opt.strip()]
            else:
                # 單一選項
                options = [single_arg]
        else:
            # 多個參數，每個都是一個選項
            options = options_args
        
        return options, count
    
    def _create_choose_embed(self, ctx, all_options: list[str], selected: list[str], count: int) -> discord.Embed:
        """建立選擇結果的 embed"""
        
        embed = discord.Embed(
            title="🎲 隨機選擇結果",
            color=discord.Color.gold()
        )
        
        embed.set_author(
            name=f"{ctx.author.display_name} 的選擇",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else None
        )
        
        # 顯示所有選項
        options_display = "、".join(all_options)
        if len(options_display) > 200:
            options_display = options_display[:200] + "..."
        
        embed.add_field(
            name="📋 可選項目",
            value=f"```\n{options_display}\n```",
            inline=False
        )
        
        # 顯示選中結果
        if len(selected) == 1:
            embed.add_field(
                name="🎯 選中結果",
                value=f"🎉 **{selected[0]}**",
                inline=False
            )
        else:
            result_text = "\n".join(f"{i+1}. **{item}**" for i, item in enumerate(selected))
            embed.add_field(
                name=f"🎯 選中結果 (共 {len(selected)} 個)",
                value=result_text,
                inline=False
            )
        
        # 統計資訊
        embed.set_footer(
            text=f"從 {len(all_options)} 個選項中選擇了 {count} 個"
        )
        
        return embed
    
    @choose_command.error
    async def choose_error(self, ctx, error):
        """處理 choose 指令錯誤"""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ 請提供選項，例如：`?choose A,B,C` 或 `?choose A,B,C 2`")
        else:
            await ctx.send("❌ 指令執行時發生錯誤")


async def setup(bot):
    await bot.add_cog(Draw(bot))
