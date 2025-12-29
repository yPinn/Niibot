# Render 部署設置檢查清單

完整的 Render 平台設置步驟和配置參考。

## 📋 部署前檢查

- [ ] GitHub repository 已推送最新代碼
- [ ] 確認 `backend/discord/Dockerfile` 存在
- [ ] 確認 `backend/discord/bot.py` 和 `http_server.py` 存在
- [ ] 已取得 Discord Bot Token

## 🚀 Render 設置步驟

### 步驟 1：創建 Web Service

1. 訪問 [Render Dashboard](https://dashboard.render.com/)
2. 點擊 **"New"** → **"Web Service"**
3. 選擇 **"Build and deploy from a Git repository"**
4. 點擊 **"Next"**

### 步驟 2：連接 GitHub Repository

1. 如果是第一次使用，需要授權 Render 訪問 GitHub
2. 選擇 `yPinn/Niibot` repository
3. 點擊 **"Connect"**

### 步驟 3：配置基本設置

在 **"You are deploying a web service"** 頁面：

#### Basic Settings

| 設定項 | 值 |
|--------|-----|
| **Name** | `niibot-discord` |
| **Region** | `Singapore (Southeast Asia)` 或最近的區域 |
| **Branch** | `main` |
| **Root Directory** | 留空 |

#### Build Settings

| 設定項 | 值 |
|--------|-----|
| **Runtime** | `Docker` |
| **Dockerfile Path** | `./backend/discord/Dockerfile` |
| **Docker Build Context Directory** | `./backend` |

⚠️ **重要**：Docker Build Context 必須是 `./backend`，不是 `./backend/discord`

#### Instance Type

選擇 **"Free"** ✅

### 步驟 4：設置環境變數

點擊 **"Advanced"** 展開進階設置，然後在 **"Environment Variables"** 部分添加：

#### 必要環境變數

複製以下內容到 Render：

```env
# Python 設置
PYTHONUNBUFFERED=1

# HTTP 服務器（Render Web Service 必需）
ENABLE_HTTP_SERVER=true
HTTP_PORT=8080

# Discord Bot Token（⚠️ 必須正確設置）
DISCORD_BOT_TOKEN=你的Discord Bot Token

# Discord Guild ID（可選，用於快速同步指令）
DISCORD_GUILD_ID=你的測試伺服器ID

# Bot 狀態設定
DISCORD_STATUS=dnd
DISCORD_ACTIVITY_TYPE=streaming
DISCORD_ACTIVITY_NAME=Rendering...
DISCORD_ACTIVITY_URL=https://twitch.tv/你的頻道

# 日誌等級
LOG_LEVEL=INFO
```

#### 添加方式

對於每個環境變數：
1. 點擊 **"Add Environment Variable"**
2. 在 **Key** 欄位輸入變數名稱（如 `PYTHONUNBUFFERED`）
3. 在 **Value** 欄位輸入值（如 `1`）
4. 重複直到所有變數都添加完成

### 步驟 5：配置持久化存儲（可選）

如果需要保存數據（如用戶設定、統計等）：

1. 在 **"Advanced"** 部分找到 **"Disks"**
2. 點擊 **"Add Disk"**
3. 配置：
   - **Name**: `discord-data`（可自訂）
   - **Mount Path**: `/app/data`
   - **Size**: `1` GB（免費方案最大值）

### 步驟 6：配置健康檢查（可選但推薦）

在 **"Advanced"** 部分：

| 設定項 | 值 |
|--------|-----|
| **Health Check Path** | `/health` |

這會讓 Render 定期檢查 Bot 是否正常運行。

### 步驟 7：部署

1. 檢查所有設置是否正確
2. 點擊頁面底部的 **"Create Web Service"**
3. Render 開始構建 Docker 鏡像（約 2-5 分鐘）

## 📊 部署監控

### 查看構建日誌

1. 在 Service Dashboard 點擊 **"Logs"** 標籤
2. 選擇 **"Build Logs"** 查看構建過程
3. 等待出現 `Build successful` 訊息

### 查看運行日誌

1. 切換到 **"Deploy Logs"**
2. 應該看到：
   ```
   HTTP server started on 0.0.0.0:8080
   正在連接 Discord...
   Bot 已就緒: YourBotName#1234
   ```

### 確認服務運行

部署完成後，您會得到一個 URL，例如：
```
https://niibot-discord.onrender.com
```

測試端點：
```bash
# 測試 ping
curl https://niibot-discord.onrender.com/ping
# 應該返回: pong

# 查看 Bot 狀態
curl https://niibot-discord.onrender.com/
# 應該返回 JSON 狀態信息
```

## 🔄 防止休眠設置（重要！）

免費方案會在 15 分鐘無活動後休眠。使用 UptimeRobot 防止：

### UptimeRobot 設置步驟

1. **註冊帳號**
   - 訪問 https://uptimerobot.com/
   - 點擊 **"Register for FREE!"**
   - 使用 Email 或 Google 帳號註冊

2. **創建新監控**
   - 登入後點擊 **"+ Add New Monitor"**
   - 配置如下：

   | 設定項 | 值 |
   |--------|-----|
   | **Monitor Type** | `HTTP(s)` |
   | **Friendly Name** | `Niibot Discord Bot` |
   | **URL (or IP)** | `https://niibot-discord.onrender.com/ping` |
   | **Monitoring Interval** | `5 minutes` |

3. **完成設置**
   - 點擊 **"Create Monitor"**
   - UptimeRobot 會每 5 分鐘 ping 一次，防止 Bot 休眠

4. **可選：設置警報**
   - 在 Monitor 設置中添加 **Alert Contacts**
   - 當 Bot 離線時會收到 Email 通知

## ✅ 驗證清單

部署完成後，確認以下項目：

- [ ] Render Dashboard 顯示服務狀態為 **"Live"**（綠色）
- [ ] Logs 中顯示 `Bot 已就緒`
- [ ] Discord 上 Bot 顯示為在線（狀態：dnd）
- [ ] HTTP 端點 `/ping` 正常響應
- [ ] HTTP 端點 `/health` 返回 `"status": "healthy"`
- [ ] Bot 指令可以正常使用（測試一個斜線指令）
- [ ] UptimeRobot 監控已設置且顯示 **"Up"**

## 🐛 常見問題排查

### 問題 1：構建失敗

**錯誤訊息**：`Failed to build`

**解決方案**：
1. 檢查 Dockerfile 路徑是否正確：`./backend/discord/Dockerfile`
2. 檢查 Docker Context 是否正確：`./backend`
3. 查看 Build Logs 中的具體錯誤訊息

### 問題 2：Bot 無法啟動

**錯誤訊息**：`找不到 DISCORD_BOT_TOKEN 環境變數`

**解決方案**：
1. 進入 Service → Environment 標籤
2. 確認 `DISCORD_BOT_TOKEN` 已正確設置
3. 點擊 **"Save Changes"** 並重新部署

### 問題 3：HTTP 服務器無響應

**錯誤訊息**：`curl: (7) Failed to connect`

**解決方案**：
1. 檢查環境變數 `ENABLE_HTTP_SERVER=true`
2. 檢查環境變數 `HTTP_PORT=8080`
3. 確認 Dockerfile 有 `EXPOSE 8080`

### 問題 4：Bot 頻繁休眠

**症狀**：Bot 每隔一段時間就離線

**解決方案**：
1. 確認 UptimeRobot 監控已正確設置
2. 檢查 UptimeRobot 的 Status 是否顯示 **"Up"**
3. 確認監控間隔設置為 5 分鐘

### 問題 5：指令無法同步

**症狀**：Discord 中看不到斜線指令

**解決方案**：
1. 確認 `DISCORD_GUILD_ID` 環境變數已設置（加速同步）
2. 等待最多 1 小時讓 Discord 全域同步
3. 檢查 Logs 中是否有 `已同步斜線指令` 訊息

## 📝 環境變數快速參考

| 變數名 | 必需 | 說明 | 範例值 |
|--------|------|------|--------|
| `PYTHONUNBUFFERED` | ✅ | Python 無緩衝輸出 | `1` |
| `ENABLE_HTTP_SERVER` | ✅ | 啟用 HTTP 服務器 | `true` |
| `HTTP_PORT` | ✅ | HTTP 埠口 | `8080` |
| `DISCORD_BOT_TOKEN` | ✅ | Discord Bot Token | `MTI3O...` |
| `DISCORD_GUILD_ID` | ❌ | 測試伺服器 ID | `1330756...` |
| `DISCORD_STATUS` | ❌ | Bot 狀態 | `dnd` |
| `DISCORD_ACTIVITY_TYPE` | ❌ | 活動類型 | `streaming` |
| `DISCORD_ACTIVITY_NAME` | ❌ | 活動名稱 | `Rendering...` |
| `DISCORD_ACTIVITY_URL` | ❌ | Streaming URL | `https://twitch.tv/...` |
| `LOG_LEVEL` | ❌ | 日誌等級 | `INFO` |

## 🔗 相關連結

- [Render Dashboard](https://dashboard.render.com/)
- [Render 文檔](https://render.com/docs)
- [UptimeRobot](https://uptimerobot.com/)
- [Discord Developer Portal](https://discord.com/developers/applications)

## 💡 提示

1. **首次部署**需要約 2-5 分鐘構建時間
2. **程式碼更新**後 Render 會自動重新部署
3. **免費方案限制**：750 小時/月（足夠 24/7 運行）
4. **升級方案**：如需永不休眠，升級到 Starter ($7/月)

---

🎉 完成以上步驟後，您的 Discord Bot 就在 Render 上運行了！
