---
name: discordpy
description: Discord.py 2.x Python 非同步函式庫 API 指南。用於 Discord Bot 開發、Slash Commands、事件處理、Cogs 模組系統。當需要撰寫 Discord.py 相關程式碼時自動套用。
allowed-tools: Read, Grep, Glob
---

# Discord.py 2.x API 指南

現代非同步 Python 函式庫，用於 Discord Bot 開發與 Slash Commands。

## 安裝

```bash
pip install discord.py
```

**最新版本**: 2.6.4 (2025)
**Python 版本要求**: 3.8+

---

## 核心架構

```
Client               # 基礎事件處理
  └── Bot            # 加入指令系統
      └── commands.Cog  # 模組化元件
```

---

## Bot 基本結構

```python
import discord
from discord.ext import commands

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # 訊息內容權限
        intents.members = True          # 成員資訊權限

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None  # 停用預設 help
        )

        self.initial_extensions = [
            "cogs.moderation",
            "cogs.utility",
        ]

    async def setup_hook(self):
        """Bot 啟動前的初始化"""
        # 載入 Cogs
        for ext in self.initial_extensions:
            await self.load_extension(ext)

        # 同步 Slash Commands
        await self.tree.sync()

    async def on_ready(self):
        """Bot 就緒時觸發"""
        print(f"Logged in as {self.user}")

bot = MyBot()
bot.run("TOKEN")
```

---

## Slash Commands（斜線指令）

### 基本 Slash Command

```python
import discord
from discord import app_commands

@bot.tree.command(name="hello", description="打招呼")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message(f"Hello {interaction.user.mention}!")

@bot.tree.command(name="add", description="加法計算")
@app_commands.describe(a="第一個數字", b="第二個數字")
async def add(interaction: discord.Interaction, a: int, b: int):
    await interaction.response.send_message(f"{a} + {b} = {a + b}")
```

### 指令群組

```python
group = app_commands.Group(name="config", description="設定指令")

@group.command(name="show", description="顯示設定")
async def config_show(interaction: discord.Interaction):
    await interaction.response.send_message("目前設定...")

@group.command(name="set", description="修改設定")
@app_commands.describe(key="設定項", value="數值")
async def config_set(interaction: discord.Interaction, key: str, value: str):
    await interaction.response.send_message(f"已設定 {key} = {value}")

bot.tree.add_command(group)
```

### Interaction 常用屬性與方法

| 屬性/方法                                      | 說明                     |
| ---------------------------------------------- | ------------------------ |
| `interaction.user`                             | 使用者 (Member/User)     |
| `interaction.guild`                            | 伺服器 (Guild)           |
| `interaction.channel`                          | 頻道 (Channel)           |
| `interaction.command`                          | 呼叫的指令物件           |
| `interaction.namespace`                        | 解析後的指令參數         |
| `interaction.response`                         | InteractionResponse 物件 |
| `interaction.followup`                         | Webhook 用於後續訊息     |
| `interaction.response.send_message()`          | 初次回應訊息 (3 秒內)    |
| `interaction.response.defer()`                 | 延遲回應（顯示載入中）   |
| `interaction.followup.send()`                  | 後續訊息                 |
| `await interaction.original_response()`        | 取得原始回應             |
| `await interaction.edit_original_response()`   | 編輯原始回應             |
| `await interaction.delete_original_response()` | 刪除原始回應             |

---

## Cogs 模組系統

```python
from discord.ext import commands
import discord

class MyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def cog_load(self):
        """Cog 載入時"""
        print(f"{self.__class__.__name__} loaded")

    async def cog_unload(self):
        """Cog 卸載時"""
        print(f"{self.__class__.__name__} unloaded")

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        """前綴指令"""
        await ctx.send("Pong!")

    @app_commands.command(name="info", description="顯示資訊")
    async def info(self, interaction: discord.Interaction):
        """Slash Command"""
        await interaction.response.send_message("資訊...")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """事件監聽"""
        if message.author.bot:
            return
        print(f"{message.author}: {message.content}")

async def setup(bot: commands.Bot):
    await bot.add_cog(MyCog(bot))
```

### 生命週期

