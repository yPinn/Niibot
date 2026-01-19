# Niibot

多平台直播整合 Bot - 支援 Twitch 和 Discord。

## 快速開始

```bash
# Docker (推薦)
docker-compose up -d

# 本地開發
cd backend && pip install -r requirements.txt
cd frontend && npm install
```

## 結構

```
backend/
├── api/       # FastAPI 服務
├── twitch/    # Twitch Bot
├── discord/   # Discord Bot
frontend/      # React 前端
```

## 環境變數

複製各服務的 `.env.example` 為 `.env` 並填入設定。

## License

MIT
