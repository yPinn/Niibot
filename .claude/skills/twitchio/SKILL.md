---
name: twitchio
description: TwitchIO 3 Python 非同步函式庫 API 指南。用於 Twitch Bot 開發、EventSub 事件訂閱、聊天指令系統。當需要撰寫 TwitchIO 相關程式碼時自動套用。
allowed-tools: Read, Grep, Glob
---

# TwitchIO 3 API 指南

非同步 Python 函式庫，用於 Twitch Helix API 與 EventSub。無 IRC（2.x 的 IRC 已移除，聊天改走 EventSub）。

## 安裝與版本

```bash
pip install twitchio                 # 核心
pip install "twitchio[starlette]"    # 需要 Starlette web adapter（EventSub webhook / OAuth）時
```

| 項目 | 值 |
| ---- | -- |
| **函式庫版本** | **3.3.2**（此指南對應版本；Niibot 亦鎖此版） |
| 版本約束（專案） | `twitchio>=3.3.0,<4.0.0`（`backend/pyproject.toml`） |
| **Python** | `>=3.11`，官方測試 3.11 / 3.12 / 3.13；Niibot 用 **3.12** |
| 相依 | `aiohttp>=3.9.1,<4`；`[starlette]` extra 需 `starlette>=1.0.0` + `uvicorn` |
| 官方文件 | <https://twitchio.dev/en/stable/> |

> 3.3.0 為功能版，3.3.1 / 3.3.2 為 bugfix。**目前無 beta 分支需要區分**。

### 版本工具

```bash
python -m twitchio --version      # 印出 twitchio / aiohttp / starlette / OS 等除錯資訊
python -m twitchio --create-new   # 互動式產生 bot 樣板
```

---

## 核心架構

```
Client                     # HTTP + EventSub(websocket/webhook) + OAuth + token 管理
  └── Bot(Client)          # 加入 commands ext（指令、Component、prefix）
        └── AutoBot(Bot, AutoClient)   # 以 Conduit + Shard 管理 EventSub（多頻道/正式部署建議）
```

- **Client / Bot** — EventSub 走 WebSocket（`subscribe_websocket`）或 Webhook（`subscribe_webhook`）。
- **AutoClient / AutoBot** — EventSub 走 **Conduit**；用 `multi_subscribe()` 批次訂閱。Conduit 在 shard 離線後仍保留訂閱最長 72 小時，適合長駐多租戶 bot。

---

## Bot 基本結構（WebSocket EventSub）

```python
import asyncio
import logging

import twitchio
from twitchio import eventsub
from twitchio.ext import commands

LOGGER = logging.getLogger("Bot")


class MyBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            client_id="...",
            client_secret="...",
            bot_id="BOT_USER_ID",       # commands.Bot 上強烈建議（DCF 時才可省略）
            owner_id="OWNER_USER_ID",   # 選填
            prefix="!",                 # 必填，str / iterable[str] / coroutine
        )

    async def setup_hook(self) -> None:
        await self.add_component(MyComponent())
        # subscribe_websocket 在 Bot 上 as_bot 預設 True（用 bot 自己的 user token）
        await self.subscribe_websocket(
            eventsub.ChatMessageSubscription(
                broadcaster_user_id="CHANNEL_ID",
                user_id=self.bot_id,
            )
        )

    async def event_ready(self) -> None:
        LOGGER.info("Ready as %s", self.bot_id)


def main() -> None:
    twitchio.utils.setup_logging(level=logging.INFO)

    async def runner() -> None:
        async with MyBot() as bot:
            await bot.start()

    asyncio.run(runner())


main()
```

`bot.run()` 為阻塞式便利入口（內部做 `start()`）。

### AutoBot（Conduit）骨架

```python
class MyBot(commands.AutoBot):
    def __init__(self, subs: list[eventsub.SubscriptionPayload]) -> None:
        super().__init__(
            client_id="...",
            client_secret="...",
            bot_id="BOT_USER_ID",
            owner_id="OWNER_USER_ID",
            prefix="!",
            subscriptions=subs,   # 建立新 Conduit 時自動呼叫 multi_subscribe(subs)
            # conduit_id="..."    # 重用既有 Conduit（跨重啟保留訂閱）
        )

    async def setup_hook(self) -> None:
        await self.add_component(MyComponent())
        # 執行期再加訂閱：
        # resp = await self.multi_subscribe([sub])
        # resp.success / resp.errors
```