| 方法                            | 時機             |
| ------------------------------- | ---------------- |
| `cog_load()`                    | 載入時           |
| `cog_unload()`                  | 卸載時           |
| `cog_check(ctx)`                | 指令檢查（前綴） |
| `cog_before_invoke(ctx)`        | 指令執行前       |
| `cog_after_invoke(ctx)`         | 指令執行後       |
| `cog_command_error(ctx, error)` | 錯誤處理         |

### Cog 管理

```python
# 載入
await bot.load_extension("cogs.moderation")

# 卸載
await bot.unload_extension("cogs.moderation")

# 重載
await bot.reload_extension("cogs.moderation")
```

---

## 事件處理

### 常用事件

```python
@bot.event
async def on_ready():
    """Bot 就緒"""
    print(f"Logged in as {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    """收到訊息"""
    if message.author.bot:
        return
    await bot.process_commands(message)  # 處理指令

@bot.event
async def on_member_join(member: discord.Member):
    """成員加入"""
    channel = member.guild.system_channel
    if channel:
        await channel.send(f"歡迎 {member.mention}!")

@bot.event
async def on_message_delete(message: discord.Message):
    """訊息刪除"""
    print(f"Deleted: {message.content}")
```

### 事件名稱對照

| 事件                    | 觸發時機     |
| ----------------------- | ------------ |
| `on_ready`              | Bot 就緒     |
| `on_message`            | 收到訊息     |
| `on_message_edit`       | 訊息編輯     |
| `on_message_delete`     | 訊息刪除     |
| `on_member_join`        | 成員加入     |
| `on_member_remove`      | 成員離開     |
| `on_member_update`      | 成員更新     |
| `on_guild_join`         | 加入伺服器   |
| `on_reaction_add`       | 新增反應     |
| `on_voice_state_update` | 語音狀態更新 |

---

## Tasks 定時任務

```python
from discord.ext import tasks
from datetime import time

class TaskCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.my_task.start()  # 啟動任務

    def cog_unload(self):
        self.my_task.cancel()  # 停止任務

    @tasks.loop(minutes=10)
    async def my_task(self):
        """每 10 分鐘執行"""
        print("Task running...")

    @my_task.before_loop
    async def before_task(self):
        """任務開始前"""
        await self.bot.wait_until_ready()

    @my_task.error
    async def task_error(self, error: Exception):
        """錯誤處理"""
        print(f"Task error: {error}")
```

### 參數選項

| 參數        | 說明                            |
| ----------- | ------------------------------- |
| `seconds`   | 秒數間隔 (float)                |
| `minutes`   | 分鐘間隔 (float)                |
| `hours`     | 小時間隔 (float)                |
| `time`      | 每日時間 (datetime.time 或序列) |
| `count`     | 執行次數限制 (Optional[int])    |
| `reconnect` | 斷線重連時是否繼續 (bool)       |
| `name`      | 任務內部名稱 (Optional[str])    |

### 控制方法

```python
task.start(*args, **kwargs)  # 啟動任務
task.stop()                   # 完成當前迭代後停止
task.cancel()                 # 立即取消
task.restart(*args, **kwargs) # 重啟任務
task.is_running()            # 是否執行中
task.is_being_cancelled()    # 是否正在取消
task.failed()                # 是否失敗
task.get_task()              # 取得內部 asyncio.Task
task.change_interval(seconds=0, minutes=0, hours=0, time=...)  # 修改間隔
task.add_exception_type(*exceptions)  # 新增要處理的例外
task.remove_exception_type(*exceptions)  # 移除例外類型
task.clear_exception_types()  # 清除所有例外類型
```

---

## Checks 檢查裝飾器

```python
from discord.ext import commands

# 僅限擁有者
@commands.is_owner()
async def owner_command(ctx: commands.Context):
    await ctx.send("Owner only!")

# 權限檢查
@commands.has_permissions(administrator=True)
async def admin_command(ctx: commands.Context):
    await ctx.send("Admin only!")

# 伺服器限定
@commands.guild_only()
async def guild_command(ctx: commands.Context):
    await ctx.send("Guild only!")

# 自訂檢查
def is_in_channel(channel_id: int):
    async def predicate(ctx: commands.Context):
        return ctx.channel.id == channel_id
    return commands.check(predicate)

@is_in_channel(123456789)
async def channel_command(ctx: commands.Context):
    await ctx.send("Correct channel!")
```

