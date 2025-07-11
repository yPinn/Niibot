# Niibot - 雙平台機器人系統

一個同時支援 Discord 和 Twitch 的功能豐富機器人系統。

## 🏗️ 架構總覽

採用分區架構設計，將 Discord Bot 和 Twitch Bot 分別維護，確保各平台功能的穩定性和可擴展性。

```
niibot/
├── discord-bot/     # Discord Bot (完整功能)
├── twitch-bot/      # Twitch Bot (輕量化設計)
├── shared/          # 共用模組 (按需添加)
├── tools/           # 開發工具
├── logs/            # 統一日誌
└── docs/            # 文檔
```

## 🚀 快速開始

### Discord Bot
```bash
cd discord-bot
pip install -r requirements.txt
python bot.py
```

### Twitch Bot
```bash
cd twitch-bot
pip install -r requirements.txt
# 設定環境變數後
python bot.py
```

## 📋 主要功能

### Discord Bot
- 完整的 cogs 系統
- 豐富的 UI 交互組件
- 個人化打卡系統
- 分隊語音管理
- Twitter 監控
- 用餐推薦、抽獎系統

### Twitch Bot
- 輕量化指令系統
- 基礎用餐推薦
- 冷卻機制
- 權限管理
- 支援未來擴展

## 🔧 開發說明

### 設計原則
- **分區不分離** - 清晰邊界，靈活互動
- **輕量化設計** - Twitch Bot 專注核心功能
- **穩定擴展** - 支援未來功能添加
- **實用主義** - 優先考慮可工作性

### 分別運營
如需分別運營，只需：
1. 複製對應的 `discord-bot/` 或 `twitch-bot/` 資料夾
2. 複製必要的 `shared/` 模組
3. 獨立部署

## 📊 版本資訊

- **架構版本**: 2.0 (分區架構)
- **Discord Bot**: 保持原有完整功能
- **Twitch Bot**: 輕量化初始版本
- **最後更新**: 2025-01-09

---

**開發者**: yPinn  
**分支**: twitch (基於 Claude 分支)  
**部署**: 支援多種雲端平台