`AutoBot` 額外建構參數：`conduit_id`、`shard_ids`、`max_per_shard`、`subscriptions`、`force_subscribe`、`force_scale`。

---

## 生命週期

```python
await bot.login(token=None, load_tokens=True, save_tokens=True)  # 產生 app token、載入使用者 token
await bot.start()          # 非阻塞
bot.run()                  # 阻塞
await bot.close()          # 卸載 module/component 後關閉

# Device Code Flow（無 client_secret 的公開 app）
await bot.login_dcf(...)
await bot.start_dcf(...)
```

### 可覆寫鉤子

| 鉤子 | 時機 |
| ---- | ---- |
| `setup_hook()` | `login()` 後、`event_ready` 前 |
| `event_ready()` | 完成登入 |
| `before_invoke(ctx)` / `after_invoke(ctx)` | 每個指令前/後（Bot 層） |
| `event_command_error(payload)` | 指令錯誤（Bot 層，參數為 `CommandErrorPayload`） |
| `load_tokens(path)` / `save_tokens(path)` | 覆寫以改用 DB 儲存 token |

---

## 指令系統

### 基本指令

```python
@commands.command()                       # name=/aliases=/extras= 可選
async def hello(ctx: commands.Context) -> None:
    await ctx.reply(f"Hello {ctx.chatter.display_name}!")

@commands.command(aliases=["plus"])
async def add(ctx: commands.Context, a: int, b: int) -> None:
    await ctx.reply(f"{a + b}")

@commands.command()
async def echo(ctx: commands.Context, *, msg: str) -> None:   # 吃到行尾
    await ctx.send(msg)
```

### 指令群組

```python
@commands.group(invoke_fallback=True)
async def config(ctx: commands.Context) -> None:
    # 無匹配 subcommand 時才跑（invoke_fallback=True）；有 subcommand 時此 callback 不執行
    await ctx.reply("用法: !config show | !config set <key> <value>")

@config.command()
async def show(ctx: commands.Context) -> None:
    await ctx.reply("...")
```

> 有匹配 subcommand 時，group callback **完全不執行**。group 內的 early-return / guard 對 subcommand **無效**——每個 subcommand 需自行守衛，或用 Component-level guard。

### Context 常用成員

| 成員 | 類型 | 說明 |
| ---- | ---- | ---- |
| `ctx.chatter` / `ctx.author` | `Chatter \| PartialUser` | 發送者（alias） |
| `ctx.broadcaster` / `ctx.channel` | `PartialUser` | 頻道主（alias） |
| `ctx.source_broadcaster` | `PartialUser \| None` | Shared Chat 來源頻道 |
| `ctx.message` | `ChatMessage \| None` | 原始訊息（reward context 為 None） |
| `ctx.redemption` | `ChannelPointsRedemptionAdd/Update \| None` | reward context |
| `ctx.payload` | `ChatMessage \| ChannelPointsRedemption*` | message 或 redemption |
| `ctx.command` / `ctx.component` | — | 目前指令 / 所屬 Component |
| `ctx.invoked_subcommand` | `Command \| None` | 已匹配的 subcommand |
| `ctx.invoked_with` / `ctx.subcommand_trigger` | `str \| None` | 觸發用的字串 |
| `ctx.prefix` / `ctx.content` | `str` | 前綴 / 訊息內容 |
| `ctx.args` / `ctx.kwargs` | — | 解析後參數 |
| `ctx.type` | `ContextType` | `MESSAGE` \| `REWARD` |
| `ctx.is_owner()` | `bool` | chatter 是否為 `bot.owner_id` |
| `await ctx.send(content, *, me=False)` | `SentMessage` | 發送 |
| `await ctx.reply(content, *, me=False)` | `SentMessage` | 回覆 |
| `await ctx.send_announcement(content, *, color=None)` | — | 需 `moderator:manage:announcements` |
| `await ctx.delete_message()` | — | reward context 不可用 |

### Chatter 角色屬性（3.3.x）

`Chatter` 繼承 `PartialUser`（有 `.id` / `.name` / `.display_name`），並依徽章提供布林屬性——**無 `is_` 前綴**：

