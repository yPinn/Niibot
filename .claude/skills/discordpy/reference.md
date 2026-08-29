# Discord.py 2.x API 參考

**版本**: 2.6.4 (2025-10-08) | **Python**: 3.8+

## Bot 建構參數

| 參數                 | 類型                           | 必填 | 說明                           |
| -------------------- | ------------------------------ | :--: | ------------------------------ |
| `command_prefix`     | `str \| list \| callable`      |  ✓   | 指令前綴                       |
| `intents`            | `discord.Intents`              |  ✓   | Bot 權限意圖                   |
| `help_command`       | `commands.HelpCommand \| None` |  -   | Help 指令（None 為停用）       |
| `description`        | `str`                          |  -   | Bot 描述                       |
| `owner_id`           | `int`                          |  -   | 擁有者 ID                      |
| `owner_ids`          | `set[int]`                     |  -   | 擁有者 ID 集合                 |
| `strip_after_prefix` | `bool`                         |  -   | 移除前綴後空白（預設 False）   |
| `case_insensitive`   | `bool`                         |  -   | 指令不區分大小寫（預設 False） |

**注意**: discord.py 2.x 版本要求 Python 3.8+，最新版本為 2.6.4 (2025)

## Client 額外參數

| 參數           | 類型                | 說明                      |
| -------------- | ------------------- | ------------------------- |
| `max_messages` | `int`               | 訊息快取數量（預設 1000） |
| `proxy`        | `str`               | HTTP 代理 URL             |
| `proxy_auth`   | `aiohttp.BasicAuth` | 代理認證                  |

---

## Intents 權限意圖

```python
intents = discord.Intents.default()  # 預設權限
intents = discord.Intents.all()      # 所有權限（不建議）
intents = discord.Intents.none()     # 無權限

# 特權 Intents（需在 Discord Developer Portal 啟用）
intents.members = True          # 成員事件與快取
intents.presences = True        # 成員狀態更新
intents.message_content = True  # 訊息內容（2022/9 後必需）

# 常用 Intents
intents.guilds = True           # 伺服器事件
intents.messages = True         # 訊息事件
intents.reactions = True        # 反應事件
intents.voice_states = True     # 語音狀態
```

---

## 生命週期方法

```python
await bot.login(token)    # 登入
await bot.connect()       # 連接 WebSocket
await bot.start(token)    # login + connect
bot.run(token)            # 阻塞式啟動（推薦）
await bot.close()         # 關閉連接
```

### 覆寫鉤子

```python
async def setup_hook(self):
    """連接前的設置（載入 Cogs、同步指令）
    在 login() 後、連接 WebSocket 前執行"""

async def on_ready(self):
    """Bot 就緒時（首次或重連後）"""

async def on_connect(self):
    """連接時（可能多次觸發）"""

async def on_disconnect(self):
    """斷線時"""

async def on_resumed(self):
    """恢復連接時"""
```

---

## 指令管理

### 前綴指令

```python
# 註冊
@bot.command(name="ping", aliases=["p"], hidden=False)
async def ping(ctx: commands.Context):
    await ctx.send("Pong!")

# 管理
bot.add_command(cmd)
bot.remove_command("name")
bot.get_command("name")
bot.walk_commands()  # 迭代所有指令
```

### Slash Commands

```python
# 註冊
@bot.tree.command(name="hello", description="打招呼")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message("Hello!")

# 管理
bot.tree.add_command(cmd)
bot.tree.remove_command("name")
bot.tree.get_command("name")

# 同步（必需！）
await bot.tree.sync()                    # 全域同步（1 小時生效）
await bot.tree.sync(guild=guild_obj)     # 伺服器同步（即時）
bot.tree.copy_global_to(guild=guild_obj) # 複製全域到伺服器
await bot.tree.clear_commands(guild=None) # 清除指令
```

---

## Cog 管理

```python
# 載入
await bot.load_extension("cogs.moderation")
await bot.load_extension("folder.subfolder.module")

# 卸載
await bot.unload_extension("cogs.moderation")

# 重載
await bot.reload_extension("cogs.moderation")

# 取得
cog = bot.get_cog("CogClassName")

# 列出所有
bot.cogs  # dict[str, Cog]
```

---

## Context (前綴指令)

### 屬性

