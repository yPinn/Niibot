# Discord Bot 速率限制監控

## 概述

為了避免 Discord bot 因發送過多請求而被 API 封禁,已實作自動速率限制監控系統。

## 功能特點

### 1. 自動監控
- 追蹤所有 Discord API 請求
- 自動偵測 429 (Too Many Requests) 錯誤
- 每 5 分鐘輸出統計報告

### 2. 預先檢查
- 在發送請求前檢查速率風險
- 達到警告閾值時發出警告
- 達到危險閾值時阻止請求

### 3. 管理指令
- `/rate_stats` - 查看詳細統計資訊
- `/rate_check` - 檢查當前速率風險

## 配置說明

在 `backend/discord/.env` 文件中配置:

```env
# 啟用/停用速率限制監控
RATE_LIMIT_ENABLED=true

# 警告閾值 (70% = 達到限制的 70% 時警告)
RATE_LIMIT_WARNING_THRESHOLD=0.7

# 危險閾值 (90% = 達到限制的 90% 時阻止)
RATE_LIMIT_CRITICAL_THRESHOLD=0.9
```

## Discord API 限制參考值

- **全局限制**: 50 請求/秒
- **訊息限制**: 5 訊息/5秒/頻道
- **反應限制**: 1 反應/0.25秒

## 在 Cog 中使用

### 方法 1: 使用 safe_send_message (推薦)

```python
class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rate_limiter = bot.rate_limiter

    @app_commands.command()
    async def my_command(self, interaction: discord.Interaction):
        # 使用安全發送,自動檢查速率
        message = await self.rate_limiter.safe_send_message(
            interaction.channel,
            "這是一條安全發送的訊息"
        )

        if message is None:
            # 速率過高,訊息未發送
            await interaction.response.send_message("⚠️ 請稍後再試", ephemeral=True)
```

### 方法 2: 手動檢查速率

```python
@app_commands.command()
async def bulk_command(self, interaction: discord.Interaction):
    # 手動檢查速率風險
    is_safe, msg = self.bot.rate_limiter.check_rate_limit_risk("message")

    if not is_safe:
        await interaction.response.send_message(f"⚠️ {msg}", ephemeral=True)
        return

    # 安全,繼續執行
    await interaction.response.send_message("執行中...")
```

### 方法 3: 批量操作

```python
@app_commands.command()
async def bulk_send(self, interaction: discord.Interaction):
    channels = [...]  # 多個頻道

    # 準備批量操作 (注意:不要直接 await,傳入 coroutine)
    operations = [
        channel.send("批量訊息")
        for channel in channels
    ]

    # 安全執行批量操作 (自動延遲和檢查)
    results = await self.bot.rate_limiter.safe_bulk_operation(
        operations,
        delay=0.5  # 每個操作間隔 0.5 秒
    )

    success_count = sum(1 for r in results if r is not None)
    await interaction.response.send_message(f"發送完成: {success_count}/{len(results)}")
```

## 監控輸出範例

### 定期統計報告 (每 5 分鐘)
```
📊 速率統計 (過去 5.0 分鐘): 總請求: 234, 平均 0.78 req/s, 最近1分鐘: 1.2 req/s, 限制次數: 0
```

### 速率警告
```
⚠️ 全局速率警告 (38/50 req/s, 76%)
```

### 速率限制觸發
```
⚠️ 觸發速率限制! Bucket: /channels/123/messages, 重試等待: 2.34秒, 範圍: user
```

## 最佳實踐

### 1. 批量操作時使用延遲

```python
# ❌ 不好的做法
for user in users:
    await channel.send(f"Hello {user}")

# ✅ 好的做法
operations = [channel.send(f"Hello {user}") for user in users]
await self.bot.rate_limiter.safe_bulk_operation(operations, delay=0.5)
```

### 2. 處理失敗情況

```python
message = await self.bot.rate_limiter.safe_send_message(channel, "內容")
if message is None:
    # 速率過高,向用戶說明
    await interaction.followup.send("⚠️ 系統繁忙,請稍後再試", ephemeral=True)
```

### 3. 定期監控

- 使用 `/rate_stats` 檢查統計
- 關注 `rate_limited_count` 數值
- 如果經常觸發限制,優化指令邏輯

## 故障排查

### 經常觸發速率限制

**解決方案:**
1. 檢查是否有循環發送大量訊息的指令
2. 增加批量操作的延遲時間
3. 使用 `/rate_stats` 查看請求模式
4. 考慮使用 Embed 合併多條訊息

### 監控未啟動

**解決方案:**
1. 檢查 `.env` 中 `RATE_LIMIT_ENABLED=true`
2. 查看 bot 啟動日誌是否有 "速率限制監控已啟動"
3. 確認沒有語法錯誤

### 想要更嚴格的限制

調整 `.env` 中的閾值:
```env
RATE_LIMIT_WARNING_THRESHOLD=0.5  # 50% 就警告
RATE_LIMIT_CRITICAL_THRESHOLD=0.7  # 70% 就阻止
```

## 技術細節

### 監控原理
- 監聽 `on_socket_raw_send` 事件記錄所有請求
- 監聽 `on_rate_limit` 事件捕獲 429 錯誤
- 使用滑動窗口追蹤最近 1000 個請求

### 與 Discord.py 內建處理的關係
Discord.py 已有內建的速率限制處理 (自動等待重試),本系統是**額外的預防層**:
- Discord.py: 收到 429 後自動等待
- 本系統: 發送前就預防,避免觸發 429
- 兩者互補,提供雙重保護

### 性能影響
- 記憶體使用: ~20KB (1000 個時間戳)
- CPU 影響: 極低 (僅時間戳記錄)
- 不影響正常運作
