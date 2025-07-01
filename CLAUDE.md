# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
此文件為 Claude Code (claude.ai/code) 在此程式庫中工作時提供指導。

## Project Overview 專案概述

Niibot is a feature-rich Discord bot written in Python using discord.py. The bot uses a cog-based architecture for modular functionality and supports both local development and production environments through configuration files. It includes comprehensive features like automated moderation, entertainment systems, social media integration, and personalized user experiences.

Niibot 是使用 discord.py 開發的功能豐富 Python Discord 機器人。機器人採用基於 cog 的模組化架構，透過配置文件支援本機開發和生產環境。包含完整的自動化管理、娛樂系統、社交媒體整合和個人化用戶體驗功能。

## Commands 指令

**Running the bot 執行機器人:**
```bash
python bot.py
```

**Installing dependencies 安裝依賴套件:**
```bash
# 生產環境
pip install -r requirements.txt

# 開發環境（包含程式碼品質工具）
pip install -r requirements-dev.txt
```

**Testing and syntax checking 測試和語法檢查:**
```bash
python3 -m py_compile bot.py
python3 -m py_compile cogs/[module_name].py
```

**Code quality tools 程式碼品質工具:**
```bash
black .                    # 代碼格式化
flake8 .                  # 代碼風格檢查
pytest                    # 運行測試
```

## Architecture 架構

### Configuration System 配置系統
- `config_local.py` - Local development configuration (uses .env file)  
  本機開發配置（使用 .env 文件）
- `config_prod.py` - Production configuration (uses environment variables with validation)  
  生產環境配置（使用環境變數並進行驗證）
- `utils/config_manager.py` - Centralized configuration management with singleton pattern  
  集中式配置管理，採用單例模式
- Environment determined by `BOT_ENV` environment variable (defaults to "local")  
  環境由 `BOT_ENV` 環境變數決定（預設為 "local"）

### Bot Structure 機器人結構
- `bot.py` - Main bot entry point with dynamic cog loading and slash command support  
  主要機器人進入點，具備動態 cog 載入功能和斜線指令支援
- `cogs/` - Modular command and event handlers  
  模組化指令和事件處理器
- `utils/util.py` - Shared utilities for text processing, time handling, JSON I/O, and Discord activities  
  文字處理、時間處理、JSON I/O 和 Discord 活動的共用工具
- `data/` - JSON data storage directory with automatic backup support  
  JSON 資料儲存目錄，支援自動備份
- `keep_alive.py` - Flask server for keeping bot alive in production with dynamic port allocation  
  Flask 伺服器用於在生產環境中保持機器人運行，支援動態埠號分配
- `utils/logger.py` - Centralized logging system with different levels and optional file output  
  集中式日誌系統，支援不同級別和可選檔案輸出

### Key Components 核心組件

**Cog System Cog 系統:**
- All cogs are automatically loaded from the `cogs/` directory  
  所有 cog 會自動從 `cogs/` 目錄載入
- Dynamic loading/unloading commands: `?l`, `?u`, `?rl`, `?rla` (load, unload, reload, reload all)  
  動態載入/卸載指令：`?l`, `?u`, `?rl`, `?rla`（載入、卸載、重新載入、重新載入全部）
- Main cogs include: reply (copycat), party (team management), listener (message handling), eat, draw, clock (personal), clear, emojitool, repo, tinder, twitter_monitor  
  主要 cog 包括：reply（copycat）、party（隊伍管理）、listener（訊息處理）、eat、draw、clock（個人化）、clear、emojitool、repo、tinder、twitter_monitor

**Slash Command Support 斜線指令支援:**
- Full slash command integration with `/help` command for listing all available slash commands  
  完整斜線指令整合，包含 `/help` 指令列出所有可用斜線指令
- Automatic command registration and synchronization with `?sync` command  
  自動指令註冊和同步，使用 `?sync` 指令
- Mixed traditional (`?`) and slash (`/`) command support  
  支援傳統（`?`）和斜線（`/`）指令混合使用

**Event Handling 事件處理:**
- `listener.py` implements a centralized message handling system  
  `listener.py` 實作集中式訊息處理系統
- Cogs can implement `handle_on_message()` method to receive all messages  
  Cog 可以實作 `handle_on_message()` 方法來接收所有訊息
- Prevents need for multiple `@commands.Cog.listener()` decorators  
  避免需要多個 `@commands.Cog.listener()` 裝飾器