| 屬性               | 類型                             | 說明         |
| ------------------ | -------------------------------- | ------------ |
| `ctx.bot`          | `commands.Bot`                   | Bot 實例     |
| `ctx.author`       | `discord.Member \| User`         | 指令使用者   |
| `ctx.guild`        | `discord.Guild \| None`          | 伺服器       |
| `ctx.channel`      | `discord.abc.MessageableChannel` | 頻道         |
| `ctx.message`      | `discord.Message`                | 原始訊息     |
| `ctx.command`      | `commands.Command`               | 指令物件     |
| `ctx.invoked_with` | `str`                            | 使用的指令名 |
| `ctx.args`         | `list`                           | 位置參數     |
| `ctx.kwargs`       | `dict`                           | 關鍵字參數   |

### 方法

```python
await ctx.send("訊息", embed=embed, view=view)
await ctx.reply("回覆")  # 帶引用
await ctx.defer()  # 顯示 "正在輸入..."

message = await ctx.send("文字")
await message.edit(content="新內容")
await message.delete()
```

---

## Interaction (Slash Commands)

### 屬性

| 屬性                    | 類型                             | 說明     |
| ----------------------- | -------------------------------- | -------- |
| `interaction.user`      | `discord.Member \| User`         | 使用者   |
| `interaction.guild`     | `discord.Guild \| None`          | 伺服器   |
| `interaction.channel`   | `discord.abc.MessageableChannel` | 頻道     |
| `interaction.command`   | `app_commands.Command`           | 指令物件 |
| `interaction.namespace` | `Namespace`                      | 參數物件 |
| `interaction.type`      | `InteractionType`                | 互動類型 |

### 回應方法

```python
# 初次回應（3 秒內必需）
await interaction.response.send_message("訊息", ephemeral=True)
await interaction.response.defer(ephemeral=False)  # 延遲回應
await interaction.response.edit_message(content="新內容")
await interaction.response.send_modal(modal)

# 後續回應
await interaction.followup.send("後續訊息")
await interaction.edit_original_response(content="編輯")
await interaction.delete_original_response()

# 檢查
interaction.response.is_done()  # 是否已回應
```

---

## Slash Command 參數類型

| Python 類型                              | Discord 類型          | 說明       |
| ---------------------------------------- | --------------------- | ---------- |
| `str`                                    | String                | 字串       |
| `int`                                    | Integer               | 整數       |
| `float`                                  | Number                | 浮點數     |
| `bool`                                   | Boolean               | 布林值     |
| `discord.User`                           | User                  | 使用者     |
| `discord.Member`                         | User                  | 伺服器成員 |
| `discord.Role`                           | Role                  | 角色       |
| `discord.TextChannel`                    | Channel               | 文字頻道   |
| `discord.VoiceChannel`                   | Channel               | 語音頻道   |
| `discord.CategoryChannel`                | Channel               | 分類頻道   |
| `discord.StageChannel`                   | Channel               | 舞台頻道   |
| `discord.Thread`                         | Channel               | 討論串     |
| `discord.Attachment`                     | Attachment            | 附件       |
| `Literal[...]`                           | String                | 選項列表   |
| `app_commands.Range[type, min, max]`     | Integer/Number/String | 範圍限制   |
| `app_commands.Transform[T, Transformer]` | -                     | 自訂轉換器 |

**注意**: 不支援 `*args` 或 `**kwargs`，所有參數必須明確定義

### 範例

```python
from typing import Literal
from discord import app_commands

@bot.tree.command()
@app_commands.describe(
    text="文字參數",
    number="數字參數",
    user="使用者"
)
async def example(
    interaction: discord.Interaction,
    text: str,
    number: app_commands.Range[int, 1, 100],
    user: discord.Member,
    choice: Literal["選項1", "選項2", "選項3"] = "選項1"
):
    await interaction.response.send_message(f"{text} {number} {user.mention} {choice}")
```

---

## 事件列表

### 連接事件

| 事件             | 參數       | 說明         |
| ---------------- | ---------- | ------------ |
| `on_ready`       | -          | Bot 就緒     |
| `on_connect`     | -          | 連接 Discord |
| `on_disconnect`  | -          | 斷線         |
| `on_resumed`     | -          | 恢復連接     |
| `on_shard_ready` | `shard_id` | 分片就緒     |

