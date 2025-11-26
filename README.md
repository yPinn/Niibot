# TwitchIO Multi-Channel Bot

多頻道 Twitch bot，使用 PostgreSQL 儲存資料，支援 OpenRouter AI。

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![TwitchIO](https://img.shields.io/badge/TwitchIO-3.x-purple.svg)](https://twitchio.dev/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 特色

- **多頻道支援**: AutoBot + Conduit 架構
- **持久化儲存**: PostgreSQL/Supabase
- **AI 整合**: OpenRouter 多模型支援
- **動態授權**: OAuth 自動訂閱頻道
- **Channel Points**: 完整支援頻道點數兌換與管理

## 快速開始

### 1. 安裝與設定

```bash
pip install -r requirements.txt
cp .env.example .env
```

編輯 `.env` 填入：

- Twitch Client ID/Secret ([取得](https://dev.twitch.tv/console))
- Bot ID / Owner ID
- DATABASE_URL
- OpenRouter API Key

### 2. 初始化資料庫

```bash
# PostgreSQL
psql -U user -d database -f init_db.sql

# Supabase: 在 SQL Editor 執行 init_db.sql
```

### 3. OAuth 授權

將 `YOUR_CLIENT_ID` 替換為你的 Client ID：

**Bot 帳號授權**（使用 Bot 帳號登入）：

```
https://id.twitch.tv/oauth2/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=http%3A%2F%2Flocalhost%3A4343%2Foauth%2Fcallback&response_type=code&scope=user%3Aread%3Achat+user%3Awrite%3Achat+user%3Abot
```

**頻道授權**（Streamer 使用自己的帳號登入）：

```
https://id.twitch.tv/oauth2/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=http%3A%2F%2Flocalhost%3A4343%2Foauth%2Fcallback&response_type=code&scope=channel%3Abot+channel%3Amanage%3Aredemptions+channel%3Aread%3Aredemptions+moderator%3Aread%3Afollowers+channel%3Aread%3Asubscriptions+moderator%3Amanage%3Achat_messages+moderator%3Aread%3Achatters+channel%3Aread%3Ahype_train+channel%3Aread%3Apolls+channel%3Aread%3Apredictions+bits%3Aread
```

### 4. 啟動

```bash
python main.py
```

## 可用指令

### 一般指令

- `!hi` / `!hello` - 打招呼
- `!uptime` - 查看直播時長
- `!socials` - 顯示社交媒體連結
- `!ai <問題>` - AI 對話

### 版主指令

- `!say <內容>` - 複讀訊息

### Channel Points（頻道點數）

- `!redemptions` - 查看 Channel Points 功能說明
- ✨ 自動監聽並記錄所有點數兌換事件
- ✨ 根據獎勵標題執行自訂動作（可擴展）
- 💡 請使用 Twitch 後台管理獎勵的創建/刪除

### Owner 專用

- `!load <module>` - 載入模組
- `!unload <module>` - 卸載模組
- `!reload <module>` - 重載模組
- `!loaded` / `!modules` - 列出已載入模組
- `!shutdown` - 關閉 bot

## 資料庫結構

### tokens 表

- `user_id`: Twitch user ID（主鍵）
- `token`, `refresh`: OAuth tokens

### channels 表

- `channel_id`: Twitch user ID（主鍵，= broadcaster_user_id）
- `channel_name`: 小寫用戶名
- `enabled`: 啟用狀態

**重要**: 在 Twitch，channel = user，`channel_id` = `broadcaster_user_id` = `user_id`

## 技術棧

- TwitchIO v3 AutoBot
- PostgreSQL/Supabase (asyncpg)
- Twitch EventSub + Conduit
- OpenRouter AI

## 注意事項

- `.env` 勿提交版本控制
- Conduit 在離線 72 小時後過期
- DATABASE_URL 格式: `postgresql://user:password@host:port/database`

## 文件說明

- 📖 [設定與權限指南](docs/SETUP_GUIDE.md) - OAuth 授權、Scopes、權限架構完整說明
- 🗄️ [database/schema.sql](database/schema.sql) - PostgreSQL 資料庫初始化腳本
