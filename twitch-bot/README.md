# Niibot Twitch Bot

Niibot 的 Twitch 平台實現，使用 TwitchIO 2.x 穩定版本，專注於核心功能的穩定實現。

## 🏗️ 架構特色

- **TwitchIO 2.x** - 使用穩定且成熟的2.9.1版本
- **簡化連線** - 只需OAuth Token即可運行
- **模組化設計** - 清晰的功能分離和管理
- **完整功能** - 支援聊天互動和資料管理

## 📋 功能列表

### 🤖 核心指令
- `?test` - 測試 bot 狀態
- `?help` - 顯示指令說明
- `?ping` - Pong!
- `?info` - 顯示 bot 資訊

### 🍽️ 用餐推薦
- `?eat [分類]` - 隨機推薦食物
- `?eat_categories` - 顯示餐點分類

### 🎲 抽獎功能
- `?draw 選項1 選項2 ...` - 隨機抽獎
- `?draw 選項1*權重1 選項2*權重2` - 權重抽獎
- `?draw_stats` - 抽獎統計
- `?draw_history` - 抽獎記錄

## 🚀 快速開始

### 安裝依賴
```bash
pip install -r requirements.txt
```

### Token 配置

**步驟 1：獲取 Twitch Token**
1. 前往 [Twitch Token Generator](https://twitchtokengenerator.com/)
2. 輸入你的 Twitch 應用程式 Client ID
3. 選擇權限：`chat:read`, `chat:edit`
4. 用機器人帳號登入並授權
5. 複製生成的Token（格式：`oauth:xxxxx`）

**步驟 2：設定配置檔案**
```bash
# 從範本複製配置檔案
cp ../config/twitch/bot.env.example ../config/twitch/bot.env

# 編輯配置檔案，填入你的Token和設定
# BOT_TOKEN=oauth:your_token_here
# BOT_NICK=your_bot_username
# INITIAL_CHANNELS=target_channel_name
```

### 執行 Bot
```bash
# 從專案根目錄執行
cd ..
python main.py twitch --env local

# 或直接執行bot.py
cd twitch-bot
python bot.py
```

## ⚙️ 配置說明

### 必要配置 (TwitchIO 2.x)
- `BOT_TOKEN` - Twitch OAuth Token（必需）
- `BOT_NICK` - Bot 使用者名稱
- `COMMAND_PREFIX` - 指令前綴 (預設: ?)
- `INITIAL_CHANNELS` - 初始加入的頻道

### 可選配置
- `ADMIN_USERS` - 管理員用戶清單
- `MODERATOR_USERS` - 版主用戶清單
- `LOG_LEVEL` - 日誌級別 (預設: INFO)
- `LOG_TO_FILE` - 是否記錄到檔案 (預設: true)
- `DATA_PATH` - 資料檔案路徑 (預設: data)

## 🏗️ 架構說明

### TwitchIO 2.x 特色
- **簡化連線** - 只需 OAuth Token 即可運行
- **穩定可靠** - 成熟的 2.9.1 版本，大量社群支援
- **WebSocket + IRC** - 高效能的聊天連線方式
- **內建指令系統** - 完整的指令處理框架

### 目錄結構
```
twitch-bot/
├── bot.py              # 主程式 (TwitchIO 2.x)
├── utils/              # 工具模組
│   ├── data_manager.py # 資料管理
│   ├── logger.py       # 日誌系統
│   └── cooldown.py     # 冷卻管理
├── data/               # 資料檔案
│   ├── eat.json        # 用餐推薦資料
│   └── draw_history.json # 抽獎記錄
└── requirements.txt    # 依賴套件
```

### 功能實現
- **內建指令** - 直接在 bot.py 中實現所有指令
- **資料管理** - JSON 格式的簡單資料儲存
- **日誌系統** - 完整的操作記錄和除錯資訊
- **權限控制** - 管理員和版主權限管理

### 連線架構
```python
# TwitchIO 2.x 簡化初始化
super().__init__(
    token=bot_token,           # OAuth Token
    prefix=command_prefix,     # 指令前綴
    initial_channels=channels  # 初始頻道
)
```

## 🔧 開發說明

### 添加新指令
1. 在 `bot.py` 中添加新的 `@commands.command()` 方法
2. 實作指令邏輯和錯誤處理
3. 更新日誌記錄和權限檢查

### 測試方法
```bash
# 測試 bot 啟動
python bot.py

# 或使用統一啟動器
python ../main.py twitch --env local

# 在Twitch聊天室中測試指令
?test
?help
```

### 除錯工具
- 查看日誌：`../logs/twitch.log`
- 檢查連線狀態：查看控制台輸出
- 驗證Token：確認 `Successfully logged onto Twitch WS` 訊息

## 🎯 版本資訊

- **TwitchIO 版本**: 2.9.1 (穩定版)
- **Python 版本**: 3.7+
- **主要依賴**: `twitchio==2.9.1`, `aiofiles`
- **最後更新**: 2025-01-11

## 🐛 故障排除

### 常見問題

**1. Token 錯誤**
```
Invalid or unauthorized Access Token passed
```
- 解決：重新生成有效的 OAuth Token
- 確認Token格式包含 `oauth:` 前綴

**2. 連線失敗**
```
Bot.__init__() missing arguments
```
- 解決：確認使用 TwitchIO 2.x 格式參數
- 檢查是否有多餘的 3.x 參數

**3. 無法加入頻道**
- 檢查頻道名稱拼寫（不包含 # 符號）
- 確認機器人帳號有聊天權限

### 除錯步驟
1. 檢查日誌檔案 `../logs/twitch.log`
2. 確認配置檔案格式正確
3. 驗證 TwitchIO 版本：`pip list | grep twitchio`
4. 測試基本指令：`?test`, `?ping`

## 📋 配置範例

```env
# 最小配置範例
BOT_TOKEN=oauth:your_token_here
BOT_NICK=your_bot_username
COMMAND_PREFIX=?
INITIAL_CHANNELS=target_channel

# 可選配置
ADMIN_USERS=admin1,admin2
LOG_LEVEL=INFO
LOG_TO_FILE=true
```

---

**架構版本**: TwitchIO 2.x 穩定版  
**維護狀態**: 穩定運行  
**更新日期**: 2025-01-11