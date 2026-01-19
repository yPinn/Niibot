---
name: twitchio
description: TwitchIO 3 Python 非同步函式庫 API 指南。用於 Twitch Bot 開發、EventSub 事件訂閱、聊天指令系統。當需要撰寫 TwitchIO 相關程式碼時自動套用。
allowed-tools: Read, Grep, Glob
---

# TwitchIO 3 API 指南

非同步 Python 函式庫，用於 Twitch API 與 EventSub。

## 安裝

```bash
pip install twitchio
```

**最新版本**: 3.1.0 (2025)
**Python 版本要求**: 3.11+（支援 3.11、3.12、3.13）

---

## 核心架構

```
Client          # 基礎 HTTP/EventSub/OAuth
  └── Bot       # 加入指令系統
      └── AutoBot  # 自動 Token 管理
```

---

## Bot 基本結構

```python
import twitchio
from twitchio.ext import commands, eventsub

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            client_id="...",
            client_secret="...",
            bot_id="BOT_USER_ID",      # 必填
            owner_id="OWNER_USER_ID",  # 選填
            prefix="!"
        )

    async def setup_hook(self):
        # 載入元件
        await self.add_component(MyComponent())
        # 訂閱事件
        await self.subscribe_websocket(
            eventsub.ChatMessageSubscription(
                broadcaster_user_id="CHANNEL_ID",
                user_id=self.bot_id
            )
        )

bot = MyBot()
bot.run()
```

---

## 指令系統

### 基本指令

```python
@commands.command()
async def hello(ctx: commands.Context):
    await ctx.reply(f"Hello {ctx.author.display_name}!")

@commands.command()
async def add(ctx: commands.Context, a: int, b: int):
    await ctx.reply(f"{a + b}")
```

### 指令群組

```python
@commands.group()
async def set(ctx: commands.Context):
    if ctx.invoked_subcommand is None:
        await ctx.reply("用法: !set <subcommand>")

@set.command()
async def prefix(ctx: commands.Context, new: str):
    await ctx.reply(f"前綴: {new}")
```

### Context 常用屬性

| 屬性             | 說明             |
| ---------------- | ---------------- |
| `ctx.author`     | 發送者 (Chatter) |
| `ctx.channel`    | 頻道             |
| `ctx.message`    | 原始訊息         |
| `ctx.send(msg)`  | 發送訊息         |
| `ctx.reply(msg)` | 回覆訊息         |

---

## Component 元件

```python
class MyComponent(commands.Component):
    # 不呼叫 super().__init__()

    async def component_load(self):
        """載入時"""

    async def component_teardown(self):
        """卸載時"""

    @commands.command()
    async def ping(self, ctx: commands.Context):
        await ctx.reply("Pong!")

    @commands.Component.listener()
    async def event_message(self, payload: twitchio.ChatMessage):
        print(f"{payload.chatter.name}: {payload.text}")
```

### 生命週期

| 方法                                  | 時機   |
| ------------------------------------- | ------ |
| `component_load()`                    | 載入   |
| `component_teardown()`                | 卸載   |
| `component_before_invoke(ctx)`        | 指令前 |
| `component_after_invoke(ctx)`         | 指令後 |
| `component_command_error(ctx, error)` | 錯誤   |

### 元件守衛

```python
@commands.Component.guard()
async def check(self, ctx: commands.Context) -> bool:
    return ctx.author.is_mod  # False 阻止執行
```

---

## EventSub 訂閱

### 訂閱方式

```python
# WebSocket（推薦聊天用）
await bot.subscribe_websocket(subscription)

# Webhook（需公開 HTTPS）
await bot.subscribe_webhook(subscription, callback_url="...")
```

### 常用訂閱類型

| 類型                           | 參數                                   |
| ------------------------------ | -------------------------------------- |
| `ChatMessageSubscription`      | broadcaster_user_id, user_id           |
| `ChannelFollowSubscription`    | broadcaster_user_id, moderator_user_id |
| `ChannelSubscribeSubscription` | broadcaster_user_id                    |
| `ChannelCheerSubscription`     | broadcaster_user_id                    |
| `ChannelRaidSubscription`      | to_broadcaster_user_id                 |
| `StreamOnlineSubscription`     | broadcaster_user_id                    |
| `StreamOfflineSubscription`    | broadcaster_user_id                    |

### 事件監聽

```python
@commands.Component.listener()
async def event_message(self, payload: twitchio.ChatMessage):
    print(payload.text)

@commands.Component.listener()
async def event_follow(self, payload: twitchio.ChannelFollow):
    print(f"{payload.user.name} followed!")
```

---

## Routines 定時任務

```python
from twitchio.ext import routines
from datetime import timedelta

@routines.routine(delta=timedelta(minutes=10))
async def task():
    print("執行")

task.start()   # 啟動
task.stop()    # 停止
task.cancel()  # 取消
```

### 參數

| 參數         | 說明                     |
| ------------ | ------------------------ |
| `delta`      | 間隔 (timedelta)         |
| `time`       | 每日時間 (datetime.time) |
| `iterations` | 次數限制                 |
| `wait_first` | 首次前等待               |

---

## Token 管理

```python
await bot.add_token(token="...", refresh="...")
await bot.remove_token(user_id="...")
await bot.save_tokens()  # 預設 .tio.tokens.json
await bot.load_tokens()
```

---

## 資料查詢

```python
user = await bot.fetch_user(user_id="123")
channel = await bot.fetch_channel(broadcaster_id="123")

async for stream in bot.fetch_streams(user_ids=["123"]):
    print(stream.title)
```

---

## 相關檔案

- [reference.md](reference.md) - 完整 API
- [examples.md](examples.md) - 程式碼範例

## 官方資源

- [文件](https://twitchio.dev/)
- [GitHub](https://github.com/PythonistaGuild/TwitchIO)
