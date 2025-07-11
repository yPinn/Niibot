# CLAUDE.md

此文件為 Claude Code (claude.ai/code) 在此程式庫中工作時提供指導。

## 專案概述 Project Overview

Niibot 是一個多平台機器人專案，支援 Discord 和 Twitch 平台。採用模組化架構，透過配置文件支援本機開發和生產環境。

### 架構特色
- **多平台支援** - Discord Bot + Twitch Bot
- **統一啟動器** - `main.py` 統一管理兩個平台
- **模組化配置** - 分離的配置文件系統
- **版本管理** - 明確的版本控制和相容性

## 指令 Commands

### 執行機器人
```bash
# Discord Bot
python main.py discord --env local

# Twitch Bot  
python main.py twitch --env local

# 同時啟動兩個Bot
python main.py both --env local
```

### 安裝依賴套件
```bash
# 安裝主要依賴
pip install -r requirements-launcher.txt

# Discord Bot 依賴
pip install -r discord-bot/requirements.txt

# Twitch Bot 依賴  
pip install -r twitch-bot/requirements.txt
```

### 程式碼品質檢查
```bash
# 語法檢查
python3 -m py_compile main.py
python3 -m py_compile twitch-bot/bot.py

# 程式碼格式化 (如果有安裝dev工具)
black .
flake8 .
```

## 架構說明 Architecture

### 配置系統 Configuration System
- **模組化配置** - 新的模組化配置系統，為不同組件使用獨立檔案
- `config/shared/common.env` - 共用配置（環境設定、API 金鑰）
- `config/discord/bot.env` - Discord Bot 基本配置
- `config/discord/features.env` - Discord Bot 功能配置
- `config/twitch/bot.env` - Twitch Bot 基本配置（TwitchIO 2.x）
- `config/twitch/features.env` - Twitch Bot 功能配置
- `shared/config/modular_config.py` - 統一配置管理器，支援模組化載入
- 環境由 `BOT_ENV` 環境變數決定（預設為 "local"）

### 專案結構
```
niibot/
├── main.py                 # 統一啟動器
├── shared/                 # 共用模組
│   └── config/            # 配置管理
├── discord-bot/           # Discord Bot
│   ├── bot.py            # Discord Bot 主程式
│   └── cogs/             # Discord 功能模組
├── twitch-bot/            # Twitch Bot  
│   ├── bot.py            # Twitch Bot 主程式 (TwitchIO 2.x)
│   └── utils/            # Twitch 工具模組
└── config/                # 配置文件
    ├── shared/           # 共用配置
    ├── discord/          # Discord 配置
    └── twitch/           # Twitch 配置
```

## Twitch Bot 架構 (TwitchIO 2.x)

### 版本資訊
- **TwitchIO 版本**: 2.9.1 (穩定版)
- **連線方式**: WebSocket + IRC
- **認證方式**: OAuth Token

### 初始化參數
```python
# TwitchIO 2.x 簡化格式
super().__init__(
    token=bot_token,           # OAuth Token (必需)
    prefix=command_prefix,     # 指令前綴 (必需)
    initial_channels=channels  # 初始頻道 (必需)
)
```

### 配置需求
```env
# 最小必要配置
BOT_TOKEN=oauth:your_token_here
BOT_NICK=your_bot_username  
COMMAND_PREFIX=?
INITIAL_CHANNELS=target_channel

# 可選配置
ADMIN_USERS=admin1,admin2
MODERATOR_USERS=mod1,mod2
LOG_LEVEL=INFO
LOG_TO_FILE=true
DATA_PATH=data
```

### Token 獲取
1. 前往 [Twitch Token Generator](https://twitchtokengenerator.com/)
2. 輸入應用程式的 Client ID
3. 選擇權限：`chat:read`, `chat:edit`
4. 用機器人帳號授權獲取Token
5. 複製Token（格式：`oauth:xxxxx`）

### 可用指令
- `?test` - 測試連線狀態
- `?help` - 顯示幫助訊息
- `?ping` - Ping測試
- `?info` - 顯示機器人資訊
- `?eat [分類]` - 隨機推薦食物
- `?eat_categories` - 顯示餐點分類
- `?draw 選項1 選項2 ...` - 隨機抽獎
- `?draw_stats` - 抽獎統計
- `?draw_history` - 抽獎記錄

## Discord Bot 架構

### 版本資訊
- **Discord.py 版本**: 2.3.0+
- **架構**: Cog-based 模組化系統
- **指令支援**: 傳統指令 + Slash指令

### 主要功能
- **Reply System** - Copycat功能
- **Party System** - 分隊系統
- **Clock System** - 個人化打卡
- **Draw/Eat System** - 抽獎和用餐推薦
- **Twitter Monitor** - 社交媒體監控

## 開發注意事項 Development Notes

### 重要規則
- **繁體中文介面** - 所有使用者介面和訊息使用繁體中文
- **版本相容性** - 嚴格遵循各套件的版本需求
- **配置分離** - 開發和生產環境使用不同配置
- **錯誤處理** - 完整的錯誤處理和日誌記錄

### TwitchIO 版本注意事項
- **使用 TwitchIO 2.x** - 穩定且成熟的版本
- **避免 TwitchIO 3.x** - 新技術但尚未穩定
- **參數簡化** - 只需要Token、Prefix、Channels三個基本參數
- **不需要HTTP服務器** - TwitchIO 2.x不需要Web伺服器

### 配置最佳實踐
1. **複製範本** - 從 `.env.example` 複製建立實際配置
2. **檢查必要欄位** - 確保所有必要參數都已設定
3. **測試連線** - 使用測試指令確認功能正常
4. **版本鎖定** - requirements.txt 使用明確版本號

## 部署 Deployment

### 本地開發
```bash
# 設定環境
export BOT_ENV=local

# 啟動Twitch Bot
python main.py twitch --env local
```

### 生產環境
```bash
# 設定環境
export BOT_ENV=prod

# 更新配置檔案
# 使用生產環境的Token和設定

# 啟動服務
python main.py twitch --env prod
```

### 依賴管理
- `requirements-launcher.txt` - 主要啟動器依賴
- `twitch-bot/requirements.txt` - Twitch Bot專用依賴
- `discord-bot/requirements.txt` - Discord Bot專用依賴

### 版本控制
所有套件版本都已鎖定在 requirements 檔案中：
- `twitchio==2.9.1` - 穩定的2.x版本
- `discord.py>=2.3.0` - Discord API支援
- 其他依賴套件使用語意化版本範圍

## 故障排除 Troubleshooting

### 常見問題

**Twitch Bot 無法連線**
1. 檢查Token格式是否正確（包含`oauth:`前綴）
2. 確認Token權限包含 `chat:read` 和 `chat:edit`
3. 檢查目標頻道名稱拼寫
4. 確認使用正確的TwitchIO版本（2.9.1）

**配置檔案錯誤**
1. 確認檔案路徑正確
2. 檢查環境變數 `BOT_ENV` 設定
3. 驗證必要欄位都已填寫
4. 確認沒有多餘的TwitchIO 3.x參數

**版本衝突**
1. 檢查實際安裝的套件版本
2. 重新安裝正確版本的依賴
3. 清理Python快取和重新啟動

## 最近更新 Recent Updates

- **TwitchIO 降級** - 從3.x降級到2.9.1穩定版
- **配置簡化** - 移除不必要的3.x參數
- **文檔更新** - 完整的架構和使用說明
- **範本更新** - 所有配置範本已更新為2.x格式
- **版本鎖定** - 統一所有requirements檔案版本