| 屬性 | 說明 |
| ---- | ---- |
| `chatter.broadcaster` | 頻道主 |
| `chatter.moderator` | mod；**回傳 True 也涵蓋 lead moderator 與 broadcaster** |
| `chatter.lead_moderator` | lead mod（也涵蓋 broadcaster） |
| `chatter.vip` | VIP（Twitch 限制：mod/broadcaster 不會同時是 VIP） |
| `chatter.subscriber` / `chatter.founder` | 訂閱者 / 創始訂閱 |
| `chatter.staff` / `chatter.admin` / `chatter.partner` | Twitch 官方身分 |
| `chatter.turbo` / `chatter.prime` | Turbo / Prime |
| `chatter.artist` | 頻道 artist |
| `chatter.no_audio` / `chatter.no_video` | 觀看時無音訊 / 無視訊 |
| `chatter.colour` (`.color`) | `Colour \| None` |
| `chatter.badges` | `list[ChatMessageBadge]` |

> 舊指南曾稱「3.3.0b 改名 `.is_moderator`」——**此事未發生**，正式版仍是 `.moderator` 等。
> `commands.is_moderator()` 之類是**守衛裝飾器工廠**（見下），與 Chatter 屬性無關。

### 守衛

```python
# 自訂守衛
def owner_only():
    def predicate(ctx: commands.Context) -> bool:
        return ctx.chatter.id == ctx.bot.owner_id
    return commands.guard(predicate)

@owner_only()
@commands.command()
async def shutdown(ctx: commands.Context) -> None: ...

# 內建守衛（皆為裝飾器工廠；失敗拋 GuardFailure）
commands.is_owner()          # chatter.id == bot.owner_id
commands.is_broadcaster()    # chatter.id == broadcaster.id
commands.is_moderator()      # chatter.moderator（含 lead mod / broadcaster）
commands.is_lead_moderator()
commands.is_vip()
commands.is_staff()
commands.is_elevated()       # broadcaster / moderator / VIP 任一即可
```

> `is_staff` / `is_moderator` / `is_lead_moderator` / `is_vip` / `is_elevated` **不可**用於 `RewardCommand`（會恆為失敗）。

### 冷卻

```python
@commands.cooldown(rate=2, per=10, key=commands.BucketType.chatter)
@commands.command()
async def spammy(ctx: commands.Context) -> None: ...
```

`BucketType`：`default`（全域）、`user`（跨頻道每人）、`channel`（每頻道所有人）、`chatter`（每頻道每人）。超過拋 `CommandOnCooldown`。

---

## Component 元件

```python
class MyComponent(commands.Component):
    # 不呼叫 super().__init__()

    async def component_load(self) -> None: ...       # 載入（async 初始化）
    async def component_teardown(self) -> None: ...   # 卸載（清理資源）

    @commands.command()
    async def ping(self, ctx: commands.Context) -> None:
        await ctx.reply("Pong!")

    @commands.Component.listener()                    # 也可 listener("event_message")
    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        print(f"{payload.chatter.name}: {payload.text}")

    @commands.Component.guard()                       # sync 或 async；回傳非 True → 阻擋整個 Component
    def _is_mod(self, ctx: commands.Context) -> bool:
        return ctx.chatter.moderator

    async def component_command_error(
        self, payload: commands.CommandErrorPayload
    ) -> bool | None:
        error, ctx = payload.exception, payload.context
        if isinstance(error, commands.GuardFailure):
            await ctx.reply("No permission")
            return False        # False = 不再往 Bot 層傳
        return None             # None = 繼續往上傳
```

### 生命週期鉤子

| 方法 | 時機 |
| ---- | ---- |
| `component_load()` / `component_teardown()` | 載入 / 卸載 |
| `component_before_invoke(ctx)` / `component_after_invoke(ctx)` | 每個指令前 / 後 |
| `component_command_error(payload: CommandErrorPayload)` | Component 內指令錯誤 |

### Bot 上的管理方法

```python
await bot.add_component(component)      # bot.remove_component / bot.get_component
await bot.load_module("pkg.mod")        # 模組需有 setup(bot) entry point
await bot.reload_module("pkg.mod")      # bot.unload_module
bot.components   # dict[str, Component]
bot.modules      # dict[str, ModuleType]
```

---

## EventSub

### 訂閱

```python
# WebSocket（Client / Bot）— Bot 上 as_bot 預設 True
await bot.subscribe_websocket(subscription, *, as_bot=None, token_for=None, socket_id=None)

# Webhook（需公開 HTTPS + web adapter）
await bot.subscribe_webhook(subscription, callback_url="https://...", eventsub_secret="...")

# Conduit 批次（AutoClient / AutoBot）
resp = await bot.multi_subscribe(subs, *, wait=True, stop_on_error=False)
resp.success     # list[MultiSubscribeSuccess] — 每項 .response 為 Twitch 原始回應
                 #   {"data": [{"id": ...}]}；訂閱 id 在 resp.success[i].response["data"][0]["id"]
resp.errors      # list[MultiSubscribeError]
```

