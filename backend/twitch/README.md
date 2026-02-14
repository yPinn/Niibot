# Niibot Twitch Bot

TwitchIO 3.x 多頻道 Bot，支援 EventSub。部署於 Render (Docker)。

## 啟動

```bash
cp .env.example .env
uv sync && uv run python main.py
```

初次設定需執行 `scripts/db_migrate.py` 建立資料表。

## 指令

**一般**
- `!hi` — 打招呼（別名 `!hello`、`!hey`）
- `!help` — 指令列表（別名 `!commands`）
- `!uptime` — 直播時長
- `!ai <問題>` — AI 對話
- `!運勢` — 今日運勢（別名 `!fortune`、`!占卜`）
- `!rk [player#tag]` — TFT 排名查詢

**自訂指令管理**（Mod+）
- `!cmd a !name [options] text` — 新增指令
- `!cmd e !name [options] [text]` — 編輯指令
- `!cmd d !name` — 刪除指令

**Owner**
- `!comp` — 列出已載入模組
- `!comp l / u / r <module>` — 載入 / 卸載 / 重載模組
- `!comp off` — 關閉 Bot

## EventSub 事件

- **Channel Points** — Niibot 授權、VIP 獎勵、搶第一獎勵
- **Follow** — 追隨通知（24 小時防刷）
- **Subscribe** — 訂閱通知（含禮物訂閱、等級顯示）
- **Raid** — 突襲通知（可設定自動 Shoutout）
- **Stream Online / Offline** — 分析場次追蹤
