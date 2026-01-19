# Niibot Twitch Bot

TwitchIO 3.x 多頻道 Bot。

## 啟動

```bash
cp .env.example .env
python main.py
```

## 初始化

1. 設定資料庫：執行 `database/schema.sql`
2. 產生 OAuth：`python scripts/oauth.py`
3. 啟動 Bot：`python main.py`

## 指令

**一般**
- `!hi` - 打招呼
- `!uptime` - 直播時長
- `!ai <問題>` - AI 對話
- `!運勢` - 今日運勢
- `!rk` - TFT 排名查詢

**版主**
- `!say <內容>` - 複讀訊息

**Owner**
- `!load/unload/reload <module>`
- `!loaded` - 列出模組
- `!shutdown` - 關閉 bot

## Channel Points

自動監聽點數兌換事件，支援：
- Niibot 獎勵 → 發送 OAuth URL
- VIP 獎勵 → 授予 VIP
- 搶第一獎勵 → 公告突顯
