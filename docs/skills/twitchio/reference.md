# TwitchIO 3 API 參考

**版本**: 3.1.0 (2025-08-10)
**Python 要求**: 3.11+（支援 3.11、3.12、3.13）

## Client 建構參數

| 參數            | 類型     | 必填 | 說明                    |
| --------------- | -------- | :--: | ----------------------- |
| `client_id`     | `str`    |  ✓   | Twitch App ID           |
| `client_secret` | `str`    |  ✓   | Twitch App Secret       |
| `bot_id`        | `str`    |  -   | Bot User ID（強烈建議） |
| `redirect_uri`  | `str`    |  -   | OAuth 回調 URL          |
| `scopes`        | `Scopes` |  -   | OAuth 權限              |

## Bot 額外參數

| 參數       | 類型          | 說明      |
| ---------- | ------------- | --------- |
| `bot_id`   | `str`         | **必填**  |
| `owner_id` | `str`         | 擁有者 ID |
| `prefix`   | `str \| list` | 指令前綴  |

---

## 生命週期方法

```python
await bot.login()   # 初始化 Token
await bot.start()   # 啟動（非阻塞）
bot.run()           # 啟動（阻塞）
await bot.close()   # 關閉
```

### 覆寫鉤子

```python
async def setup_hook(self):
    """login 後、ready 前"""

async def before_invoke(self, ctx):
    """每個指令前"""

async def after_invoke(self, ctx):
    """每個指令後"""

async def event_command_error(self, payload):
    """指令錯誤"""
```

---

## 指令管理

```python
bot.add_command(cmd)
bot.get_command("name")
bot.remove_command("name")
```

## 元件管理

```python
await bot.add_component(component)
await bot.remove_component(component)
bot.get_component(ComponentClass)
```

## 模組管理

```python
await bot.load_module("path.to.module")
await bot.unload_module("path.to.module")
await bot.reload_module("path.to.module")
```

---

## EventSub 方法

```python
# 訂閱
await bot.subscribe_websocket(subscription)
await bot.subscribe_webhook(subscription, callback_url="...")

# 管理
subs = await bot.fetch_eventsub_subscriptions()
await bot.delete_eventsub_subscription(sub_id)
await bot.delete_all_eventsub_subscriptions()
```

---

## EventSub 訂閱類型

### 聊天

| 類型                            | 參數                         |
| ------------------------------- | ---------------------------- |
| `ChatMessageSubscription`       | broadcaster_user_id, user_id |
| `ChatNotificationSubscription`  | broadcaster_user_id, user_id |
| `ChatMessageDeleteSubscription` | broadcaster_user_id, user_id |
| `ChatClearSubscription`         | broadcaster_user_id, user_id |

### 頻道

| 類型                                  | 參數                                   |
| ------------------------------------- | -------------------------------------- |
| `ChannelUpdateSubscription`           | broadcaster_user_id                    |
| `ChannelFollowSubscription`           | broadcaster_user_id, moderator_user_id |
| `ChannelSubscribeSubscription`        | broadcaster_user_id                    |
| `ChannelSubscriptionGiftSubscription` | broadcaster_user_id                    |
| `ChannelCheerSubscription`            | broadcaster_user_id                    |
| `ChannelRaidSubscription`             | to_broadcaster_user_id                 |
| `ChannelBanSubscription`              | broadcaster_user_id                    |
| `ChannelUnbanSubscription`            | broadcaster_user_id                    |

### 頻道點數

| 類型                                     | 參數                |
| ---------------------------------------- | ------------------- |
| `ChannelPointsRewardAddSubscription`     | broadcaster_user_id |
| `ChannelPointsRedemptionAddSubscription` | broadcaster_user_id |

### 直播狀態

| 類型                        | 參數                |
| --------------------------- | ------------------- |
| `StreamOnlineSubscription`  | broadcaster_user_id |
| `StreamOfflineSubscription` | broadcaster_user_id |

---

## 事件名稱對照

| 事件                          | Payload 類型                 |
| ----------------------------- | ---------------------------- |
| `event_ready`                 | -                            |
| `event_message`               | `ChatMessage`                |
| `event_follow`                | `ChannelFollow`              |
| `event_subscription`          | `ChannelSubscribe`           |
| `event_subscription_gift`     | `ChannelSubscriptionGift`    |
| `event_cheer`                 | `ChannelCheer`               |
| `event_raid`                  | `ChannelRaid`                |
| `event_ban`                   | `ChannelBan`                 |
| `event_unban`                 | `ChannelUnban`               |
| `event_stream_online`         | `StreamOnline`               |
| `event_stream_offline`        | `StreamOffline`              |
| `event_custom_redemption_add` | `ChannelPointsRedemptionAdd` |

---

## Token 管理

```python
await bot.add_token(token="...", refresh="...")
await bot.remove_token(user_id="...")
await bot.load_tokens(path=None)   # 預設 .tio.tokens.json
await bot.save_tokens(path=None)
```

### 自訂儲存（覆寫）

```python
async def load_tokens(self, path=None):
    # 從 DB 讀取
    async for row in db.execute("SELECT ..."):
        await self.add_token(token=row[0], refresh=row[1])

async def save_tokens(self, path=None):
    # 寫入 DB
    for uid, data in self.tokens.items():
        await db.execute("INSERT ...", (uid, data.token, data.refresh))
```

---

## 資料查詢

```python
# 用戶
user = await bot.fetch_user(user_id="...")
user = await bot.fetch_user(user_login="...")
users = await bot.fetch_users(user_ids=[...])

# 頻道
channel = await bot.fetch_channel(broadcaster_id="...")

# 串流（非同步迭代器）
async for stream in bot.fetch_streams(user_ids=[...]):
    print(stream.title, stream.viewer_count)

# Clips
async for clip in bot.fetch_clips(broadcaster_id="..."):
    print(clip.title)

# 遊戲
game = await bot.fetch_game(game_id="...")
async for game in bot.fetch_top_games():
    print(game.name)

# 表情/徽章
emotes = await bot.fetch_emotes()
badges = await bot.fetch_badges()
```

---

## Routines 參數

| 參數             | 類型            | 說明                      |
| ---------------- | --------------- | ------------------------- |
| `delta`          | `timedelta`     | 執行間隔                  |
| `time`           | `datetime.time` | 每日時間（與 delta 互斥） |
| `iterations`     | `int`           | 次數限制                  |
| `wait_first`     | `bool`          | 首次前等待（預設 False）  |
| `wait_remainder` | `bool`          | 只等剩餘時間              |
| `max_attempts`   | `int`           | 錯誤次數上限（預設 5）    |
| `stop_on_error`  | `bool`          | 遇錯停止                  |

### 控制方法

```python
routine.start(*args, **kwargs)  # 啟動
routine.stop()                   # 完成當前後停止
routine.cancel()                 # 立即取消
routine.restart(force=True)      # 重啟
routine.change_interval(delta=timedelta(...))  # 動態修改
```

### 生命週期鉤子

```python
@my_routine.before_routine
async def before(): ...

@my_routine.after_routine
async def after(): ...

@my_routine.error
async def on_error(error): ...
```

---

## 常見錯誤

| 錯誤                      | 說明         |
| ------------------------- | ------------ |
| `CommandNotFound`         | 指令不存在   |
| `MissingRequiredArgument` | 缺少參數     |
| `BadArgument`             | 參數類型錯誤 |
| `GuardFailure`            | 守衛檢查失敗 |
| `AuthenticationError`     | 認證失敗     |
| `HTTPException`           | HTTP 錯誤    |
