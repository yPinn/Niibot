# Discord.py 2.x 範例

**版本**: 2.6.4 | **Python**: 3.8+

## 最小 Bot

```python
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command()
async def ping(ctx: commands.Context):
    await ctx.send("Pong!")

bot.run("TOKEN")
```

---

## Slash Commands 範例

### 基本 Slash Command

```python
import discord
from discord import app_commands

@bot.tree.command(name="greet", description="打招呼")
@app_commands.describe(name="要打招呼的對象")
async def greet(interaction: discord.Interaction, name: str = None):
    target = name or interaction.user.name
    await interaction.response.send_message(f"Hello, {target}!")
```

### 帶選項的指令

```python
from typing import Literal

@bot.tree.command(name="ban", description="封禁使用者")
@app_commands.describe(
    member="要封禁的成員",
    reason="封禁原因",
    delete_days="刪除幾天內的訊息"
)
async def ban(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "無",
    delete_days: Literal[0, 1, 7] = 0
):
    await member.ban(reason=reason, delete_message_days=delete_days)
    await interaction.response.send_message(f"已封禁 {member.mention}")
```

### Autocomplete 自動完成

```python
FRUITS = ["apple", "banana", "cherry", "durian", "elderberry"]

async def fruit_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=fruit, value=fruit)
        for fruit in FRUITS if current.lower() in fruit.lower()
    ][:25]  # Discord 限制 25 個選項

@bot.tree.command(name="fruit", description="選擇水果")
@app_commands.describe(name="水果名稱")
@app_commands.autocomplete(name=fruit_autocomplete)
async def fruit(interaction: discord.Interaction, name: str):
    await interaction.response.send_message(f"你選擇了: {name}")
```

### Slash Command 群組

```python
admin_group = app_commands.Group(name="admin", description="管理指令")

@admin_group.command(name="kick", description="踢出成員")
@app_commands.describe(member="要踢出的成員")
async def admin_kick(interaction: discord.Interaction, member: discord.Member):
    await member.kick()
    await interaction.response.send_message(f"已踢出 {member.mention}")

@admin_group.command(name="mute", description="禁言成員")
@app_commands.describe(member="要禁言的成員", duration="禁言時長(分鐘)")
async def admin_mute(interaction: discord.Interaction, member: discord.Member, duration: int):
    await interaction.response.send_message(f"{member.mention} 已禁言 {duration} 分鐘")

bot.tree.add_command(admin_group)
```

---

## Cog 範例

### 完整 Cog 模組

```python
# cogs/moderation.py
import discord
from discord import app_commands
from discord.ext import commands

class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def cog_load(self):
        print("Moderation cog loaded")

    @app_commands.command(name="clear", description="清除訊息")
    @app_commands.describe(amount="要清除的訊息數量")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: int):
        if amount > 100:
            await interaction.response.send_message("一次最多清除 100 則訊息", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"已清除 {len(deleted)} 則訊息", ephemeral=True)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot:
            return
        print(f"Deleted: {message.content}")

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("你沒有權限使用這個指令")

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
```

### Context Menu Commands

```python
class ContextMenus(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ctx_menu = app_commands.ContextMenu(
            name="取得使用者資訊",
            callback=self.get_user_info
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    async def get_user_info(self, interaction: discord.Interaction, member: discord.Member):
        embed = discord.Embed(
            title=f"{member.name} 的資訊",
            color=member.color
        )
        embed.add_field(name="ID", value=member.id)
        embed.add_field(name="加入時間", value=member.joined_at.strftime("%Y-%m-%d"))
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ContextMenus(bot))
```

---

## 事件監聽

### 歡迎訊息

```python
@bot.event
async def on_member_join(member: discord.Member):
    channel = member.guild.system_channel
    if channel:
        embed = discord.Embed(
            title="歡迎!",
            description=f"{member.mention} 加入了伺服器!",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)
```

### 反應角色

```python
ROLE_EMOJI = {
    "🎮": 123456789,  # 遊戲角色 ID
    "🎵": 987654321,  # 音樂角色 ID
}

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.emoji.name not in ROLE_EMOJI:
        return

    guild = bot.get_guild(payload.guild_id)
    role = guild.get_role(ROLE_EMOJI[payload.emoji.name])
    member = guild.get_member(payload.user_id)

    if member and role:
        await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.emoji.name not in ROLE_EMOJI:
        return

    guild = bot.get_guild(payload.guild_id)
    role = guild.get_role(ROLE_EMOJI[payload.emoji.name])
    member = guild.get_member(payload.user_id)

    if member and role:
        await member.remove_roles(role)
```