### 管理

```python
subs = await bot.fetch_eventsub_subscriptions()
await bot.delete_eventsub_subscription(sub_id)
await bot.delete_all_eventsub_subscriptions()
```

### 常用訂閱類型（`twitchio.eventsub`）

| 類型 | 主要參數 |
| ---- | -------- |
| `ChatMessageSubscription` | `broadcaster_user_id`, `user_id` |
| `ChatNotificationSubscription` | `broadcaster_user_id`, `user_id` |
| `ChatMessageDeleteSubscription` / `ChatClearSubscription` | `broadcaster_user_id`, `user_id` |
| `StreamOnlineSubscription` / `StreamOfflineSubscription` | `broadcaster_user_id` |
| `ChannelUpdateSubscription` | `broadcaster_user_id` |
| `ChannelFollowSubscription` | `broadcaster_user_id`, `moderator_user_id` |
| `ChannelSubscribeSubscription` | `broadcaster_user_id` |
| `ChannelSubscriptionGiftSubscription` / `ChannelSubscribeMessageSubscription` / `ChannelSubscriptionEndSubscription` | `broadcaster_user_id` |
| `ChannelCheerSubscription` | `broadcaster_user_id` |
| `ChannelRaidSubscription` | `to_broadcaster_user_id` 或 `from_broadcaster_user_id` |
| `ChannelBanSubscription` / `ChannelUnbanSubscription` | `broadcaster_user_id` |
| `ChannelModeratorAddSubscription` / `ChannelModeratorRemoveSubscription` | `broadcaster_user_id` |
| `ChannelVIPAddSubscription` / `ChannelVIPRemoveSubscription` | `broadcaster_user_id` |
| `ChannelPointsRewardAddSubscription` / `...RewardUpdateSubscription` / `...RewardRemoveSubscription` | `broadcaster_user_id` |
| `ChannelPointsRedeemAddSubscription` / `ChannelPointsRedeemUpdateSubscription` | `broadcaster_user_id`（+ 可選 `reward_id`） |
| `ChannelPointsAutoRedeemSubscription` / `...AutoRedeemV2Subscription` | `broadcaster_user_id` |
| `CustomPowerupRedeemAddSubscription` | `broadcaster_user_id` |
| `SharedChatSessionBeginSubscription` / `...UpdateSubscription` / `...EndSubscription` | `broadcaster_user_id` |

> **命名陷阱**：訂閱類是 `ChannelPointsRedeem*Subscription`（Redeem，非 Redemption）。
> 對應的**事件**卻是 `event_custom_redemption_add`、payload 為 `ChannelPointsRedemptionAdd`。

### 事件監聽

事件可在 Component（`@commands.Component.listener()`）或 Bot 子類（直接 `async def event_x`）中定義。
所有 EventSub payload 皆為 stateful 物件——使用者以 `PartialUser` 呈現（有 `.id` / `.name`），不是扁平字串（2.x 差異）。

```python
@commands.Component.listener()
async def event_message(self, payload: twitchio.ChatMessage) -> None:
    print(payload.text, payload.chatter.name, payload.broadcaster.id)

@commands.Component.listener()
async def event_follow(self, payload: twitchio.ChannelFollow) -> None:
    print(f"{payload.user.name} followed")

@commands.Component.listener()
async def event_raid(self, payload: twitchio.ChannelRaid) -> None:
    # payload.from_broadcaster = 發起 raid 的頻道；payload.to_broadcaster = 被 raid 的頻道
    print(f"{payload.from_broadcaster.name} raided ({payload.viewer_count})")

@commands.Component.listener()
async def event_stream_online(self, payload: twitchio.StreamOnline) -> None:
    # payload.broadcaster (PartialUser), payload.type
    #   ("live" | "playlist" | "watch_party" | "premiere" | "rerun"), payload.started_at
    ...

@commands.Component.listener()
async def event_stream_offline(self, payload: twitchio.StreamOffline) -> None:
    # 只有 payload.broadcaster
    ...
```

完整事件 ↔ payload 對照見 [reference.md](reference.md)。

---

## 資料查詢

