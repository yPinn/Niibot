# Niibot 系統架構說明

## 🏗️ 專案結構

```
niibot/
├── main.py                    # 主啟動腳本
├── README.md                  # 專案說明文檔
├── CLAUDE.md                  # Claude AI 工作指南
├── CONFIG_MIGRATION_GUIDE.md  # 配置遷移指南
├── SYSTEM_ARCHITECTURE.md     # 系統架構說明 (本文件)
├── requirements-launcher.txt  # 啟動器依賴
│
├── config/                    # 📁 模組化配置目錄
│   ├── shared/               # 共用配置
│   │   ├── common.env        # 環境設定、API金鑰
│   │   └── common.env.example
│   ├── discord/              # Discord Bot 配置
│   │   ├── bot.env          # 基本配置 (Token、狀態)
│   │   ├── bot.env.example
│   │   ├── features.env     # 功能配置 (冷卻時間等)
│   │   └── features.env.example
│   └── twitch/              # Twitch Bot 配置
│       ├── bot.env          # 基本配置 (Token、頻道)
│       ├── bot.env.example
│       ├── features.env     # 功能配置 (開關、冷卻)
│       └── features.env.example
│
├── shared/                   # 📁 共用模組
│   ├── config/
│   │   └── modular_config.py # 統一配置管理器
│   ├── constants/
│   └── utils/
│
├── discord-bot/             # 📁 Discord Bot
│   ├── bot.py              # Discord Bot 主程式
│   ├── cogs/               # Discord Bot 功能模組
│   │   ├── admin_commands.py
│   │   ├── bot_status.py
│   │   ├── clear.py
│   │   ├── clock.py        # 個人化打卡系統
│   │   ├── draw.py
│   │   ├── eat.py
│   │   ├── emojitool.py
│   │   ├── listener.py     # 訊息監聽器
│   │   ├── party.py        # 分隊系統
│   │   ├── party_modules/  # 分隊系統模組
│   │   ├── reply.py        # Copycat 系統
│   │   ├── repo.py
│   │   ├── system_commands.py
│   │   ├── tinder.py
│   │   └── twitter_monitor.py # Twitter 監控
│   ├── core/               # 核心功能
│   │   ├── command_manager.py
│   │   └── sync_manager.py
│   ├── ui/                 # 使用者介面組件
│   │   ├── components.py
│   │   └── help_system.py
│   ├── utils/              # 工具模組
│   │   ├── logger.py
│   │   └── util.py
│   ├── data/              # 資料儲存
│   ├── requirements.txt   # Discord Bot 依賴
│   ├── requirements-dev.txt
│   ├── runtime.txt
│   └── keep_alive.py     # 生產環境保活
│
├── twitch-bot/            # 📁 Twitch Bot
│   ├── bot.py            # Twitch Bot 主程式
│   ├── cogs/             # Twitch Bot 功能模組
│   │   ├── core.py
│   │   ├── draw.py
│   │   └── eat.py
│   ├── adapters/         # 功能適配器
│   │   └── twitch_eat.py
│   ├── utils/            # 工具模組
│   │   ├── cooldown.py
│   │   ├── data_manager.py
│   │   └── logger.py
│   ├── data/             # 資料儲存
│   └── requirements.txt  # Twitch Bot 依賴
│
├── bin/                  # 📁 執行腳本 (已廢棄，使用 main.py)
├── config_backup/        # 📁 配置備份
└── logs/                 # 📁 日誌檔案
```

## 🔧 核心組件

### 1. 配置管理系統

**模組化配置設計**
- **分離原則**: Discord、Twitch、共用配置分別管理
- **安全性**: 敏感資訊自動隱藏，支援環境變數覆蓋
- **靈活性**: 支援按需載入、自動類型轉換

**配置管理器 API**
```python
from shared.config.modular_config import config

# Discord 配置
token = config.get_discord_config('TOKEN')
prefix = config.get_discord_config('COMMAND_PREFIX', '?')

# Twitch 配置
bot_token = config.get_twitch_config('BOT_TOKEN')
channels = config.get_twitch_config('INITIAL_CHANNELS', [])

# 共用配置
env = config.get_shared_config('BOT_ENV', 'local')
```