### 訊息事件

| 事件                     | 參數            | 說明         |
| ------------------------ | --------------- | ------------ |
| `on_message`             | `message`       | 收到訊息     |
| `on_message_edit`        | `before, after` | 訊息編輯     |
| `on_message_delete`      | `message`       | 訊息刪除     |
| `on_bulk_message_delete` | `messages`      | 批次刪除     |
| `on_raw_message_edit`    | `payload`       | 原始編輯事件 |
| `on_raw_message_delete`  | `payload`       | 原始刪除事件 |

### 成員事件

| 事件               | 參數            | 說明       |
| ------------------ | --------------- | ---------- |
| `on_member_join`   | `member`        | 成員加入   |
| `on_member_remove` | `member`        | 成員離開   |
| `on_member_update` | `before, after` | 成員更新   |
| `on_user_update`   | `before, after` | 使用者更新 |
| `on_member_ban`    | `guild, user`   | 成員被封禁 |
| `on_member_unban`  | `guild, user`   | 成員解封   |

### 伺服器事件

| 事件                   | 參數            | 說明       |
| ---------------------- | --------------- | ---------- |
| `on_guild_join`        | `guild`         | 加入伺服器 |
| `on_guild_remove`      | `guild`         | 離開伺服器 |
| `on_guild_update`      | `before, after` | 伺服器更新 |
| `on_guild_role_create` | `role`          | 角色建立   |
| `on_guild_role_delete` | `role`          | 角色刪除   |
| `on_guild_role_update` | `before, after` | 角色更新   |

### 反應事件

| 事件                     | 參數                 | 說明         |
| ------------------------ | -------------------- | ------------ |
| `on_reaction_add`        | `reaction, user`     | 新增反應     |
| `on_reaction_remove`     | `reaction, user`     | 移除反應     |
| `on_reaction_clear`      | `message, reactions` | 清除所有反應 |
| `on_raw_reaction_add`    | `payload`            | 原始新增反應 |
| `on_raw_reaction_remove` | `payload`            | 原始移除反應 |

### 語音事件

| 事件                    | 參數                    | 說明         |
| ----------------------- | ----------------------- | ------------ |
| `on_voice_state_update` | `member, before, after` | 語音狀態更新 |

### 互動事件

| 事件             | 參數          | 說明     |
| ---------------- | ------------- | -------- |
| `on_interaction` | `interaction` | 所有互動 |

---

## Tasks 定時任務

### 建立任務

```python
from discord.ext import tasks
from datetime import time, datetime

@tasks.loop(seconds=60)  # 每 60 秒
async def task1():
    pass

@tasks.loop(minutes=10)  # 每 10 分鐘
async def task2():
    pass

@tasks.loop(hours=1)  # 每 1 小時
async def task3():
    pass

@tasks.loop(time=time(hour=12, minute=0))  # 每天 12:00
async def task4():
    pass

@tasks.loop(count=5)  # 只執行 5 次
async def task5():
    pass
```

### 參數

| 參數        | 類型                                       | 說明                                    |
| ----------- | ------------------------------------------ | --------------------------------------- |
| `seconds`   | `float`                                    | 秒數間隔                                |
| `minutes`   | `float`                                    | 分鐘間隔                                |
| `hours`     | `float`                                    | 小時間隔                                |
| `time`      | `datetime.time \| Sequence[datetime.time]` | 每日執行時間（可指定多個時間）          |
| `count`     | `Optional[int]`                            | 執行次數限制（預設無限）                |
| `reconnect` | `bool`                                     | 是否啟用錯誤處理和重連邏輯（預設 True） |
| `name`      | `Optional[str]`                            | 任務內部名稱                            |

### 控制方法

```python
task.start(*args, **kwargs)  # 啟動任務
task.stop()                   # 完成當前迭代後停止
task.cancel()                 # 立即取消
task.restart(*args, **kwargs) # 重啟任務
task.is_running()            # 是否執行中
task.is_being_cancelled()    # 是否正在取消
task.failed()                # 內部任務是否失敗
task.get_task()              # 取得內部 asyncio.Task 或 None
task.change_interval(seconds=0, minutes=0, hours=0, time=...)  # 動態修改間隔
task.add_exception_type(*exceptions)    # 新增要處理的例外類型
task.remove_exception_type(*exceptions) # 移除例外類型
task.clear_exception_types()            # 清除所有已處理的例外
```