```python
# 使用者 / 頻道
users = await bot.fetch_users(ids=["1", "2"], logins=["foo"])
channels = await bot.fetch_channels(broadcaster_ids=["123"])

# 是否開台：優先用 PartialUser.fetch_stream()（單數、可 await、回傳 Stream | None）
partial = bot.create_partialuser("123")            # 或事件裡的 payload.broadcaster
stream = await partial.fetch_stream()
if stream:
    print(stream.title, stream.viewer_count, stream.game_name)

# fetch_streams 回傳 HTTPAsyncIterator（不可 await，必須 async for）
async for s in bot.fetch_streams(user_ids=["123"]):
    print(s.title)

# 遊戲 / clips
game = await bot.fetch_game(name="...")
async for clip in partial.fetch_clips():
    print(clip.title)
```

> `token_for=None`（3.3.0 起）在多數 Helix 方法上代表明確使用預設 app token。

---

## 傳訊 / Shoutout（用模型方法，勿戳 `bot._http`）

```python
# 3.3.0 起 bot.http 為公開 property；但一般用 PartialUser 方法即可
await broadcaster.send_message(message="hi", sender=bot.bot_id, reply_to_message_id=None, pin=False)
await broadcaster.send_announcement(moderator=bot.bot_id, message="...", color="green")
await broadcaster.send_shoutout(to_broadcaster=target_id, moderator=bot.bot_id)
```

---

## Routines 定時任務

```python
from datetime import timedelta
from twitchio.ext import routines

@routines.routine(delta=timedelta(minutes=10), wait_first=False)
async def announce() -> None:
    ...

@announce.error
async def _on_error(error: Exception) -> None:
    ...

announce.start()   # 回傳 asyncio.Task；start(*args, **kwargs) 會轉傳給 callback
announce.stop()    # 跑完當前迭代後停止
announce.cancel()  # 立即取消
announce.change_interval(delta=timedelta(minutes=5))
```

`@routines.routine` 參數：`delta` **或** `time`（互斥、擇一必填）、`name`、`iterations`、`wait_first`、`wait_remainder`、`max_attempts`（預設 5）、`stop_on_error`。
生命週期鉤子：`@r.before_routine`、`@r.after_routine`、`@r.error`。

---

## Token 管理

```python
await bot.add_token(token="...", refresh="...")   # 回傳 ValidateTokenPayload
await bot.remove_token(user_id)                   # 回傳 TokenMappingData | None
await bot.load_tokens(path=None)                  # 預設檔 .tio.tokens.json
await bot.save_tokens(path=None)
bot.tokens                                        # 目前管理中的 token 映射

@commands.Component.listener()  # 或 Bot 子類
async def event_token_refreshed(self, payload: twitchio.TokenRefreshedPayload) -> None:
    ...   # 持久化更新後的 token
```

自訂儲存：覆寫 `load_tokens` / `save_tokens`，在其中呼叫 `add_token`（見 [examples.md](examples.md)）。

---

## Scopes

```python
import twitchio

scopes = twitchio.Scopes(["channel:bot", "user:bot", "moderator:manage:shoutouts"])
scopes = twitchio.Scopes.all()
scopes = twitchio.Scopes.from_url("https://id.twitch.tv/oauth2/authorize?...&scope=...")
scopes.selected   # list[str]
```

---

## 常見指令例外（`twitchio.ext.commands`）

| 例外 | 說明 |
| ---- | ---- |
| `CommandNotFound` | 指令不存在 |
| `MissingRequiredArgument` | 缺少必要參數 |
| `BadArgument` / `ConversionError` / `ArgumentError` | 參數轉換失敗 |
| `GuardFailure` | 守衛未通過 |
| `CommandOnCooldown` | 冷卻中 |
| `CommandInvokeError` / `CommandHookError` | callback / 鉤子內部拋錯 |
| `CommandExistsError` | 重複註冊指令 |
| `ModuleLoadFailure` / `ModuleAlreadyLoadedError` / `NoEntryPointError` | 模組載入問題 |

HTTP 層錯誤為 `twitchio.HTTPException`；認證為 `twitchio.exceptions` 內的類別。

---

## 相關檔案

- [reference.md](reference.md) — 詳細 API 表（建構參數、事件對照、payload 屬性）
- [examples.md](examples.md) — 完整程式碼範例

## 官方資源

- 文件：<https://twitchio.dev/en/stable/>
- 遷移指南（2.x → 3.x）：<https://twitchio.dev/en/stable/getting-started/migrating.html>
- 更新紀錄：<https://twitchio.dev/en/stable/getting-started/changelog.html>
- GitHub：<https://github.com/PythonistaGuild/TwitchIO>