**Enhanced Copycat System (`reply.py`) 增強版Copycat系統:**
- Interactive toggle between server-specific and global user assets (avatars/banners)  
  伺服器專用和全域用戶資產（頭像/橫幅）的互動式切換
- Intelligent server-first priority for Nitro users  
  Nitro 用戶的智能伺服器優先邏輯
- Single-button toggle interface with permission controls  
  單一按鈕切換介面，包含權限控制
- Consistent asset pairing (avatar + banner from same source)  
  一致的資產配對（頭像和橫幅來自同一來源）

**Party System (`party.py` + `party_modules/`) 分隊系統:**
- Modularized architecture with separate components for different responsibilities  
  模組化架構，不同職責分離到獨立組件
- `party_modules/state_manager.py` - Guild-specific party state management with async locks  
  公會特定的分隊狀態管理，使用非同步鎖定機制
- `party_modules/team_divider.py` - Intelligent team division algorithms with multiple modes  
  智能分隊演算法，支援多種分隊模式
- `party_modules/voice_manager.py` - Dynamic voice channel creation and automatic cleanup  
  動態語音頻道建立和自動清理機制
- Persistent queue system with interactive UI using Discord Views/Modals  
  使用 Discord Views/Modals 的持久化佇列系統和互動式 UI
- Real-time voice channel monitoring with 30-second cleanup cycles  
  即時語音頻道監控，30秒清理週期
- Support for moving players between voice channels (requires manage_channels and move_members permissions)  
  支援在語音頻道間移動玩家（需要 manage_channels 和 move_members 權限）

**Personal Clock System (`clock.py`) 個人化打卡系統:**
- Completely personalized clock-in system with individual user settings  
  完全個人化的打卡系統，支援個人用戶設定
- Automatic reminders and notifications at configured work times  
  在配置的工作時間自動提醒和通知
- Flexible time window support for clock-in operations  
  支援彈性打卡時間窗口
- Accurate work hour calculation and lateness detection  
  準確的工時計算和遲到檢測
- Beautiful UI with consistent color scheme and clear information hierarchy  
  美觀界面，統一色彩系統和清晰資訊層次

**Twitter/X Monitoring System (`twitter_monitor.py`) Twitter/X監控系統:**
- Automated monitoring of specified X (Twitter) accounts with new post detection  
  自動監控指定 X（Twitter）帳號的新貼文檢測
- Intelligent translation using Google Translate API to Traditional Chinese  
  使用 Google Translate API 智能翻譯為繁體中文
- Complete media support including images and video previews  
  完整媒體支援，包括圖片和影片預覽
- Beautiful Discord embed presentation with Twitter branding  
  美觀的 Discord embed 呈現，包含 Twitter 品牌元素
- Deduplication mechanism to prevent duplicate posts  
  去重機制防止重複發送貼文
- Comprehensive debugging tools: `/twitter_debug`, `/twitter_test`, `/twitter_force_check`  
  完整調試工具：`/twitter_debug`, `/twitter_test`, `/twitter_force_check`

### Utilities (`utils/util.py`) 工具程式

**Key Functions 核心函數:**
- `read_json()` / `write_json()` - Async JSON file operations with error handling and backup support  
  非同步 JSON 檔案操作，具備錯誤處理和備份支援
- `create_activity()` - Discord bot status/activity creation  
  Discord 機器人狀態/活動建立
- `get_deployment_info()` - Deployment environment information for debugging  
  部署環境資訊，用於除錯目的
- `Cooldown` class - Simple per-user cooldown system with configurable timeouts  
  簡單的每用戶冷卻系統，可配置超時時間
- Time utilities with timezone support (defaults to UTC+8)  
  時間工具，支援時區（預設 UTC+8）
- Text processing helpers for command parsing and validation  
  指令解析和驗證的文字處理輔助函數

### Configuration Variables 配置變數
- `TOKEN` - Discord bot token (required)  
  Discord 機器人令牌（必要）
- `COMMAND_PREFIX` - Bot command prefixes (list, defaults: `["?", "❓"]` local, `["?"]` prod)  
  機器人指令前綴（列表，預設：本機 `["?", "❓"]`，生產 `["?"]`）
- `STATUS` - Bot status ("dnd" local, "online" prod)  
  機器人狀態（本機 "dnd"，生產 "online"）
- `ACTIVITY_TYPE`/`ACTIVITY_NAME`/`ACTIVITY_URL` - Bot activity settings  
  機器人活動設定