### 裝飾器

```python
@task.before_loop
async def before():
    """在循環開始執行前呼叫（每次啟動時）"""
    await bot.wait_until_ready()

@task.after_loop
async def after():
    """循環完成後呼叫（正常結束或被停止時）"""
    if task.is_being_cancelled():
        print("Task was cancelled")

@task.error
async def on_error(error: Exception):
    """任務遇到未處理異常時呼叫"""
    print(f"Task error: {error}")
```

---

## Checks 檢查裝飾器

### 前綴指令檢查

```python
from discord.ext import commands

@commands.is_owner()              # 擁有者
@commands.is_nsfw()               # NSFW 頻道
@commands.guild_only()            # 僅限伺服器
@commands.dm_only()               # 僅限私訊
@commands.has_role("角色名")       # 擁有角色
@commands.has_any_role("角色1", "角色2")  # 擁有任一角色
@commands.has_permissions(administrator=True)  # 擁有權限
@commands.bot_has_permissions(send_messages=True)  # Bot 擁有權限
@commands.cooldown(1, 60, commands.BucketType.user)  # 冷卻時間
```

### Slash Command 檢查

```python
from discord import app_commands

@app_commands.checks.has_permissions(administrator=True)
@app_commands.checks.bot_has_permissions(manage_messages=True)
@app_commands.checks.cooldown(1, 60)  # 每 60 秒 1 次
@app_commands.guild_only()            # 僅限伺服器
```

### 自訂檢查

```python
# 前綴指令
def is_mod():
    async def predicate(ctx: commands.Context):
        return ctx.author.guild_permissions.manage_messages
    return commands.check(predicate)

@bot.command()
@is_mod()
async def cmd(ctx: commands.Context):
    pass

# Slash Command
def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

@bot.tree.command()
@is_admin()
async def cmd(interaction: discord.Interaction):
    pass
```

---

## Embeds 嵌入訊息

### 建立

```python
embed = discord.Embed(
    title="標題",
    description="描述",
    color=discord.Color.blue(),  # 或 0x3498db
    url="https://example.com",
    timestamp=discord.utils.utcnow()
)
```

### 方法

| 方法                                          | 說明         |
| --------------------------------------------- | ------------ |
| `set_author(name, url, icon_url)`             | 設定作者     |
| `set_thumbnail(url)`                          | 設定縮圖     |
| `set_image(url)`                              | 設定大圖     |
| `set_footer(text, icon_url)`                  | 設定頁尾     |
| `add_field(name, value, inline)`              | 新增欄位     |
| `insert_field_at(index, name, value, inline)` | 插入欄位     |
| `clear_fields()`                              | 清除所有欄位 |
| `remove_field(index)`                         | 移除欄位     |
| `to_dict()`                                   | 轉為字典     |

### 限制

| 項目     | 限制      |
| -------- | --------- |
| 標題     | 256 字元  |
| 描述     | 4096 字元 |
| 欄位數量 | 25 個     |
| 欄位名稱 | 256 字元  |
| 欄位內容 | 1024 字元 |
| 頁尾     | 2048 字元 |
| 作者     | 256 字元  |
| 總字元數 | 6000 字元 |

---

## Views 互動元件

### 建立 View

```python
class MyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)  # 3 分鐘後失效

    async def on_timeout(self):
        """逾時處理"""
        pass

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        """錯誤處理"""
        pass
```

### Button 按鈕

```python
@discord.ui.button(
    label="按鈕",
    style=discord.ButtonStyle.primary,  # primary, secondary, success, danger, link
    custom_id="button_1",
    emoji="👍",
    disabled=False,
    row=0  # 0-4
)
async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
    await interaction.response.send_message("已點擊!", ephemeral=True)
```

### Select 選單

```python
@discord.ui.select(
    placeholder="選擇選項",
    min_values=1,
    max_values=3,
    options=[
        discord.SelectOption(label="選項 1", value="1", emoji="1️⃣", description="描述"),
        discord.SelectOption(label="選項 2", value="2", emoji="2️⃣"),
    ],
    row=1
)
async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
    await interaction.response.send_message(f"你選擇了: {', '.join(select.values)}")
```

