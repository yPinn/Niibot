# TwitchIO 3 官方 API 使用指南

本文檔說明專案中如何正確使用 TwitchIO 3 的官方 API。

## 目錄
- [PartialUser API](#partialuser-api)
- [ChatMessage API](#chatmessage-api)
- [EventSub Payload API](#eventsub-payload-api)
- [Context API](#context-api)
- [常見錯誤與修正](#常見錯誤與修正)

---

## PartialUser API

`PartialUser` 是 TwitchIO 3 中表示用戶/頻道的核心類別。

### 官方屬性

```python
# ✅ 正確用法
user.id              # str | int - 用戶 ID
user.name            # str | None - 用戶名（登入名）
user.display_name    # str | None - 顯示名稱
user.mention         # str - @mention 格式
```

### 常見使用場景

#### 1. 獲取頻道 ID
```python
# ✅ 正確 - 直接使用 .id
streams = await ctx.bot.fetch_streams(user_ids=[ctx.channel.id])

# ❌ 錯誤 - 使用不存在的屬性
channel_id = getattr(ctx.channel, 'user_id', ctx.channel.name)
```

#### 2. 檢查用戶身份
```python
# ✅ 正確 - 直接比較 .id
if ctx.chatter.id == ctx.channel.id:
    # 這是頻道擁有者

if ctx.chatter.id == ctx.bot.owner_id:
    # 這是 Bot Owner

# ❌ 錯誤 - 使用不存在的屬性
if ctx.chatter.id == ctx.channel.user_id:  # user_id 不存在！
```

#### 3. 發送訊息
```python
# ✅ 正確 - 使用 PartialUser.send_message()
broadcaster = payload.broadcaster  # PartialUser
await broadcaster.send_message(
    message="Hello!",
    sender=self.bot.bot_id,
    token_for=self.bot.bot_id
)
```

#### 4. 發送私訊 (Whisper)
```python
# ✅ 正確 - 從 Bot 發送 whisper 給用戶
# 創建發送者（Bot）的 PartialUser
bot_user = bot.create_partialuser(user_id=bot.bot_id)
await bot_user.send_whisper(
    to_user=recipient_user,  # 接收者的 PartialUser
    message="這是私訊"
)

# ❌ 錯誤 1 - 使用私有 API
await self.bot._http.post_whisper(...)  # 不要使用 _http！

# ❌ 錯誤 2 - 接收者發給接收者（會導致 400 錯誤）
recipient = bot.create_partialuser(user_id=user_id)
await recipient.send_whisper(to_user=recipient)  # 不能給自己發私訊！
```

### 參考資料
- [PartialUser 官方文檔](https://twitchio.dev/en/latest/references/users/partialuser.html)

---

## ChatMessage API

`ChatMessage` 是 EventSub 聊天訊息事件的 payload。

### 官方屬性

```python
payload.broadcaster       # PartialUser - 接收訊息的頻道
payload.chatter          # PartialUser - 發送訊息的用戶
payload.text             # str - 訊息內容
payload.source_broadcaster  # PartialUser | None - 共享聊天來源頻道
payload.source_id        # str | None - 來源訊息 ID
payload.cheer            # ChatMessageCheer | None - Cheer 資訊
payload.channel_points_id  # str | None - 點數兌換 ID
```

### 常見使用場景

#### 訊息記錄
```python
# ✅ 正確 - 使用 .broadcaster
async def event_message(self, payload: twitchio.ChatMessage) -> None:
    if payload.broadcaster:
        LOGGER.debug(
            f"[{payload.chatter.name}#{payload.broadcaster.name}]: {payload.text}"
        )

# ❌ 錯誤 - 使用不存在的屬性
channel_name = getattr(payload, 'channel', None)  # 'channel' 不存在！
```

### 參考資料
- [ChatMessage 官方文檔](https://twitchio.dev/en/latest/references/eventsub/eventsub_models.html)

---

## EventSub Payload API

### ChannelPointsRedemptionAdd

頻道點數兌換事件。

```python
# 官方屬性
payload.user             # PartialUser - 兌換用戶
payload.broadcaster      # PartialUser - 頻道擁有者
payload.reward          # 獎勵資訊
payload.reward.title    # str - 獎勵標題
payload.reward.cost     # int - 獎勵花費
payload.user_input      # str | None - 用戶輸入
payload.id              # str - 兌換 ID
payload.status          # str - 兌換狀態
```

#### 使用範例
```python
@commands.Component.listener()
async def event_custom_redemption_add(
    self,
    payload: twitchio.ChannelPointsRedemptionAdd
) -> None:
    # ✅ 正確 - 直接使用官方屬性
    user_name = payload.user.name
    reward_title = payload.reward.title
    broadcaster = payload.broadcaster

    LOGGER.info(
        f"{user_name} 在 {broadcaster.name} 頻道兌換了「{reward_title}」"
    )
```

### UserTokenPayload

OAuth 授權事件。

```python
# 官方屬性
payload.user_id         # str | None - 授權用戶 ID（可能為 None！）
payload.user_login      # str | None - 用戶登入名
payload.access_token    # str - Access token
payload.refresh_token   # str - Refresh token
payload.scope           # str | list[str] - 授權範圍
```

#### 使用範例
```python
async def event_oauth_authorized(
    self,
    payload: twitchio.authentication.UserTokenPayload
) -> None:
    # ✅ 正確 - 檢查 user_id 是否存在
    if not payload.user_id:
        return

    # ✅ 正確 - 使用官方屬性
    users = await self.fetch_users(ids=[payload.user_id])
    if users:
        user = users[0]
        await self.add_channel_to_db(user.id, user.name)
```

### StreamOnline

直播上線事件。

```python
# 官方屬性
payload.broadcaster      # PartialUser - 開播的頻道
payload.type            # str - 直播類型（live, playlist, etc.）
payload.started_at      # datetime - 開播時間
```

---

## Context API

命令上下文物件，在命令處理函數中可用。

### 官方屬性

```python
ctx.channel             # PartialUser - 命令執行的頻道
ctx.chatter             # PartialUser - 執行命令的用戶
ctx.author              # PartialUser - 同 ctx.chatter
ctx.message             # ChatMessage - 原始訊息物件
ctx.bot                 # Bot - Bot 實例
```

### 常見使用場景

#### 1. 獲取頻道資訊
```python
@commands.command()
async def uptime(self, ctx: commands.Context[Bot]) -> None:
    # ✅ 正確 - ctx.channel 是 PartialUser，直接使用 .id
    streams = await ctx.bot.fetch_streams(user_ids=[ctx.channel.id])

    if streams:
        stream = streams[0]
        # 處理直播時長...
```

#### 2. 權限檢查
```python
@commands.command()
async def my_command(self, ctx: commands.Context[Bot]) -> None:
    # ✅ 正確 - 檢查是否為頻道擁有者
    if ctx.chatter.id == ctx.channel.id:
        await ctx.reply("你是頻道擁有者！")

    # ✅ 正確 - 檢查是否為 Bot Owner
    if ctx.chatter.id == ctx.bot.owner_id:
        await ctx.reply("你是 Bot Owner！")
```

#### 3. 回覆訊息
```python
@commands.command()
async def greet(self, ctx: commands.Context[Bot]) -> None:
    # ✅ 正確 - 使用 @mention 格式
    await ctx.reply(f"你好 {ctx.chatter.mention}！")

    # ✅ 正確 - 使用 display_name
    await ctx.send(f"歡迎 {ctx.chatter.display_name}！")
```

### 參考資料
- [Context 官方文檔](https://twitchio.dev/en/latest/exts/commands/core.html)

---

## 常見錯誤與修正

### 錯誤 1: 使用不存在的屬性

```python
# ❌ 錯誤
channel_id = ctx.channel.user_id  # PartialUser 沒有 user_id 屬性！

# ✅ 正確
channel_id = ctx.channel.id  # 使用 .id
```

### 錯誤 2: 使用 getattr() 繞路

```python
# ❌ 錯誤 - 不必要的複雜化
channel_id = getattr(ctx.channel, 'user_id', ctx.channel.name)
streams = await ctx.bot.fetch_streams(
    user_ids=[channel_id] if isinstance(channel_id, str) else []
)

# ✅ 正確 - 直接使用官方屬性
streams = await ctx.bot.fetch_streams(user_ids=[ctx.channel.id])
```

### 錯誤 3: 使用私有 API 或錯誤的發送邏輯

```python
# ❌ 錯誤 1 - 使用私有 _http API
await self.bot._http.post_whisper(
    from_user_id=self.bot.bot_id,
    to_user_id=user_id,
    message=message,
    token_for=self.bot.bot_id
)

# ❌ 錯誤 2 - 接收者發給自己
recipient = self.bot.create_partialuser(user_id=user_id)
await recipient.send_whisper(to_user=recipient, message=message)  # 400 錯誤！

# ✅ 正確 - Bot 發給接收者
bot_user = self.bot.create_partialuser(user_id=self.bot.bot_id)
await bot_user.send_whisper(
    to_user=recipient_partialuser,
    message=message
)
```

### 錯誤 4: 錯誤的 payload 屬性名

```python
# ❌ 錯誤 - ChatMessage 沒有 'channel' 屬性
channel_name = getattr(payload, 'channel', None)

# ✅ 正確 - 使用 'broadcaster'
broadcaster = payload.broadcaster  # PartialUser
if broadcaster:
    channel_name = broadcaster.name
```

---

## 檢查清單

在編寫或審查程式碼時，請確保：

- [ ] 使用 `PartialUser.id` 而非 `user_id` 或其他變體
- [ ] 使用 `ChatMessage.broadcaster` 而非 `channel`
- [ ] 使用 `PartialUser.send_whisper()` 而非 `_http.post_whisper()`
- [ ] 不使用 `getattr()` 來獲取已知的官方屬性
- [ ] 不使用任何以 `_` 開頭的私有 API
- [ ] 檢查可能為 `None` 的屬性（如 `payload.user_id`）

---

## 參考資源

### 官方文檔
- [TwitchIO 3 首頁](https://twitchio.dev/)
- [PartialUser API](https://twitchio.dev/en/latest/references/users/partialuser.html)
- [ChatMessage API](https://twitchio.dev/en/latest/references/eventsub/eventsub_models.html)
- [Commands API](https://twitchio.dev/en/latest/exts/commands/core.html)
- [EventSub API](https://twitchio.dev/en/latest/references/eventsub_subscriptions.html)

### Twitch 文檔
- [Twitch EventSub](https://dev.twitch.tv/docs/eventsub)
- [Twitch API Reference](https://dev.twitch.tv/docs/api/reference)

### 問題回報
- [TwitchIO GitHub Issues](https://github.com/TwitchIO/TwitchIO/issues)
- [TwitchIO Discussions](https://github.com/TwitchIO/TwitchIO/discussions)