- `USE_KEEP_ALIVE` - Enable Flask server for production hosting  
  啟用 Flask 伺服器以供生產環境託管
- `TWITTER_BEARER_TOKEN` - Twitter API Bearer Token for monitoring functionality  
  Twitter API Bearer Token 用於監控功能
- `GOOGLE_TRANSLATE_API_KEY` - Google Translate API key for translation services  
  Google Translate API 金鑰用於翻譯服務

### Development Notes 開發注意事項
- Bot uses `discord.Intents.all()` for full Discord API access  
  機器人使用 `discord.Intents.all()` 以完整存取 Discord API
- Async/await pattern throughout with proper error handling  
  全面採用 Async/await 模式，具備適當錯誤處理
- Error handling with try/catch blocks and user-friendly error messages  
  使用 try/catch 區塊進行錯誤處理，並提供用戶友善的錯誤訊息
- Chinese language interface and messages  
  中文語言介面和訊息
- **IMPORTANT: Always respond in Traditional Chinese (繁體中文) when working on this codebase**  
  **重要：在處理此程式庫時，請一律使用繁體中文回覆**
- Interactive UI components using Discord Views, Buttons, and Modals  
  使用 Discord Views、Buttons 和 Modals 的互動式 UI 組件
- Comprehensive logging system for debugging and monitoring  
  完整的日誌系統用於除錯和監控

### Deployment 部署
- Production environment requires `BOT_ENV=prod` environment variable  
  生產環境需要設定 `BOT_ENV=prod` 環境變數
- TOKEN validation prevents bot startup with invalid/empty tokens  
  TOKEN 驗證機制可防止使用無效或空白 token 啟動機器人
- Dynamic port allocation supports various hosting platforms (Render, Railway, etc.)  
  動態埠號分配支援各種託管平台（Render、Railway 等）
- `runtime.txt` specifies Python version for deployment platforms  
  `runtime.txt` 指定部署平台的 Python 版本
- Deployment information available via `?test` command for debugging  
  可透過 `?test` 指令取得部署資訊以供除錯
- Absolute path usage ensures consistent file loading across different environments  
  使用絕對路徑確保在不同環境中檔案載入的一致性
- Support for various cloud platforms with automatic health check endpoints  
  支援各種雲端平台，具備自動健康檢查端點

### Code Quality 程式碼品質
- Use `requirements-dev.txt` for development tools (black, flake8, pytest)  
  使用 `requirements-dev.txt` 安裝開發工具（black、flake8、pytest）
- Dependency versions use semantic versioning ranges for stability  
  依賴套件版本使用語意化版本範圍以確保穩定性
- Comprehensive error handling and logging throughout the codebase  
  整個程式庫具備完整的錯誤處理和日誌記錄
- Modular design with clear separation of concerns  
  模組化設計，清晰的關注點分離
- Type hints and documentation for better code maintainability  
  類型提示和文檔以提高程式碼可維護性

### Recent Updates 最近更新
- **Enhanced Copycat System**: Server/global asset toggle with intelligent priority  
  **增強Copycat系統**：伺服器/全域資產切換，具備智能優先級
- **Slash Command Integration**: Complete `/help` command system for slash commands  
  **斜線指令整合**：完整的斜線指令 `/help` 指令系統
- **Module Cleanup**: Removed duplicate repo functionality, simplified architecture  
  **模組清理**：移除重複repo功能，簡化架構
- **Twitter Monitoring**: Full X platform monitoring with translation and media support  
  **Twitter監控**：完整X平台監控，支援翻譯和媒體
- **Personalized Clock**: Complete overhaul of clock system for individual user settings  
  **個人化打卡**：打卡系統完全改版，支援個人用戶設定

### API Integrations API整合
- **Discord API**: Full bot functionality with slash commands, embeds, UI components  
  **Discord API**：完整機器人功能，包含斜線指令、embeds、UI組件
- **Twitter API v2**: Social media monitoring with Essential access tier support  
  **Twitter API v2**：社交媒體監控，支援 Essential 存取層級
- **Google Translate API**: Automatic text translation with Traditional Chinese support  
  **Google Translate API**：自動文字翻譯，支援繁體中文
- **HTTP/HTTPS**: Robust HTTP client for external API communications  
  **HTTP/HTTPS**：穩健的 HTTP 客戶端用於外部 API 通訊