---

## Embeds 嵌入訊息

```python
embed = discord.Embed(
    title="標題",
    description="描述文字",
    color=discord.Color.blue()
)

embed.set_author(name="作者", icon_url="https://...")
embed.set_thumbnail(url="https://...")
embed.set_image(url="https://...")
embed.add_field(name="欄位 1", value="內容 1", inline=True)
embed.add_field(name="欄位 2", value="內容 2", inline=True)
embed.set_footer(text="頁尾", icon_url="https://...")

await channel.send(embed=embed)
```

---

## Views 互動元件

```python
import discord

class MyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)  # 180 秒後失效（預設值）

    @discord.ui.button(label="按鈕", style=discord.ButtonStyle.primary, row=0)
    async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("按鈕已點擊!", ephemeral=True)

    @discord.ui.select(
        placeholder="選擇選項",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="選項 1", value="1", emoji="1️⃣"),
            discord.SelectOption(label="選項 2", value="2", emoji="2️⃣"),
        ],
        row=1
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.send_message(f"你選擇了: {select.values[0]}")

    async def on_timeout(self):
        """逾時時觸發"""
        pass

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        """錯誤處理"""
        pass

view = MyView()
await channel.send("互動訊息", view=view)
```

### Select 選單變體

```python
# 使用者選單
discord.ui.UserSelect(placeholder="選擇使用者")

# 角色選單
discord.ui.RoleSelect(placeholder="選擇角色")

# 頻道選單
discord.ui.ChannelSelect(placeholder="選擇頻道")

# 可提及對象選單（使用者+角色）
discord.ui.MentionableSelect(placeholder="選擇對象")
```

---

## 資料查詢

```python
# 取得伺服器
guild = bot.get_guild(guild_id)
guild = await bot.fetch_guild(guild_id)

# 取得成員
member = guild.get_member(user_id)
member = await guild.fetch_member(user_id)

# 取得頻道
channel = bot.get_channel(channel_id)
channel = await bot.fetch_channel(channel_id)

# 取得訊息
message = await channel.fetch_message(message_id)

# 取得使用者
user = bot.get_user(user_id)
user = await bot.fetch_user(user_id)
```

---

## Permissions 權限

```python
# 檢查權限
if member.guild_permissions.administrator:
    print("管理員")

if member.guild_permissions.manage_messages:
    print("可管理訊息")

# 頻道權限
perms = channel.permissions_for(member)
if perms.send_messages:
    print("可發送訊息")

# 權限整數
perms = discord.Permissions(administrator=True)
print(perms.value)  # 8
```

---

## 錯誤處理

```python
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingPermissions):
        await ctx.send("你沒有權限使用這個指令")
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"缺少參數: {error.param.name}")
        return

    if isinstance(error, commands.BadArgument):
        await ctx.send("參數格式錯誤")
        return

    print(f"錯誤: {error}")
```

---

## Modal 表單

```python
class MyModal(discord.ui.Modal, title="表單標題"):
    name = discord.ui.TextInput(
        label="名稱",
        style=discord.TextStyle.short,  # short 或 paragraph
        placeholder="請輸入名稱",
        required=True,
        max_length=100
    )

    feedback = discord.ui.TextInput(
        label="意見",
        style=discord.TextStyle.paragraph,
        placeholder="請輸入詳細意見",
        required=False,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"收到: {self.name.value}")

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message("發生錯誤", ephemeral=True)

# 使用
@bot.tree.command()
async def form(interaction: discord.Interaction):
    await interaction.response.send_modal(MyModal())
```

---

## 相關檔案

- [reference.md](reference.md) - 完整 API 參考
- [examples.md](examples.md) - 程式碼範例

## 官方資源

- [官方文件](https://discordpy.readthedocs.io/)
- [GitHub](https://github.com/Rapptz/discord.py)
- [PyPI](https://pypi.org/project/discord.py/)
- [Discord 伺服器](https://discord.gg/dpy)
