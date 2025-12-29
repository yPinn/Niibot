# Render 部署指南

本文檔說明如何在 Render 平台上部署 Niibot 專案。

## 專案架構說明

本專案支援兩種部署方式：

### 🚀 生產環境（Render）
- 使用 `render.yaml` 配置文件
- 每個服務獨立部署
- 使用 Render 的 Disk 進行數據持久化

### 💻 本地開發環境
- 使用根目錄的 `docker-compose.yml`
- 一鍵啟動所有服務：`docker-compose up`
- 使用 Docker named volume `niibot-data` 共享數據

## 重要說明

⚠️ **Render 不支援 docker-compose**
Render 要求每個服務單獨部署，使用各自的 Dockerfile。本專案的 Dockerfile 已經優化為同時支援 Render 和本地開發。

## 部署方式

### 方式 1：使用 Blueprint（推薦）

使用根目錄的 `render.yaml` 一次性部署所有服務。

#### 步驟：

1. **連接 GitHub Repository**
   - 登入 [Render Dashboard](https://dashboard.render.com/)
   - 點擊 "New" → "Blueprint"
   - 連接您的 GitHub repository

2. **自動讀取 render.yaml**
   - Render 會自動檢測 `render.yaml` 文件
   - 審查將要創建的服務列表

3. **設置環境變數**
   - 在部署前，需要在 Render Dashboard 為每個服務設置必要的環境變數
   - 參考下方「必要環境變數」章節

4. **確認並部署**
   - 點擊 "Apply" 開始部署
   - Render 會自動創建 4 個服務

### 方式 2：手動創建各個服務

如果不使用 Blueprint，可以手動創建每個服務：

#### Discord Bot

1. Dashboard → "New" → "Background Worker"
2. 配置：
   - **Name**: `niibot-discord`
   - **Environment**: Docker
   - **Dockerfile Path**: `./backend/discord/Dockerfile`
   - **Docker Build Context Directory**: `./backend`
3. 添加 Disk（在 Advanced 設置中）：
   - **Mount Path**: `/app/data`
   - **Size**: 1GB
4. 設置環境變數（參考下方）

#### Twitch Bot

1. Dashboard → "New" → "Background Worker"
2. 配置：
   - **Name**: `niibot-twitch`
   - **Environment**: Docker
   - **Dockerfile Path**: `./backend/twitch/Dockerfile`
   - **Docker Build Context Directory**: `./backend`
3. 添加 Disk（在 Advanced 設置中）：
   - **Mount Path**: `/app/data`
   - **Size**: 1GB
4. 設置環境變數（參考下方）

#### API Server

1. Dashboard → "New" → "Web Service"
2. 配置：
   - **Name**: `niibot-api`
   - **Environment**: Docker
   - **Dockerfile Path**: `./backend/api/Dockerfile`
   - **Docker Build Context Directory**: `./backend`
3. 添加 Disk（在 Advanced 設置中）：
   - **Mount Path**: `/app/data`
   - **Size**: 1GB
4. 設置環境變數（參考下方）

#### Frontend

1. Dashboard → "New" → "Web Service"
2. 配置：
   - **Name**: `niibot-frontend`
   - **Environment**: Docker
   - **Dockerfile Path**: `./frontend/Dockerfile`
   - **Docker Build Context Directory**: `./frontend`
3. 設置環境變數（參考下方）

## 必要環境變數

### Discord Bot (`niibot-discord`)

從 `backend/discord/.env` 複製以下變數到 Render：

```
DISCORD_TOKEN=你的Discord Token
DISCORD_STATUS=online
DISCORD_ACTIVITY_TYPE=watching
DISCORD_ACTIVITY_NAME=Niibot
RATE_LIMIT_ENABLED=true
RATE_LIMIT_WARNING_THRESHOLD=0.7
RATE_LIMIT_CRITICAL_THRESHOLD=0.9
```

### Twitch Bot (`niibot-twitch`)

從 `backend/twitch/.env` 複製以下變數到 Render：

```
TWITCH_CLIENT_ID=你的Twitch Client ID
TWITCH_CLIENT_SECRET=你的Twitch Client Secret
TWITCH_CHANNEL_NAME=你的頻道名稱
TWITCH_BOT_USERNAME=機器人用戶名
TWITCH_OAUTH_TOKEN=OAuth Token
```

### API Server (`niibot-api`)

從 `backend/api/.env` 複製以下變數到 Render：

```
API_KEY=你的API密鑰
DATABASE_URL=資料庫連接字串（如果有）
```

### Frontend (`niibot-frontend`)

從 `frontend/.env` 複製以下變數到 Render：

```
REACT_APP_API_URL=https://niibot-api.onrender.com
NODE_ENV=production
```

⚠️ **注意**：請將 `https://niibot-api.onrender.com` 替換為您實際的 API 服務 URL

## 數據持久化

Render 使用 **Disk** 功能來持久化數據：

- 每個需要保存數據的服務都配置了 1GB 的 Disk
- 掛載路徑統一為 `/app/data`
- 即使服務重啟，數據也會保留

### 共享數據（進階）

如果多個服務需要共享同一份數據，您需要：

1. 使用外部存儲服務（如 AWS S3、Google Cloud Storage）
2. 或使用 Render 的 PostgreSQL/Redis 服務
3. 在 `render.yaml` 中配置共享數據庫

## 服務間通信

由於 Render 上各服務獨立部署：

1. **內部通信**：使用 Render 提供的私有網絡
   - 服務可通過 `https://<service-name>` 互相訪問
   - 例如：API 可通過 `https://niibot-discord` 訪問 Discord 服務

2. **外部訪問**：
   - Web Service (API/Frontend) 會獲得公開 URL
   - Background Worker (Bots) 不對外開放

## 部署流程

1. **推送代碼到 GitHub**
   ```bash
   git add .
   git commit -m "Prepare for Render deployment"
   git push origin main
   ```

2. **在 Render 創建服務**（選擇上述任一方式）

3. **配置環境變數**（非常重要！）

4. **啟動服務**
   - Render 會自動構建 Docker 鏡像
   - 構建完成後服務會自動啟動

5. **監控日誌**
   - 在 Render Dashboard 查看各服務的日誌
   - 確認服務正常運行

## 費用說明

Render 的定價：

- **Free Tier**：
  - 750 小時/月的免費運行時間
  - 適合輕量級應用
  - 服務閒置 15 分鐘後會休眠

- **Starter ($7/月/服務)**：
  - 不會休眠
  - 更好的性能
  - 適合生產環境

計算本專案成本：
- 4 個服務 × $7 = **$28/月**（如果全部使用 Starter）
- 或混合使用 Free + Starter

## 故障排除

### 服務無法啟動

1. 檢查 Render 日誌中的錯誤訊息
2. 確認所有環境變數都已正確設置
3. 檢查 Dockerfile 路徑是否正確

### 找不到 /app/data

確保在 Render Dashboard 中為服務添加了 Disk，並設置：
- Mount Path: `/app/data`

### 服務間無法通信

1. 確認使用正確的內部 URL
2. 檢查網絡配置
3. 查看 Render 的 Private Network 設置

## 替代方案

如果一定要使用 docker-compose，可以考慮：

1. **Railway.app**：支援 docker-compose
2. **DigitalOcean App Platform**：部分支援
3. **自建 VPS**：完全控制，使用 Docker Compose

## 更新部署

代碼更新後：

1. 推送到 GitHub
2. Render 會自動檢測並重新部署
3. 或在 Dashboard 手動觸發部署

## 相關連結

- [Render 官方文檔](https://render.com/docs)
- [Render Docker 支援](https://render.com/docs/docker)
- [Blueprint 規範](https://render.com/docs/blueprint-spec)

---

如有問題，請參考 Render 官方文檔或聯繫支援團隊。
