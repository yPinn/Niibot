# TwitchIO 3 API 快速參考

## PartialUser

```python
user.id              # str | int - 用戶 ID
user.name            # str | None - 用戶名
user.display_name    # str | None - 顯示名稱
user.mention         # str - @mention 格式
```

## Context (命令)

```python
ctx.channel          # PartialUser - 頻道
ctx.chatter          # PartialUser - 執行者
ctx.bot              # Bot 實例

# 獲取直播資訊
streams = await ctx.bot.fetch_streams(user_ids=[ctx.channel.id])

# 權限檢查
if ctx.chatter.id == ctx.channel.id:  # 頻道擁有者
if ctx.chatter.id == ctx.bot.owner_id:  # Bot Owner
```

## ChatMessage (EventSub)

```python
payload.broadcaster  # PartialUser - 頻道
payload.chatter      # PartialUser - 發送者
payload.text         # str - 訊息內容
```

## ChannelPointsRedemptionAdd

```python
payload.user         # PartialUser - 兌換用戶
payload.broadcaster  # PartialUser - 頻道
payload.reward.title # str - 獎勵標題
payload.reward.cost  # int - 花費
payload.user_input   # str | None - 用戶輸入
```

## 發送私訊

```python
# Bot 發給用戶
bot_user = bot.create_partialuser(user_id=bot.bot_id)
await bot_user.send_whisper(to_user=recipient, message="內容")
```

## 常見錯誤

```python
# ❌ 錯誤
ctx.channel.user_id      # 不存在
payload.channel          # 不存在
self.bot._http.xxx()     # 私有 API

# ✅ 正確
ctx.channel.id           # 使用 .id
payload.broadcaster      # 使用 broadcaster
```

## 參考

- [TwitchIO 文檔](https://twitchio.dev/)
- [Twitch API](https://dev.twitch.tv/docs/api/reference)
