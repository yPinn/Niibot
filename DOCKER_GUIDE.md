# Docker 使用指南

本文檔說明 Niibot 專案的 Docker 配置和使用方式。

## 📁 專案結構

```
Niibot/
├── docker-compose.yml          # 本地開發：啟動所有服務
├── render.yaml                 # Render 部署配置
├── backend/
│   ├── discord/
│   │   ├── Dockerfile         # Discord Bot 鏡像
│   │   └── .env              # Discord 環境變數
│   ├── twitch/
│   │   ├── Dockerfile         # Twitch Bot 鏡像
│   │   └── .env              # Twitch 環境變數
│   ├── api/
│   │   ├── Dockerfile         # API Server 鏡像
│   │   └── .env              # API 環境變數
│   └── data/                  # 本地開發時的數據目錄
└── frontend/
    ├── Dockerfile             # Frontend 鏡像
    └── .env                  # Frontend 環境變數
```

## 🎯 設計理念

### 統一的 Dockerfile
每個服務的 Dockerfile 設計為**同時支援**：
- ✅ Render 雲端部署
- ✅ 本地 Docker Compose 開發
- ✅ 直接 Docker 運行

### 數據持久化策略

| 環境 | Volume 類型 | 數據位置 | 用途 |
|------|------------|---------|------|
| **本地開發** | Named Volume | `niibot-data` | 所有服務共享，重啟保留 |
| **Render** | Disk | 各服務獨立 | 每個服務 1GB 獨立空間 |
| **直接運行** | 無 | 容器內 | 測試用，重啟清空 |

## 🚀 使用方式

### 方式 1：本地開發（推薦）

啟動所有服務：

```bash
# 在根目錄執行
docker-compose up -d

# 查看日誌
docker-compose logs -f

# 停止所有服務
docker-compose down

# 停止並刪除數據
docker-compose down -v
```

**訪問服務：**
- Frontend: http://localhost:3000
- API: http://localhost:8000
- Twitch Bot: http://localhost:4343
- Discord Bot: 背景運行

**數據位置：**
- 使用 Docker named volume: `niibot-data`
- 查看：`docker volume inspect niibot-data`

### 方式 2：單獨運行某個服務

如果只想啟動特定服務：

```bash
# 只啟動 Discord Bot
docker-compose up -d discord-bot

# 只啟動 API
docker-compose up -d api

# 啟動 API + Frontend
docker-compose up -d api frontend
```

### 方式 3：直接用 Docker（不推薦）

如果不使用 docker-compose：

```bash
# 創建網絡
docker network create niibot-network

# 創建 volume
docker volume create niibot-data

# 運行 Discord Bot
cd backend
docker build -f discord/Dockerfile -t niibot-discord .
docker run -d \
  --name niibot-discord \
  --env-file discord/.env \
  --network niibot-network \
  -v niibot-data:/app/data \
  niibot-discord

# 運行其他服務類似...
```

## 🌐 Render 部署

Render 不支援 docker-compose，請參考 [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md) 進行部署。

簡要步驟：

1. 推送代碼到 GitHub
2. 在 Render Dashboard 創建 Blueprint
3. 使用 `render.yaml` 自動配置
4. 設置環境變數
5. 部署

## 🔧 常見操作

### 重建鏡像

```bash
# 重建所有服務
docker-compose build

# 重建特定服務
docker-compose build discord-bot

# 強制重建（不使用緩存）
docker-compose build --no-cache
```

### 查看狀態

```bash
# 查看運行中的容器
docker-compose ps

# 查看資源使用
docker stats

# 查看 volume
docker volume ls
```

### 清理資源

```bash
# 停止並刪除容器
docker-compose down

# 同時刪除 volume
docker-compose down -v

# 清理所有未使用的資源
docker system prune -a
```

### 進入容器

```bash
# 進入 Discord Bot 容器
docker-compose exec discord-bot bash

# 或使用 sh（如果 bash 不可用）
docker-compose exec discord-bot sh

# 查看文件
docker-compose exec discord-bot ls -la /app/data
```

## 📊 環境變數

每個服務需要的環境變數請參考各自的 `.env.example` 文件：

- Discord: `backend/discord/.env`
- Twitch: `backend/twitch/.env`
- API: `backend/api/.env`
- Frontend: `frontend/.env`

**重要：** 請確保所有 `.env` 文件都已正確配置，否則服務無法啟動。

## 🐛 故障排除

### 容器無法啟動

1. 檢查日誌：
   ```bash
   docker-compose logs discord-bot
   ```

2. 檢查環境變數：
   ```bash
   docker-compose config
   ```

3. 重建鏡像：
   ```bash
   docker-compose build --no-cache discord-bot
   docker-compose up -d discord-bot
   ```

### 找不到 /app/data

確認 volume 已創建：
```bash
docker volume ls | grep niibot
```

檢查掛載：
```bash
docker-compose exec discord-bot ls -la /app/
```

### Port 已被占用

如果遇到端口衝突，修改 `docker-compose.yml` 中的端口映射：

```yaml
ports:
  - "8080:8000"  # 改用 8080
```

### 數據丟失

- 本地開發：數據存在 `niibot-data` volume 中，除非執行 `docker-compose down -v`
- Render：數據存在 Disk 中，會持久保存

## 📝 開發建議

### 本地開發流程

1. **修改代碼**後重啟服務：
   ```bash
   docker-compose restart discord-bot
   ```

2. **修改 Dockerfile** 後重建：
   ```bash
   docker-compose up -d --build discord-bot
   ```

3. **查看實時日誌**：
   ```bash
   docker-compose logs -f discord-bot
   ```

### 測試部署前

在推送到 Render 前，先在本地測試：

```bash
# 完全清理環境
docker-compose down -v

# 重新構建並啟動
docker-compose up --build

# 確認所有服務正常運行
docker-compose ps
```

## 🔗 相關文檔

- [Render 部署指南](RENDER_DEPLOYMENT.md) - Render 平台部署說明
- [Docker Compose 官方文檔](https://docs.docker.com/compose/)
- [Dockerfile 最佳實踐](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)

---

如有問題，請檢查日誌或參考相關文檔。
