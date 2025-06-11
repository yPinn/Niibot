# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
此文件為 Claude Code (claude.ai/code) 在此程式庫中工作時提供指導。

## Project Overview 專案概述

Niibot is a Discord bot written in Python using discord.py. The bot uses a cog-based architecture for modular functionality and supports both local development and production environments through configuration files.

Niibot 是使用 discord.py 開發的 Python Discord 機器人。機器人採用基於 cog 的模組化架構，透過配置文件支援本機開發和生產環境。

## Commands 指令

**Running the bot 執行機器人:**
```bash
python bot.py
```

**Installing dependencies 安裝依賴套件:**
```bash
pip install -r requirements.txt
```

## Architecture 架構

### Configuration System 配置系統
- `config_local.py` - Local development configuration (uses .env file)  
  本機開發配置（使用 .env 文件）
- `config_prod.py` - Production configuration (uses environment variables)  
  生產環境配置（使用環境變數）
- Environment determined by `BOT_ENV` environment variable (defaults to "local")  
  環境由 `BOT_ENV` 環境變數決定（預設為 "local"）

### Bot Structure 機器人結構
- `bot.py` - Main bot entry point with dynamic cog loading  
  主要機器人進入點，具備動態 cog 載入功能
- `cogs/` - Modular command and event handlers  
  模組化指令和事件處理器
- `utils/util.py` - Shared utilities for text processing, time handling, JSON I/O, and Discord activities  
  文字處理、時間處理、JSON I/O 和 Discord 活動的共用工具
- `data/` - JSON data storage directory  
  JSON 資料儲存目錄
- `keep_alive.py` - Flask server for keeping bot alive in production (controlled by `USE_KEEP_ALIVE` config)  
  Flask 伺服器用於在生產環境中保持機器人運行（由 `USE_KEEP_ALIVE` 配置控制）

### Key Components 核心組件

**Cog System Cog 系統:**
- All cogs are automatically loaded from the `cogs/` directory  
  所有 cog 會自動從 `cogs/` 目錄載入
- Dynamic loading/unloading commands: `?l`, `?u`, `?rl` (load, unload, reload)  
  動態載入/卸載指令：`?l`, `?u`, `?rl`（載入、卸載、重新載入）
- Main cogs include: party (team management), listener (message handling), reply, eat, draw, clock, clear, emojitool, tinder  
  主要 cog 包括：party（隊伍管理）、listener（訊息處理）、reply、eat、draw、clock、clear、emojitool、tinder

**Event Handling 事件處理:**
- `listener.py` implements a centralized message handling system  
  `listener.py` 實作集中式訊息處理系統
- Cogs can implement `handle_on_message()` method to receive all messages  
  Cog 可以實作 `handle_on_message()` 方法來接收所有訊息
- Prevents need for multiple `@commands.Cog.listener()` decorators  
  避免需要多個 `@commands.Cog.listener()` 裝飾器

**Party System (`party.py`) 分隊系統:**
- Complex team division and voice channel management  
  複雜的隊伍分組和語音頻道管理
- Persistent queue system with interactive UI using Discord Views/Modals  
  使用 Discord Views/Modals 的持久化佇列系統和互動式 UI
- Auto-cleanup of empty voice channels  
  自動清理空的語音頻道
- Support for moving players between voice channels (requires manage_channels and move_members permissions)  
  支援在語音頻道間移動玩家（需要 manage_channels 和 move_members 權限）

### Utilities (`utils/util.py`) 工具程式

**Key Functions 核心函數:**
- `read_json()` / `write_json()` - Async JSON file operations with error handling  
  非同步 JSON 檔案操作，具備錯誤處理
- `create_activity()` - Discord bot status/activity creation  
  Discord 機器人狀態/活動建立
- `Cooldown` class - Simple per-user cooldown system  
  簡單的每用戶冷卻系統
- Time utilities with timezone support (defaults to UTC+8)  
  時間工具，支援時區（預設 UTC+8）
- Text processing helpers for command parsing  
  指令解析的文字處理輔助函數

### Configuration Variables 配置變數
- `TOKEN` - Discord bot token  
  Discord 機器人令牌
- `COMMAND_PREFIX` - Bot command prefixes (list, defaults: `["?", "❓"]` local, `["?"]` prod)  
  機器人指令前綴（列表，預設：本機 `["?", "❓"]`，生產 `["?"]`）
- `STATUS` - Bot status ("dnd" local, "online" prod)  
  機器人狀態（本機 "dnd"，生產 "online"）
- `ACTIVITY_TYPE`/`ACTIVITY_NAME`/`ACTIVITY_URL` - Bot activity settings  
  機器人活動設定
- `USE_KEEP_ALIVE` - Enable Flask server for production hosting  
  啟用 Flask 伺服器以供生產環境託管

### Development Notes 開發注意事項
- Bot uses `discord.Intents.all()` for full Discord API access  
  機器人使用 `discord.Intents.all()` 以完整存取 Discord API
- Async/await pattern throughout  
  全面採用 Async/await 模式
- Error handling with try/catch blocks and user-friendly error messages  
  使用 try/catch 區塊進行錯誤處理，並提供用戶友善的錯誤訊息
- Chinese language interface and messages  
  中文語言介面和訊息
- **IMPORTANT: Always respond in Traditional Chinese (繁體中文) when working on this codebase**  
  **重要：在處理此程式庫時，請一律使用繁體中文回覆**