# Bot 設定與權限指南

## 目錄
- [OAuth 授權流程](#oauth-授權流程)
- [OAuth Scopes 說明](#oauth-scopes-說明)
- [權限架構](#權限架構)
- [常見問題](#常見問題)

---

## OAuth 授權流程

### 授權說明

AutoBot 在 `http://localhost:4343` 提供 OAuth server 處理授權。

**流程**：
1. 用戶訪問 Twitch 授權 URL
2. 同意授權後，Twitch 重定向到 `http://localhost:4343/oauth/callback`
3. Bot 自動交換並儲存 tokens
4. 訂閱頻道的 EventSub 事件

### 授權 URL

將 `YOUR_CLIENT_ID` 替換為你的 Twitch Client ID：

#### Bot 帳號授權（使用 Bot 帳號登入）
```
https://id.twitch.tv/oauth2/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=http%3A%2F%2Flocalhost%3A4343%2Foauth%2Fcallback&response_type=code&scope=user%3Aread%3Achat+user%3Awrite%3Achat+user%3Abot
```

#### 頻道授權（Streamer 使用自己的帳號登入）
```
https://id.twitch.tv/oauth2/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=http%3A%2F%2Flocalhost%3A4343%2Foauth%2Fcallback&response_type=code&scope=channel%3Abot+channel%3Amanage%3Aredemptions+channel%3Aread%3Aredemptions+channel%3Amanage%3Avips+moderator%3Aread%3Afollowers+channel%3Aread%3Asubscriptions+moderator%3Amanage%3Achat_messages+moderator%3Aread%3Achatters+channel%3Aread%3Ahype_train+channel%3Aread%3Apolls+channel%3Aread%3Apredictions+bits%3Aread
```

---

## OAuth Scopes 說明

### Bot 帳號需要的 Scopes
```
user:read:chat      # 讀取聊天訊息
user:write:chat     # 發送聊天訊息
user:bot            # Bot 功能
```

### Broadcaster 需要的 Scopes
```
channel:bot                      # 允許 Bot 進入頻道
channel:manage:redemptions       # 管理 Channel Points 獎勵
channel:read:redemptions         # 讀取 Channel Points 兌換記錄
channel:manage:vips              # 管理 VIP 身分（VIP 獎勵功能需要）
moderator:read:followers         # 讀取追隨者
channel:read:subscriptions       # 讀取訂閱
moderator:manage:chat_messages   # 管理聊天訊息
moderator:read:chatters          # 讀取聊天用戶
channel:read:hype_train          # 讀取 Hype Train
channel:read:polls               # 讀取投票
channel:read:predictions         # 讀取預測
bits:read                        # 讀取 Bits
```

### 可選的進階 Scopes

#### 管理功能
- `moderator:manage:banned_users` - 管理封禁用戶
- `moderator:read:banned_users` - 讀取封禁列表
- `moderator:manage:chat_settings` - 管理聊天設定
- `channel:manage:moderators` - 管理版主

#### 進階頻道功能
- `channel:manage:polls` - 管理投票
- `channel:manage:predictions` - 管理預測
- `channel:manage:raids` - 管理 Raid
- `clips:edit` - 建立剪輯
- `channel:read:goals` - 讀取目標進度

---

## 權限架構

### 角色定義

#### 1. Bot Owner（機器人擁有者）

**定義**：在 `.env` 中設定 `OWNER_ID` 的用戶

**權限**：
- ✅ 最高管理權限
- ✅ 在**任何頻道**都可以使用管理命令
- ✅ 管理 Bot 模組：`!load`, `!unload`, `!reload`, `!shutdown`
- ✅ 查看所有模組：`!loaded`

**範例**：
```env
OWNER_ID=120247692  # 這個用戶是 Bot Owner
```

**程式碼檢查**：
```python
if ctx.chatter.id == ctx.bot.owner_id:
    # 這是 Bot Owner
```

---

#### 2. Broadcaster（頻道擁有者）

**定義**：每個 Twitch 頻道的擁有者

**權限**：
- ✅ 管理**自己頻道**的功能
- ❌ 無法管理 Bot 模組
- ❌ 無法管理其他頻道

**程式碼檢查**：
```python
if ctx.chatter.id == ctx.channel.id:
    # 這是當前頻道的 Broadcaster
```

---

#### 3. Moderator（版主）

**定義**：頻道的版主

**權限**：
- ✅ 使用特定版主命令（例如 `!say`）
- ❌ 無法管理 Bot 模組

**程式碼檢查**：
```python
@commands.is_moderator()
async def my_command(self, ctx):
    # 只有 Moderator 可以使用
```

---

#### 4. Regular User（一般用戶）

**定義**：頻道中的一般觀眾

**權限**：
- ✅ 使用一般命令：`!hi`, `!uptime`, `!socials`, `!ai`
- ✅ 兌換 Channel Points
- ❌ 無法使用版主或管理命令

---

### 權限層級圖

```
Bot Owner (最高權限)
    ├── 管理 Bot 模組（所有頻道）
    └── 擁有所有 Broadcaster 權限（在任何頻道）

Broadcaster (頻道擁有者)
    ├── 管理自己頻道的功能
    └── 擁有自己頻道的 Moderator 權限

Moderator (版主)
    ├── 使用版主命令
    └── 擁有 Regular User 權限

Regular User (一般用戶)
    └── 使用基本命令
```

---

### 命令權限對照表

| 命令 | Bot Owner | Broadcaster | Moderator | Regular User |
|------|-----------|-------------|-----------|--------------|
| `!hi` | ✅ | ✅ | ✅ | ✅ |
| `!uptime` | ✅ | ✅ | ✅ | ✅ |
| `!socials` | ✅ | ✅ | ✅ | ✅ |
| `!ai` | ✅ | ✅ | ✅ | ✅ |
| `!redemptions` | ✅ | ✅ | ✅ | ✅ |
| `!say` | ✅ | ✅ (如果是 Mod) | ✅ | ❌ |
| `!load` | ✅ | ❌ | ❌ | ❌ |
| `!unload` | ✅ | ❌ | ❌ | ❌ |
| `!reload` | ✅ | ❌ | ❌ | ❌ |
| `!shutdown` | ✅ | ❌ | ❌ | ❌ |

---

## 常見問題

### Q1: Bot 需要是頻道的 Mod 嗎？

**A**: 不需要。Bot 不需要 Moderator 身分就能運作。

但是：
- 某些**命令**限制只有 Moderator 用戶可以使用（例如 `!say`）
- 這是檢查**使用命令的用戶**是否為 Mod，不是檢查 Bot

### Q2: Bot Owner 和 Broadcaster 可以是同一個人嗎？

**A**: 可以！

如果 Bot Owner 也授權了自己的頻道，那麼：
- 在自己的頻道中，同時擁有 Bot Owner 和 Broadcaster 權限
- 在其他頻道中，只有 Bot Owner 權限

### Q3: Channel Points 獎勵會同步到所有頻道嗎？

**A**: 不會！

- 每個頻道的 Channel Points 獎勵是**獨立**的
- Bot 只負責監聽兌換事件並做出反應
- 請在 Twitch 後台管理各頻道的獎勵

### Q4: 如何重新授權以獲得新的 Scopes？

**A**: 只需重新訪問授權 URL 即可。

- 新的 token 會自動覆蓋舊的 token
- 新 token 包含所有新舊 scopes
- Bot 會自動使用最新的 token

---

## 參考資源

- [Twitch OAuth 文檔](https://dev.twitch.tv/docs/authentication)
- [Twitch Scopes 列表](https://dev.twitch.tv/docs/authentication/scopes)
- [TwitchIO 官方文檔](https://twitchio.dev/)
