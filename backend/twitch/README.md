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
https://id.twitch.tv/oauth2/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=http%3A%2F%2Flocalhost%3A4343%2Foauth%2Fcallback&response_type=code&scope=channel%3Abot+channel%3Amanage%3Aredemptions+channel%3Aread%3Aredemptions+channel%3Amanage%3Avips+moderator%3Aread%3Afollowers+channel%3Aread%3Asubscriptions+moderator%3Amanage%3Achat_messages+moderator%3Aread%3Achatters+channel%3Aread%3Ahype_train+channel%3Aread%3Apolls+channel%3Aread%3Apredictions+bits%3Aread
```

### 4. 啟動

```bash
python main.py
```

## 可用指令

### 一般指令
- `!hi` / `!hello` - 打招呼
- `!uptime` - 查看直播時長
- `!ai <問題>` - AI 對話（需配置 OpenRouter）

### 版主指令
- `!say <內容>` - 複讀訊息

### Channel Points（頻道點數）
- `!redemptions` - 查看功能說明
- `!niibot` - 取得 OAuth 授權連結（僅 Bot Owner）
- ✨ 自動監聽並記錄所有點數兌換事件
- ✨ 支援 Niibot 獎勵自動發送 OAuth URL
- ✨ 支援 VIP 獎勵自動授予 VIP 身分
- 💡 使用 Twitch 後台管理獎勵的創建/刪除

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

## 開發工具

### 類型檢查
```bash
python -m mypy main.py components/
```

### 日誌級別控制
```bash
# 開發環境 - 顯示所有訊息
LOG_LEVEL=DEBUG python main.py

# 生產環境 - 只顯示重要訊息
LOG_LEVEL=INFO python main.py
```

### Rich Logging
Bot 自動偵測並使用 [Rich](https://github.com/Textualize/rich) 提供美觀的終端輸出：
- ✅ 彩色日誌
- ✅ 美化的 traceback
- ✅ 自動降級到標準格式（未安裝 Rich 時）

## 注意事項

- ⚠️ `.env` 絕不要提交到版本控制
- ⚠️ `CLIENT_SECRET` 必須保密
- ⚠️ Conduit 在離線 72 小時後過期
- ⚠️ 生產環境建議使用 `LOG_LEVEL=INFO`

## 文件說明

- 📖 [設定與權限指南](docs/SETUP_GUIDE.md) - OAuth 授權、Scopes、權限架構完整說明
- 🔧 [TwitchIO 3 API 使用指南](docs/TWITCHIO3_API.md) - TwitchIO 3 官方 API 正確用法、常見錯誤與修正
- 🗄️ [database/schema.sql](database/schema.sql) - PostgreSQL 資料庫初始化腳本
- 📝 [mypy.ini](mypy.ini) - 靜態類型檢查配置
