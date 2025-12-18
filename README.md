# Niibot

多功能直播平台整合 Bot 系統，支援 Twitch 和 Discord。

## 快速開始

### 使用 Docker Compose（推薦）

```bash
# 1. 設定環境變數
cp backend/twitch/.env.example backend/twitch/.env
cp backend/discord/.env.example backend/discord/.env
cp backend/api/.env.example backend/api/.env
cp frontend/.env.example frontend/.env

# 2. 編輯 .env 文件填入必要資訊

# 3. 啟動所有服務
docker-compose up -d

# 4. 查看日誌
docker-compose logs -f
```

### 本地開發

**Backend (Python 3.11+)**
```bash
cd backend
pip install -r requirements.txt

# Twitch Bot
python twitch/main.py

# Discord Bot
python discord/bot.py

# API Server
python api/main.py
```

**Frontend (Node.js)**
```bash
cd frontend
npm install
npm run dev
```

## 專案結構

```
Niibot/
├── backend/
│   ├── twitch/      # Twitch Bot (TwitchIO)
│   ├── discord/     # Discord Bot (discord.py)
│   ├── api/         # API Server (FastAPI)
│   └── requirements.txt
├── frontend/        # React + TypeScript + Vite
├── docs/            # 文檔
└── docker-compose.yml
```

## 服務說明

### Twitch Bot
- 多頻道支援
- Channel Points 整合
- AI 對話功能
- 詳見 [backend/twitch/README.md](backend/twitch/README.md)

### Discord Bot
- Slash Commands
- 模組化 Cogs 架構
- 管理與娛樂功能
- 詳見 [backend/discord/README.md](backend/discord/README.md)

### API Server
- Twitch OAuth 認證
- JWT Token 管理
- 資料庫查詢
- 詳見 [backend/api/README.md](backend/api/README.md)

### Frontend
- React 19 + TypeScript
- Tailwind CSS + shadcn/ui
- Vite 建置工具
- 詳見 [frontend/README.md](frontend/README.md)

## 技術棧

**Backend:**
- Python 3.11+
- TwitchIO 3.x
- discord.py 2.x
- FastAPI
- PostgreSQL

**Frontend:**
- React 19
- TypeScript
- Vite
- Tailwind CSS

## 文檔

詳細文檔請參考 [docs/](docs/) 目錄。

## License

MIT License - 詳見 [LICENSE](LICENSE)
