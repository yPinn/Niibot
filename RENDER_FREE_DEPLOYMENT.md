# Render 免費方案部署指南

本文檔說明如何在 Render **免費方案**上部署 Discord Bot。

## 🎯 免費方案說明

Render 免費方案限制：
- ✅ **Web Service 免費**：可部署 HTTP 服務
- ❌ **Background Worker 付費**：最低 $7/月
- ⚠️ **休眠機制**：15 分鐘無活動後自動休眠
- ⏱️ **喚醒時間**：30-60 秒

## 💡 解決方案：Web Service + 健康檢查

我們將 Discord Bot 配置為 Web Service，並添加 HTTP 端點：
1. Bot 正常運行在後台
2. HTTP 服務器提供健康檢查端點
3. 使用外部服務定期 ping，防止休眠

## 🚀 部署步驟

### 1. 推送代碼到 GitHub

```bash
cd e:\Niibot
git add .
git commit -m "Configure Discord Bot for Render free tier"
git push origin main
```

### 2. 在 Render 創建 Web Service

⚠️ **注意**：Blueprint 功能需要付費方案，免費方案請手動創建服務。

1. 訪問 [Render Dashboard](https://dashboard.render.com/)
2. 點擊 **"New"** → **"Web Service"**
3. 連接您的 GitHub repository
4. 配置如下：

   **Basic Settings:**
   - **Name**: `niibot-discord`
   - **Region**: 選擇離您最近的區域
   - **Branch**: `main`
   - **Runtime**: Docker

   **Build Settings:**
   - **Dockerfile Path**: `./backend/discord/Dockerfile`
   - **Docker Build Context Directory**: `./backend`

   **Plan:**
   - **Instance Type**: **Free** ✅

### 3. 設置環境變數

在 Render Dashboard 的 "Environment" 標籤中添加：

| Key | Value | 說明 |
|-----|-------|------|
| `PYTHONUNBUFFERED` | `1` | Python 輸出無緩衝 |
| `ENABLE_HTTP_SERVER` | `true` | 啟用 HTTP 服務器 |
| `HTTP_PORT` | `8080` | HTTP 埠口 |
| `DISCORD_BOT_TOKEN` | `你的Token` | Discord Bot Token ⚠️ |
| `DISCORD_STATUS` | `online` | Bot 狀態（可選） |
| `DISCORD_ACTIVITY_TYPE` | `watching` | 活動類型（可選） |
| `DISCORD_ACTIVITY_NAME` | `Niibot` | 活動名稱（可選） |

⚠️ **重要**：`DISCORD_BOT_TOKEN` 必須正確設置，否則 Bot 無法啟動。

### 4. 配置持久化存儲（可選）

如果需要保存數據：

1. 在 Render Dashboard 點擊您的服務
2. 進入 **"Settings"** 標籤
3. 向下滾動到 **"Disks"** 部分
4. 點擊 **"Add Disk"**
5. 配置：
   - **Mount Path**: `/app/data`
   - **Size**: 1 GB（免費方案最大）

### 5. 部署

1. 點擊 **"Create Web Service"**
2. Render 開始構建 Docker 鏡像
3. 等待部署完成（約 2-5 分鐘）
4. 查看 Logs 確認 Bot 正常啟動

## 🔄 防止休眠設置

免費方案會在 15 分鐘無活動後休眠。使用以下方法保持運行：

### 方式 1：UptimeRobot（推薦，完全免費）

1. 註冊 [UptimeRobot](https://uptimerobot.com/)（免費）
2. 創建新監控：
   - **Monitor Type**: HTTP(s)
   - **URL**: `https://niibot-discord.onrender.com/ping`
   - **Monitoring Interval**: 5 minutes
3. 保存，UptimeRobot 會每 5 分鐘 ping 一次

### 方式 2：Cron-job.org（免費）

1. 註冊 [Cron-job.org](https://cron-job.org/)
2. 創建新 Cron Job：
   - **URL**: `https://niibot-discord.onrender.com/ping`
   - **Interval**: Every 5 minutes
3. 啟用該任務

### 方式 3：自己的服務器（如果有）

```bash
# Linux cron
*/5 * * * * curl https://niibot-discord.onrender.com/ping
```

## 📡 HTTP 端點

部署後，您的 Bot 會提供以下端點：

| 端點 | 說明 | 響應 |
|------|------|------|
| `/` | 根路徑 | Bot 狀態信息（JSON） |
| `/health` | 健康檢查 | 健康狀態（JSON） |
| `/ping` | 簡單 ping | `pong`（文本） |

**範例**：

```bash
# 檢查 Bot 狀態
curl https://niibot-discord.onrender.com/

# 響應：
{
  "service": "Niibot Discord Bot",
  "status": "running",
  "bot_ready": true,
  "latency_ms": 45.23
}

# 簡單 ping
curl https://niibot-discord.onrender.com/ping
# 響應: pong
```

## ⚙️ 本地測試

在部署前，先在本地測試 HTTP 服務器：

```bash
# 設置環境變數
export ENABLE_HTTP_SERVER=true
export HTTP_PORT=8080
export DISCORD_BOT_TOKEN=你的Token

# 啟動 Bot
cd backend/discord
python bot.py

# 在另一個終端測試
curl http://localhost:8080/ping
```

或使用 Docker：

```bash
# 在根目錄
docker-compose up discord-bot

# 測試
curl http://localhost:8080/ping
```

## 📊 免費方案限制與說明

| 項目 | 限制 | 說明 |
|------|------|------|
| **月運行時間** | 750 小時/月 | 足夠 24/7 運行（720小時） |
| **休眠機制** | 15 分鐘後休眠 | 使用 UptimeRobot 可防止 |
| **喚醒時間** | 30-60 秒 | 第一個請求會較慢 |
| **Disk 空間** | 最大 1 GB | 足夠儲存配置和日誌 |
| **頻寬** | 100 GB/月 | 一般使用足夠 |

## 🐛 故障排除

### Bot 無法啟動

1. 檢查 Logs：
   ```
   Dashboard → 您的服務 → Logs
   ```

2. 常見問題：
   - ❌ `DISCORD_BOT_TOKEN` 未設置或錯誤
   - ❌ Dockerfile 路徑錯誤
   - ❌ 依賴安裝失敗

### HTTP 服務器無響應

檢查環境變數：
```
ENABLE_HTTP_SERVER=true
HTTP_PORT=8080
```

### Bot 頻繁休眠

- 確認 UptimeRobot 正常運行
- 檢查監控間隔是否設置為 5 分鐘
- 查看 UptimeRobot 的日誌確認請求成功

### Disk 數據丟失

免費方案的 Disk 在以下情況會清空：
- 服務刪除
- 超過 30 天未使用
- 定期備份重要數據

## 💰 升級到付費方案

如果需要更穩定的服務：

| 方案 | 價格 | 優勢 |
|------|------|------|
| **Starter** | $7/月 | 不休眠、更快響應 |
| **Standard** | $25/月 | 更多資源、優先支援 |

可在 Dashboard → 您的服務 → Settings → Instance Type 升級。

## 🔗 相關連結

- [Render 官方文檔](https://render.com/docs)
- [Discord Bot 文檔](https://discord.com/developers/docs)
- [UptimeRobot](https://uptimerobot.com/)
- [Cron-job.org](https://cron-job.org/)

## ✅ 檢查清單

部署完成後，確認以下項目：

- [ ] Bot 在 Discord 上顯示為在線
- [ ] HTTP 端點 `/ping` 正常響應
- [ ] UptimeRobot 監控已設置
- [ ] Logs 中沒有錯誤
- [ ] Bot 指令正常工作
- [ ] 數據持久化正常（如有設置）

---

🎉 恭喜！您的 Discord Bot 現在在 Render 免費方案上運行了！