### 2. Discord Bot 架構

**核心特性**
- 🎯 **Cog 系統**: 模組化功能，支援動態載入/卸載
- ⚡ **斜線指令**: 完整支援 Discord Slash Commands
- 🔄 **指令同步**: 自動同步指令到 Discord
- 📊 **狀態管理**: 智能機器人狀態和活動設定

**主要功能模組**
- **party.py**: 分隊系統，支援語音頻道管理
- **clock.py**: 個人化打卡系統
- **reply.py**: 增強版 Copycat 系統
- **twitter_monitor.py**: Twitter/X 監控與翻譯
- **emojitool.py**: 表情符號統計系統

### 3. Twitch Bot 架構

**核心特性**
- 🎮 **TwitchIO**: 基於 TwitchIO 框架
- 🔄 **模組化**: Cog 系統支援功能模組
- ⏱️ **冷卻系統**: 指令冷卻防止濫用
- 📊 **功能開關**: 可配置的功能啟用/停用

**主要功能模組**
- **draw.py**: 抽獎系統
- **eat.py**: 吃東西隨機功能
- **core.py**: 核心指令和系統功能

### 4. 啟動系統

**主啟動器 (main.py)**
```bash
# 啟動 Discord Bot
python main.py discord

# 啟動 Twitch Bot  
python main.py twitch

# 同時啟動兩個 Bot
python main.py both

# 指定環境
python main.py discord --env prod
```

## 🚀 技術架構

### 語言與框架
- **Python 3.8+**: 主要開發語言
- **discord.py**: Discord Bot 框架
- **TwitchIO**: Twitch Bot 框架
- **asyncio**: 非同步程式設計

### 資料儲存
- **JSON 檔案**: 輕量級資料儲存
- **自動備份**: 資料變更時自動備份
- **原子操作**: 確保資料一致性

### 日誌系統
- **分級日誌**: DEBUG、INFO、WARNING、ERROR
- **檔案輸出**: 可選的日誌檔案輸出
- **結構化**: 清晰的日誌格式和分類

### 安全性
- **配置分離**: 敏感資訊獨立管理
- **Token 保護**: 自動隱藏敏感資訊
- **環境隔離**: 本機/生產環境分離

## 🔄 執行流程

### 啟動流程
1. **配置載入**: 自動載入模組化配置
2. **環境檢查**: 驗證配置檔案和相依性
3. **模組初始化**: 載入對應的 Bot 模組
4. **Cog 載入**: 動態載入功能模組
5. **服務啟動**: 連線到對應平台

### 配置優先級
1. **環境變數** (最高優先級)
2. **配置檔案** (.env 檔案)
3. **預設值** (程式碼中定義)

### 錯誤處理
- **優雅降級**: 功能模組載入失敗不影響核心功能
- **詳細日誌**: 完整的錯誤追蹤和除錯資訊
- **自動恢復**: 網路中斷等問題的自動重連

## 📈 擴展性

### 新增功能模組
1. 在對應的 `cogs/` 目錄建立新檔案
2. 實作必要的指令和事件處理
3. 配置相關設定到對應的配置檔案
4. 重啟 Bot 自動載入新模組

### 新增配置選項
1. 在對應的配置檔案中新增配置項
2. 在 `.example` 檔案中提供範例
3. 在程式碼中使用配置管理器 API 存取
4. 更新文檔說明新配置項的用途

### 部署環境
- **本機開發**: `BOT_ENV=local`
- **生產環境**: `BOT_ENV=prod`
- **Docker**: 支援容器化部署
- **雲端平台**: 支援 Render、Railway 等平台

## 🛠️ 維護指南

### 定期維護
- 檢查依賴套件更新
- 監控日誌檔案大小
- 備份重要資料檔案
- 檢查 API Token 有效性

### 故障排除
- 檢查配置檔案格式和內容
- 查看日誌檔案錯誤訊息
- 驗證網路連線和 API 存取
- 測試各功能模組正常運作

### 效能最佳化
- 監控記憶體使用情況
- 最佳化資料檔案存取
- 調整冷卻時間和限制
- 優化指令回應速度