### 訊息記錄

```python
@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if before.content == after.content:
        return

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    embed = discord.Embed(
        title="訊息編輯",
        color=discord.Color.orange()
    )
    embed.add_field(name="作者", value=before.author.mention)
    embed.add_field(name="頻道", value=before.channel.mention)
    embed.add_field(name="編輯前", value=before.content, inline=False)
    embed.add_field(name="編輯後", value=after.content, inline=False)
    await log_channel.send(embed=embed)
```

---

## 定時任務

### 定時公告

```python
from discord.ext import tasks
from datetime import time

class Announcements(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.daily_announce.start()

    def cog_unload(self):
        self.daily_announce.cancel()

    @tasks.loop(time=time(hour=12, minute=0))  # 每天 12:00
    async def daily_announce(self):
        channel = self.bot.get_channel(ANNOUNCE_CHANNEL_ID)
        await channel.send("每日公告!")

    @daily_announce.before_loop
    async def before_announce(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(Announcements(bot))
```

### 自動備份

```python
import json
from pathlib import Path

class AutoBackup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.backup.start()

    def cog_unload(self):
        self.backup.cancel()

    @tasks.loop(hours=6)  # 每 6 小時
    async def backup(self):
        data = {
            "guilds": len(self.bot.guilds),
            "users": len(self.bot.users),
            "timestamp": discord.utils.utcnow().isoformat()
        }
        Path("backups").mkdir(exist_ok=True)
        with open("backups/bot_data.json", "w") as f:
            json.dump(data, f, indent=2)
        print("Backup completed")

    @backup.error
    async def backup_error(self, error: Exception):
        print(f"Backup error: {error}")

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoBackup(bot))
```

---

## Views 與按鈕

### 確認按鈕

```python
class ConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.value = None

    @discord.ui.button(label="確認", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.send_message("已確認!", ephemeral=True)

    @discord.ui.button(label="取消", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.send_message("已取消!", ephemeral=True)

@bot.command()
async def delete_all(ctx: commands.Context):
    view = ConfirmView()
    await ctx.send("確定要刪除所有資料嗎?", view=view)
    await view.wait()
    if view.value:
        # 執行刪除
        await ctx.send("已刪除所有資料")
```

### 分頁系統

```python
class Paginator(discord.ui.View):
    def __init__(self, pages: list[discord.Embed]):
        super().__init__(timeout=60)
        self.pages = pages
        self.current_page = 0

    @discord.ui.button(label="◀", style=discord.ButtonStyle.gray)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.current_page])

    @discord.ui.button(label="▶", style=discord.ButtonStyle.gray)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.current_page])

@bot.command()
async def list_items(ctx: commands.Context):
    pages = [
        discord.Embed(title="第 1 頁", description="內容 1"),
        discord.Embed(title="第 2 頁", description="內容 2"),
        discord.Embed(title="第 3 頁", description="內容 3"),
    ]
    view = Paginator(pages)
    await ctx.send(embed=pages[0], view=view)
```

### Modal 表單

```python
class FeedbackModal(discord.ui.Modal, title="意見回饋"):
    name = discord.ui.TextInput(
        label="名稱",
        placeholder="請輸入你的名稱",
        max_length=50
    )

    feedback = discord.ui.TextInput(
        label="意見",
        style=discord.TextStyle.paragraph,
        placeholder="請輸入你的意見",
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"感謝你的回饋, {self.name.value}!",
            ephemeral=True
        )
        # 儲存到資料庫或發送到特定頻道
        channel = interaction.client.get_channel(FEEDBACK_CHANNEL_ID)
        embed = discord.Embed(title="新的回饋", color=discord.Color.blue())
        embed.add_field(name="使用者", value=interaction.user.mention)
        embed.add_field(name="名稱", value=self.name.value)
        embed.add_field(name="意見", value=self.feedback.value, inline=False)
        await channel.send(embed=embed)

@bot.tree.command(name="feedback", description="提供意見回饋")
async def feedback(interaction: discord.Interaction):
    await interaction.response.send_modal(FeedbackModal())
```

