# Niibot Docker 部署指南

## 概述

Niibot 使用 Docker Compose 來管理多個服務的容器化部署。

## 服務架構

```
┌─────────────────────────────────────────────┐
│              Docker Network                 │
│         (niibot-network)                    │
│                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ Frontend │  │   API    │  │ Twitch   │ │
│  │ (Nginx)  │  │ (FastAPI)│  │   Bot    │ │
│  │  :80     │  │  :8000   │  │  :4343   │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
│       │             │              │        │
│       └─────────────┴──────────────┘        │
│                     │                       │
│                     │                       │
│              ┌─────────────┐               │
│              │ Discord Bot │               │
│              └─────────────┘               │
└─────────────────────────────────────────────┘
                      │
                      ▼
              ┌──────────────┐
              │   Supabase   │ (雲端)
              │  PostgreSQL  │
              └──────────────┘

對外端口:
- 3000 -> Frontend (HTTP)
- 8000 -> API Server
- 4343 -> Twitch Bot (OAuth)

注意: 使用 Supabase 雲端資料庫,無需本地 PostgreSQL 容器
```

## 快速開始

### 1. 環境準備

確保已安裝:
- Docker >= 20.10
- Docker Compose >= 2.0

### 2. 配置環境變數

複製所有 `.env.example` 為 `.env`:

```bash
cp backend/api/.env.example backend/api/.env
cp backend/twitch/.env.example backend/twitch/.env
cp backend/discord/.env.example backend/discord/.env
cp frontend/.env.example frontend/.env
```

然後編輯每個 `.env` 文件,填入實際配置值。

**重要**: 查看 [environment-setup.md](./environment-setup.md) 了解哪些配置需要在多個服務中保持一致。

### 3. 啟動所有服務

```bash
# 構建並啟動所有服務
docker-compose up -d

# 查看日誌
docker-compose logs -f

# 查看特定服務的日誌
docker-compose logs -f discord-bot
```

### 4. 驗證服務

- Frontend: http://localhost:3000
- API Server: http://localhost:8000/docs (Swagger UI)
- Twitch Bot OAuth: http://localhost:4343

## Docker Compose 指令

### 基本操作

```bash
# 啟動所有服務
docker-compose up -d

# 停止所有服務
docker-compose stop

# 停止並刪除容器
docker-compose down

# 停止並刪除容器和 volumes (會清空資料庫)
docker-compose down -v

# 重啟服務
docker-compose restart

# 重啟特定服務
docker-compose restart discord-bot
```

### 查看狀態

```bash
# 查看運行中的容器
docker-compose ps

# 查看資源使用
docker stats

# 查看日誌
docker-compose logs -f

# 只查看最近100行
docker-compose logs --tail=100 -f
```

### 構建和更新

```bash
# 重新構建所有鏡像
docker-compose build

# 重新構建特定服務
docker-compose build discord-bot

# 重新構建並啟動
docker-compose up -d --build

# 拉取最新的基礎鏡像
docker-compose pull
```

### 進入容器

```bash
# 進入容器 shell
docker-compose exec discord-bot sh

# 以 root 身份進入
docker-compose exec -u root discord-bot sh

# 執行單次命令
docker-compose exec discord-bot python --version
```

## 服務詳情

### Frontend

- **容器名**: `niibot-frontend`
- **Image**: Custom (Node.js build + Nginx)
- **端口映射**: `3000:80`
- **依賴**: api

**特性**:
- 多階段構建 (減小鏡像大小)
- Nginx 靜態文件服務
- 支持 React Router (SPA)
- Gzip 壓縮
- 靜態資源緩存

### API Server

- **容器名**: `niibot-api`
- **Image**: Custom (Python 3.11)
- **端口映射**: `8000:8000`
- **依賴**: Supabase (雲端資料庫)

### Twitch Bot

- **容器名**: `niibot-twitch`
- **Image**: Custom (Python 3.11)
- **端口映射**: `4343:4343`
- **依賴**: Supabase (雲端資料庫)

### Discord Bot

- **容器名**: `niibot-discord`
- **Image**: Custom (Python 3.11)
- **Volume**: `./backend/data:/app/data`
- **無依賴**

## 開發環境 vs 生產環境

### 開發環境

```bash
# 使用開發配置
docker-compose up -d

# Hot reload (需要 volume mount 源碼)
# 修改 docker-compose.yml 添加:
#   volumes:
#     - ./backend/discord:/app
```

### 生產環境

1. **修改環境變數**:
   - 使用強密碼
   - 修改 `JWT_SECRET_KEY`
   - 設置正確的 URL

