# OAuth 設定與權限指南

完整的 OAuth 授權設定、Scopes 說明與權限架構文檔。

## 目錄
- [快速開始](#快速開始)
- [OAuth Scopes 說明](#oauth-scopes-說明)
- [遠端部署設定](#遠端部署設定)
- [權限架構](#權限架構)
- [常見問題](#常見問題)

---

## 快速開始

### 1. 生成授權 URL

```bash
python scripts/oauth.py
```

### 2. Bot 帳號授權

1. 複製「Bot 帳號授權」URL
2. 在瀏覽器中打開
3. **使用 Bot 帳號登入** Twitch
4. 點擊「授權」
5. Bot 會自動處理回調並儲存 token

### 3. 頻道授權

1. 複製「頻道授權」URL
2. 在瀏覽器中打開
3. **使用 Streamer 帳號登入** Twitch
4. 點擊「授權」
5. Bot 會自動處理回調並儲存 token

### 4. 驗證授權

啟動 Bot 並檢查日誌：

```bash
LOG_LEVEL=DEBUG python main.py
```

應該看到類似訊息：
```
Successfully logged in as: bot_user_id
```

---

## OAuth Scopes 說明

### Bot 帳號需要的 Scopes (6)

```
user:read:chat                    # 讀取聊天訊息
user:write:chat                   # 發送聊天訊息
user:bot                          # Bot 功能
moderator:manage:announcements    # 發送公告（搶第一功能）
moderator:read:followers          # 讀取追隨事件
user:manage:whispers              # 發送私訊（Niibot OAuth URL）
```

### Broadcaster 需要的 Scopes (11)

```
channel:bot                      # 允許 Bot 進入頻道
user:write:chat                  # 發送聊天訊息
user:manage:whispers             # 發送私訊
channel:read:redemptions         # 讀取 Channel Points 兌換記錄
channel:manage:vips              # 管理 VIP 身分（VIP 獎勵功能）
moderator:manage:announcements   # 發送公告（搶第一功能）
channel:read:subscriptions       # 讀取訂閱
channel:read:hype_train          # 讀取 Hype Train
channel:read:polls               # 讀取投票
channel:read:predictions         # 讀取預測
bits:read                        # 讀取 Bits
```

### 可選的進階 Scopes

如果需要更多功能，可在 `scripts/config.py` 添加以下 scopes：

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

## 遠端部署設定

### 本地開發環境

預設使用 `http://localhost:4343/oauth/callback`，無需額外設定。

### 雲端部署（Render、AWS、GCP 等）

#### 1. 設定環境變數

在 `.env` 或部署平台的環境變數中添加：

```bash
OAUTH_REDIRECT_URI=https://your-domain.com/oauth/callback
```

#### 2. 更新 Twitch Developer Console

1. 前往 [Twitch Developer Console](https://dev.twitch.tv/console)
2. 選擇你的應用程式
3. 在「OAuth 重定向 URL」中添加：
   ```
   https://your-domain.com/oauth/callback
   ```
4. 點擊「儲存」

#### 3. 重新生成 URL

```bash
python scripts/oauth.py
```

新的 URL 會使用你設定的 Redirect URI。

#### 4. 重新授權

使用新的 URL 重新執行 Bot 和 Broadcaster 授權流程。

---

## 權限架構

### 角色定義

#### 1. Bot Owner（機器人擁有者）

**定義**：在 `.env` 中設定 `OWNER_ID` 的用戶

**權限**：
- 最高管理權限
- 在任何頻道都可以使用管理命令
- 管理 Bot 模組：`!load`, `!unload`, `!reload`, `!shutdown`

**設定範例**：
```env
OWNER_ID=120247692
```

#### 2. Broadcaster（頻道擁有者）

**定義**：每個 Twitch 頻道的擁有者

**權限**：
- 管理自己頻道的功能
- 無法管理 Bot 模組
- 無法管理其他頻道

#### 3. Moderator（版主）

**定義**：頻道的版主

**權限**：
- 使用特定版主命令（例如 `!say`）
- 無法管理 Bot 模組

#### 4. Regular User（一般用戶）

**定義**：頻道中的一般觀眾

**權限**：
- 使用一般命令：`!hi`, `!uptime`, `!ai`, `!運勢`, `!rk`
- 兌換 Channel Points
- 無法使用版主或管理命令

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

### 命令權限對照表

| 命令 | Bot Owner | Broadcaster | Moderator | Regular User |
|------|-----------|-------------|-----------|--------------|
| `!hi`, `!uptime`, `!ai`, `!運勢`, `!rk` | ✅ | ✅ | ✅ | ✅ |
| `!say` | ✅ | ✅ (如果是 Mod) | ✅ | ❌ |
| `!load`, `!unload`, `!reload`, `!shutdown` | ✅ | ❌ | ❌ | ❌ |

---

## 常見問題

### Q1: Bot 需要是頻道的 Mod 嗎？

**A**: 不需要。Bot 不需要 Moderator 身分就能運作。

但是：
- 某些命令限制只有 Moderator 用戶可以使用（例如 `!say`）
- 這是檢查使用命令的用戶是否為 Mod，不是檢查 Bot

### Q2: Bot Owner 和 Broadcaster 可以是同一個人嗎？

**A**: 可以！

如果 Bot Owner 也授權了自己的頻道，那麼：
- 在自己的頻道中，同時擁有 Bot Owner 和 Broadcaster 權限
- 在其他頻道中，只有 Bot Owner 權限

### Q3: Channel Points 獎勵會同步到所有頻道嗎？

**A**: 不會！

- 每個頻道的 Channel Points 獎勵是獨立的
- Bot 只負責監聽兌換事件並做出反應
- 請在 Twitch 後台管理各頻道的獎勵

### Q4: 如何重新授權以獲得新的 Scopes？

**A**: 只需重新訪問授權 URL 即可。

- 新的 token 會自動覆蓋舊的 token
- 新 token 包含所有新舊 scopes
- Bot 會自動使用最新的 token

### Q5: 授權後顯示「無法連接」

**A**: 確認 Bot 正在運行並監聽 port 4343。TwitchIO AutoBot 會自動處理 OAuth 回調。

### Q6: 如何撤銷授權？

**A**: 前往 [Twitch 設定 > 連接](https://www.twitch.tv/settings/connections)，找到你的應用並點擊「中斷連接」。

---

## 安全注意事項

- 絕不要分享 OAuth URL（包含你的 CLIENT_ID）
- 絕不要提交 `.env` 到 git
- 定期檢查已授權的應用
- 生產環境使用 HTTPS redirect URI

---

## 參考資源

- [Twitch OAuth 文檔](https://dev.twitch.tv/docs/authentication)
- [Twitch Scopes 列表](https://dev.twitch.tv/docs/authentication/scopes)
- [TwitchIO 官方文檔](https://twitchio.dev/)
- [部署指南](DEPLOYMENT.md)
