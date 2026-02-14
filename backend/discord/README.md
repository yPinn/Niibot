# Niibot Discord Bot

discord.py 2.x Slash Commands Bot。部署於 Render (Docker)。

## 啟動

```bash
cp .env.example .env
uv sync && uv run python bot.py
```

## 指令

**Owner**
- `/reload`, `/load`, `/unload`, `/cogs`, `/sync`

**管理員**
- `/clear`, `/kick`, `/ban`, `/unban`, `/mute`, `/unmute`
- `/setlog`, `/unsetlog` — 事件日誌頻道
- `/rate_stats`, `/rate_check` — API 速率監控

**一般**
- `/ping`, `/version`, `/info`, `/userinfo`, `/avatar`, `/help`
- `/rps`, `/roll`, `/choose`, `/coinflip`, `/roulette`
- `/fortune`, `/tarot`, `/giveaway`, `/tft`
- `/ai` — AI 對話
- `/eat` — 隨機推薦餐點
- `/food cat|show|add|remove|delete` — 餐點管理
- `/bday menu|init` — 生日系統
