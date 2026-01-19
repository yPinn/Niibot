# Niibot Discord Bot

discord.py Slash Commands Bot。

## 啟動

```bash
cp .env.example .env
python bot.py
```

## 環境變數

```env
DISCORD_BOT_TOKEN=your_token
DISCORD_GUILD_ID=test_server_id  # 可選，加快指令同步
```

## 指令

**管理** (Owner)
- `/reload`, `/load`, `/unload`, `/sync`

**管理員**
- `/clear`, `/kick`, `/ban`, `/mute`

**一般**
- `/ping`, `/info`, `/userinfo`, `/avatar`
- `/rps`, `/roll`, `/choose`, `/coinflip`
- `/fortune`, `/eat`, `/giveaway`

## 新增 Cog

```python
# cogs/mycog.py
from discord import app_commands
from discord.ext import commands

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command()
    async def hello(self, interaction):
        await interaction.response.send_message("Hello!")

async def setup(bot):
    await bot.add_cog(MyCog(bot))
```