### 動態按鈕

```python
class DynamicView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.Button(label="按鈕 1", custom_id="btn1"))
        self.add_item(discord.ui.Button(label="按鈕 2", custom_id="btn2"))

    @discord.ui.button(label="停用")
    async def disable_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
```

---

## Modal 表單

```python
class MyModal(discord.ui.Modal, title="表單標題"):
    name = discord.ui.TextInput(
        label="名稱",
        style=discord.TextStyle.short,  # short 或 paragraph
        placeholder="請輸入名稱",
        default="預設值",
        required=True,
        max_length=100,
        min_length=1
    )

    async def on_submit(self, interaction: discord.Interaction):
        """提交時"""
        await interaction.response.send_message(f"收到: {self.name.value}")

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """錯誤處理"""
        await interaction.response.send_message("發生錯誤", ephemeral=True)

# 使用
@bot.tree.command()
async def form(interaction: discord.Interaction):
    await interaction.response.send_modal(MyModal())
```

---

## Permissions 權限

### 權限列表

| 權限                       | 說明                |
| -------------------------- | ------------------- |
| `create_instant_invite`    | 建立邀請            |
| `kick_members`             | 踢出成員            |
| `ban_members`              | 封禁成員            |
| `administrator`            | 管理員              |
| `manage_channels`          | 管理頻道            |
| `manage_guild`             | 管理伺服器          |
| `add_reactions`            | 新增反應            |
| `view_audit_log`           | 查看審核日誌        |
| `priority_speaker`         | 優先發言            |
| `stream`                   | 直播                |
| `read_messages`            | 讀取訊息            |
| `send_messages`            | 發送訊息            |
| `send_tts_messages`        | 發送 TTS            |
| `manage_messages`          | 管理訊息            |
| `embed_links`              | 嵌入連結            |
| `attach_files`             | 附加檔案            |
| `read_message_history`     | 讀取歷史            |
| `mention_everyone`         | 提及所有人          |
| `use_external_emojis`      | 使用外部表情        |
| `connect`                  | 連接語音            |
| `speak`                    | 說話                |
| `mute_members`             | 靜音成員            |
| `deafen_members`           | 使成員聽不見        |
| `move_members`             | 移動成員            |
| `use_voice_activation`     | 使用語音啟動        |
| `change_nickname`          | 更改暱稱            |
| `manage_nicknames`         | 管理暱稱            |
| `manage_roles`             | 管理角色            |
| `manage_webhooks`          | 管理 Webhooks       |
| `manage_emojis`            | 管理表情            |
| `use_slash_commands`       | 使用斜線指令        |
| `request_to_speak`         | 請求發言            |
| `manage_threads`           | 管理討論串          |
| `create_public_threads`    | 建立公開討論串      |
| `create_private_threads`   | 建立私人討論串      |
| `use_external_stickers`    | 使用外部貼圖        |
| `send_messages_in_threads` | 在討論串發送訊息    |
| `moderate_members`         | 管理成員（timeout） |

### 使用範例

```python
# 檢查權限
if member.guild_permissions.administrator:
    print("是管理員")

# 頻道權限
perms = channel.permissions_for(member)
if perms.send_messages and perms.embed_links:
    await channel.send(embed=embed)

# 建立權限物件
perms = discord.Permissions(
    send_messages=True,
    manage_messages=True,
    read_message_history=True
)

# 修改角色權限
await role.edit(permissions=perms)
```

---

## 常見錯誤

### 前綴指令錯誤

| 錯誤                      | 說明           |
| ------------------------- | -------------- |
| `CommandNotFound`         | 指令不存在     |
| `MissingRequiredArgument` | 缺少參數       |
| `BadArgument`             | 參數類型錯誤   |
| `MissingPermissions`      | 使用者缺少權限 |
| `BotMissingPermissions`   | Bot 缺少權限   |
| `CommandOnCooldown`       | 冷卻中         |
| `CheckFailure`            | 檢查失敗       |
| `DisabledCommand`         | 指令已停用     |
| `NoPrivateMessage`        | 不可在私訊使用 |

### Slash Command 錯誤

