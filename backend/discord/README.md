# Niibot Discord Bot

基於 discord.py 2.x 的模組化 Discord Bot，使用現代的 Slash Commands。

## 快速開始

### 1. 安裝依賴

```bash
cd backend
pip install -r requirements.txt
```

### 2. 設定環境變數

複製 `.env.example` 為 `.env` 並填入：

```bash
# 必填
DISCORD_BOT_TOKEN=your_bot_token_here

# 選填（開發測試用）
DISCORD_GUILD_ID=your_test_server_id
```

### 3. 啟動 Bot

```bash
# 方法 1: 直接執行
python discord/bot.py

# 方法 2: 使用啟動腳本
python discord/run.py
```

## 架構說明

```
discord/
├── bot.py              # 主程式
├── run.py              # 快速啟動腳本
└── cogs/               # 功能模組
    ├── __init__.py
    ├── utility.py      # 實用工具
    ├── moderation.py   # 管理功能
    └── fun.py          # 娛樂功能
```

## Cogs 模組

### Utility (實用工具)
- `/ping` - 檢查延遲
- `/info` - 伺服器資訊
- `/userinfo` - 用戶資訊
- `/avatar` - 顯示頭像

### Moderation (管理)
- `/clear` - 清除訊息
- `/kick` - 踢出成員
- `/ban` - 封鎖成員
- `/unban` - 解除封鎖
- `/mute` - 禁言成員
- `/unmute` - 解除禁言

### Fun (娛樂)
- `/roll` - 擲骰子
- `/choose` - 隨機選擇
- `/8ball` - 神奇8號球
- `/coinflip` - 擲硬幣
- `/rps` - 猜拳遊戲
- `/fortune` - 今日運勢

## 新增 Cog

1. 在 `cogs/` 目錄創建新文件：

```python
import discord
from discord import app_commands
from discord.ext import commands

class MyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="example")
    async def example(self, interaction: discord.Interaction):
        await interaction.response.send_message("Hello")

async def setup(bot: commands.Bot):
    await bot.add_cog(MyCog(bot))
```

2. 在 `bot.py` 的 `initial_extensions` 中添加：

```python
self.initial_extensions = [
    "cogs.utility",
    "cogs.moderation",
    "cogs.fun",
    "cogs.mycog",  # 新增
]
```

## 進階功能

### 背景任務

```python
from discord.ext import tasks

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.my_task.start()

    @tasks.loop(minutes=5)
    async def my_task(self):
        # 每 5 分鐘執行
        pass
```

### 錯誤處理

```python
@app_commands.command()
async def mycommand(self, interaction: discord.Interaction):
    try:
        # 你的程式碼
        pass
    except Exception as e:
        await interaction.response.send_message(
            f"發生錯誤: {str(e)}",
            ephemeral=True
        )
```

### Context Menu (右鍵選單)

```python
@app_commands.context_menu(name="User Info")
async def user_context(self, interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f"User: {member}", ephemeral=True)
```

## 注意事項

- 斜線指令同步需要時間（測試伺服器立即，全域需1小時）
- 確保 Bot 有正確的權限（Intents 和伺服器權限）
- 使用 `ephemeral=True` 讓回應只有發起者看得到