2. **使用生產配置**:
   ```yaml
   # docker-compose.prod.yml
   services:
     postgres:
       environment:
         POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}  # 從環境變數讀取
   ```

3. **啟動**:
   ```bash
   docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
   ```

## 故障排除

### 服務啟動失敗

```bash
# 查看詳細錯誤
docker-compose logs <service-name>

# 檢查配置
docker-compose config

# 驗證 .env 文件
docker-compose exec <service-name> env
```

### 資料庫連接失敗

確保:
1. `DATABASE_URL` 使用 `postgres` 作為主機名 (不是 `localhost`)
2. PostgreSQL 容器健康 (`docker-compose ps`)
3. 服務配置了 `depends_on` 和健康檢查

### 端口衝突

```bash
# 檢查端口占用
netstat -ano | findstr :3000
netstat -ano | findstr :8000

# 修改 docker-compose.yml 中的端口映射
ports:
  - "3001:80"  # 使用不同的對外端口
```

### 鏡像構建失敗

```bash
# 清理舊鏡像
docker system prune -a

# 重新構建 (不使用緩存)
docker-compose build --no-cache

# 檢查 Dockerfile 路徑
docker-compose config | grep dockerfile
```

### Volume 權限問題

```bash
# Linux/Mac: 修改 volume 權限
sudo chown -R $USER:$USER ./backend/data

# Windows: 確保 Docker Desktop 有訪問權限
```

## 資料備份和恢復

### 備份資料庫

```bash
# 備份到檔案
docker-compose exec -T postgres pg_dump -U user twitchio_bot > backup.sql

# 使用 gzip 壓縮
docker-compose exec -T postgres pg_dump -U user twitchio_bot | gzip > backup.sql.gz
```

### 恢復資料庫

```bash
# 從備份恢復
docker-compose exec -T postgres psql -U user twitchio_bot < backup.sql

# 從壓縮備份恢復
gunzip < backup.sql.gz | docker-compose exec -T postgres psql -U user twitchio_bot
```

### 備份 Discord Bot 資料

```bash
# 複製 data 目錄
cp -r backend/data backend/data.backup

# 或使用 tar
tar -czf data-backup-$(date +%Y%m%d).tar.gz backend/data
```

## 監控和日誌

### 日誌管理

```bash
# 實時查看所有日誌
docker-compose logs -f

# 只看特定服務
docker-compose logs -f discord-bot twitch-bot

# 匯出日誌
docker-compose logs --no-color > logs.txt
```

### 資源監控

```bash
# 查看資源使用
docker stats

# 查看容器詳情
docker-compose ps
docker inspect niibot-discord
```

## 性能優化

### 鏡像大小優化

1. **使用多階段構建** (已實現)
2. **使用 alpine 基礎鏡像** (已實現)
3. **清理緩存**:
   ```dockerfile
   RUN pip install --no-cache-dir -r requirements.txt
   RUN npm ci --only=production
   ```

### 啟動時間優化

1. **健康檢查**: 確保依賴服務就緒
2. **並行啟動**: 移除不必要的 `depends_on`
3. **預構建鏡像**: 避免每次啟動都構建

## 安全建議

1. **不要在 Git 提交 `.env` 文件**
2. **使用 Docker secrets** (生產環境):
   ```yaml
   secrets:
     postgres_password:
       file: ./secrets/postgres_password.txt
   ```

3. **限制容器權限**:
   ```yaml
   security_opt:
     - no-new-privileges:true
   ```

4. **定期更新基礎鏡像**:
   ```bash
   docker-compose pull
   docker-compose up -d
   ```

## 常見問題

### Q: 如何只啟動部分服務?

```bash
# 只啟動 Discord Bot
docker-compose up -d postgres discord-bot
```

### Q: 如何重置資料庫?

```bash
# 停止並刪除 volumes
docker-compose down -v

# 重新啟動
docker-compose up -d
```

### Q: 如何在不停止服務的情況下更新代碼?

```bash
# 重新構建
docker-compose build discord-bot

# 重新創建容器 (會有短暫停機)
docker-compose up -d --no-deps --build discord-bot
```

### Q: Docker 和本地開發可以同時運行嗎?

可以,但需要:
1. 使用不同的端口
2. 修改 `.env` 中的 URL
3. 確保資料庫連接正確

## 參考資料

- [Docker Compose 文件參考](https://docs.docker.com/compose/compose-file/)
- [Docker 最佳實踐](https://docs.docker.com/develop/dev-best-practices/)
- [環境變數配置指南](./environment-setup.md)