| 錯誤                                    | 說明               |
| --------------------------------------- | ------------------ |
| `app_commands.AppCommandError`          | 基底錯誤類別       |
| `app_commands.CheckFailure`             | 檢查失敗           |
| `app_commands.MissingPermissions`       | 使用者缺少權限     |
| `app_commands.BotMissingPermissions`    | Bot 缺少權限       |
| `app_commands.MissingRole`              | 缺少角色           |
| `app_commands.MissingAnyRole`           | 缺少任一角色       |
| `app_commands.CommandOnCooldown`        | 冷卻中             |
| `app_commands.CommandInvokeError`       | 指令執行時發生錯誤 |
| `app_commands.TransformerError`         | 參數轉換錯誤       |
| `app_commands.CommandNotFound`          | 指令不存在         |
| `app_commands.CommandAlreadyRegistered` | 指令已註冊         |

### Discord 錯誤

| 錯誤                    | 說明           |
| ----------------------- | -------------- |
| `discord.Forbidden`     | 403 權限不足   |
| `discord.NotFound`      | 404 找不到資源 |
| `discord.HTTPException` | HTTP 錯誤      |
| `discord.LoginFailure`  | 登入失敗       |

---

## 工具函數

### discord.utils

```python
# 查找
discord.utils.find(predicate, iterable)  # 找到第一個符合條件的
discord.utils.get(iterable, **attrs)     # 依屬性查找

# 時間
discord.utils.utcnow()  # 當前 UTC 時間（datetime）
await discord.utils.sleep_until(when)  # 睡到指定時間

# Snowflake
discord.utils.snowflake_time(id)  # ID 轉時間
discord.utils.time_snowflake(datetime, high=False)  # 時間轉 ID

# 格式化
discord.utils.escape_markdown(text, as_needed=False, ignore_links=True)  # 跳脫 Markdown
discord.utils.escape_mentions(text)  # 跳脫提及
discord.utils.remove_markdown(text, ignore_links=True)  # 移除 Markdown

# OAuth
discord.utils.oauth_url(
    client_id,
    permissions=discord.Permissions.none(),
    guild=None,
    redirect_uri=None,
    scopes=('bot', 'applications.commands'),
    disable_guild_select=False
)  # 生成 OAuth 邀請連結
```

### 範例

```python
# 查找成員
member = discord.utils.get(guild.members, name="username")

# 查找角色
role = discord.utils.find(lambda r: r.name == "Moderator", guild.roles)

# 邀請連結
perms = discord.Permissions(administrator=True)
url = discord.utils.oauth_url(bot.user.id, permissions=perms)
```

---

## 顏色

```python
# 預設顏色
discord.Color.default()        # 0x000000 (黑色)
discord.Color.teal()          # 0x1abc9c
discord.Color.dark_teal()     # 0x11806a
discord.Color.brand_green()   # 0x57F287
discord.Color.green()         # 0x2ecc71
discord.Color.dark_green()    # 0x1f8b4c
discord.Color.blue()          # 0x3498db
discord.Color.dark_blue()     # 0x206694
discord.Color.purple()        # 0x9b59b6
discord.Color.dark_purple()   # 0x71368a
discord.Color.magenta()       # 0xe91e63
discord.Color.dark_magenta()  # 0xad1457
discord.Color.gold()          # 0xf1c40f
discord.Color.dark_gold()     # 0xc27c0e
discord.Color.orange()        # 0xe67e22
discord.Color.dark_orange()   # 0xa84300
discord.Color.brand_red()     # 0xED4245
discord.Color.red()           # 0xe74c3c
discord.Color.dark_red()      # 0x992d22
discord.Color.lighter_grey()  # 0x95a5a6
discord.Color.dark_grey()     # 0x607d8b
discord.Color.light_grey()    # 0x979c9f
discord.Color.darker_grey()   # 0x546e7a
discord.Color.og_blurple()    # 0x7289da (舊版)
discord.Color.blurple()       # 0x5865F2 (新版)
discord.Color.greyple()       # 0x99aab5
discord.Color.dark_theme()    # 0x313338
discord.Color.fuchsia()       # 0xEB459E
discord.Color.yellow()        # 0xFEE75C

# 自訂顏色
discord.Color(0x3498db)                # 16 進位整數
discord.Color.from_rgb(52, 152, 219)   # RGB (0-255)
discord.Color.from_hsv(h, s, v)        # HSV (0-1)
```
