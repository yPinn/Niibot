# Niibot Twitch Bot

TwitchIO 3.x 多頻道 Bot，支援 EventSub。部署於 Render (Docker)。

## 啟動

```bash
cp .env.example .env
uv sync && uv run python main.py
```

初次設定需執行 `database/schema.sql` 建立資料表。

## 指令

**一般**
- `!hi` — 打招呼
- `!help` — 指令列表
- `!uptime` — 直播時長
- `!ai <問題>` — AI 對話
- `!運勢` — 今日運勢
- `!rk` — TFT 排名查詢
- `!redemptions` — Channel Points 兌換資訊

**Owner**
- `!load / !unload / !reload <module>`
- `!loaded` — 列出已載入模組
- `!shutdown` — 關閉 Bot

## Channel Points (EventSub)

自動監聽點數兌換事件：Niibot 獎勵、VIP 獎勵、搶第一獎勵。