---

## 權限檢查

### Slash Command 權限

```python
@bot.tree.command(name="ban", description="封禁使用者")
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.checks.bot_has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member):
    await member.ban()
    await interaction.response.send_message(f"已封禁 {member.mention}")

@ban.error
async def ban_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("你沒有權限使用這個指令", ephemeral=True)
    elif isinstance(error, app_commands.BotMissingPermissions):
        await interaction.response.send_message("Bot 沒有足夠的權限", ephemeral=True)
```

### 自訂檢查

```python
def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

@bot.tree.command(name="config", description="設定")
@is_admin()
async def config(interaction: discord.Interaction):
    await interaction.response.send_message("管理員設定...")
```

---

## 等待使用者輸入

### 等待訊息

```python
@bot.command()
async def quiz(ctx: commands.Context):
    await ctx.send("1 + 1 = ?")

    def check(m: discord.Message):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", timeout=30.0, check=check)
        if msg.content == "2":
            await ctx.send("正確!")
        else:
            await ctx.send("錯誤!")
    except asyncio.TimeoutError:
        await ctx.send("時間到!")
```

### 等待反應

```python
@bot.command()
async def vote(ctx: commands.Context, *, question: str):
    msg = await ctx.send(f"投票: {question}")
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")

    def check(reaction: discord.Reaction, user: discord.User):
        return user == ctx.author and str(reaction.emoji) in ["👍", "👎"]

    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
        await ctx.send(f"你投了 {reaction.emoji}")
    except asyncio.TimeoutError:
        await ctx.send("投票時間結束!")
```

---

## API 查詢與操作

### 伺服器資訊

```python
@bot.tree.command(name="serverinfo", description="顯示伺服器資訊")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(
        title=guild.name,
        description=guild.description or "無描述",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.add_field(name="擁有者", value=guild.owner.mention)
    embed.add_field(name="成員數", value=guild.member_count)
    embed.add_field(name="創建時間", value=guild.created_at.strftime("%Y-%m-%d"))
    embed.add_field(name="驗證等級", value=guild.verification_level)
    await interaction.response.send_message(embed=embed)
```

### 批次操作

```python
@bot.tree.command(name="massban", description="批次封禁")
@app_commands.checks.has_permissions(ban_members=True)
async def massban(interaction: discord.Interaction, user_ids: str):
    await interaction.response.defer()

    ids = [int(id.strip()) for id in user_ids.split(",")]
    banned = []
    failed = []

    for user_id in ids:
        try:
            user = await bot.fetch_user(user_id)
            await interaction.guild.ban(user)
            banned.append(f"{user.name}#{user.discriminator}")
        except Exception as e:
            failed.append(f"ID {user_id}: {e}")

    result = f"成功: {len(banned)}\n失敗: {len(failed)}"
    await interaction.followup.send(result)
```

---

## 檔案處理

### 發送檔案

```python
@bot.command()
async def send_file(ctx: commands.Context):
    with open("data.txt", "rb") as f:
        file = discord.File(f, filename="data.txt")
        await ctx.send("這是檔案", file=file)
```

### 接收檔案

```python
@bot.event
async def on_message(message: discord.Message):
    if message.attachments:
        for attachment in message.attachments:
            await attachment.save(f"downloads/{attachment.filename}")
            print(f"已儲存: {attachment.filename}")
```

---

## 錯誤處理

### 全域錯誤處理

```python
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingPermissions):
        await ctx.send("你沒有權限使用這個指令")
        return

    if isinstance(error, commands.BotMissingPermissions):
        await ctx.send("Bot 沒有足夠的權限執行此操作")
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"缺少必要參數: `{error.param.name}`")
        return

    if isinstance(error, commands.BadArgument):
        await ctx.send("參數格式錯誤")
        return

    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"指令冷卻中，請等待 {error.retry_after:.1f} 秒")
        return

    # 未處理的錯誤
    print(f"未處理的錯誤: {error}", exc_info=error)
```

### Slash Command 錯誤處理

```python
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("你沒有權限", ephemeral=True)
    elif isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"冷卻中，請等待 {error.retry_after:.1f} 秒",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(f"發生錯誤: {error}", ephemeral=True)
```
