# Niibot Discord Bot

Discord bot built with discord.py 2.x using Slash Commands.

## Structure

```
discord/
├── bot.py                    # Main bot client
├── config.py                 # Configuration and environment detection
├── http_server.py            # HTTP health check server (Render deployment)
├── rate_limiter.py           # Rate limit monitoring
├── run.py                    # Quick start script
└── cogs/
    ├── admin.py              # Bot management commands
    ├── moderation.py         # Moderation tools
    ├── utility.py            # Utility commands
    ├── events.py             # Event handlers
    ├── fortune.py            # Fortune telling
    ├── giveaway.py           # Giveaway management
    ├── games.py              # Games (RPS, etc.)
    ├── eat.py                # Food commands
    └── rate_limit_monitor.py # Rate limit monitoring cog
```

## Quick Start

### Local Development

```bash
cd backend/discord
python bot.py
```

### Environment Variables

Create `backend/discord/.env`:

```env
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_GUILD_ID=your_test_server_id  # Optional, for faster command sync
DISCORD_STATUS=dnd  # online, idle, dnd, invisible
DISCORD_ACTIVITY_TYPE=streaming  # playing, streaming, listening, watching, competing
DISCORD_ACTIVITY_NAME=Rendering...
DISCORD_ACTIVITY_URL=https://twitch.tv/channel  # Required for streaming
LOG_LEVEL=INFO
```

### Render Deployment

Set environment variables:

```env
ENABLE_HTTP_SERVER=true
HTTP_PORT=8080
```

Health check endpoints:
- `GET /health` - Bot ready status
- `GET /ping` - Simple ping
- `GET /` - Service info

## Features

### Command Categories

**Admin** (Owner only)
- `/reload` - Reload cog
- `/load` - Load cog
- `/unload` - Unload cog
- `/sync` - Sync slash commands

**Moderation**
- `/clear` - Delete messages
- `/kick` - Kick member
- `/ban` / `/unban` - Ban management
- `/mute` / `/unmute` - Timeout management

**Utility**
- `/ping` - Check latency
- `/info` - Server information
- `/userinfo` - User information
- `/avatar` - Display avatar

**Games**
- `/rps` - Rock Paper Scissors
- `/roll` - Roll dice
- `/choose` - Random choice
- `/coinflip` - Flip coin

**Fun**
- `/fortune` - Daily fortune
- `/eat` - Food commands
- `/giveaway` - Giveaway management

### Rate Limit Protection

Monitors Discord API rate limits and prevents bot suspension:
- Tracks request patterns
- Warns on threshold breach
- Automatic throttling

## Adding New Cog

Create `cogs/mycog.py`:

```python
from discord import app_commands
from discord.ext import commands
import discord

class MyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="example")
    async def example(self, interaction: discord.Interaction):
        await interaction.response.send_message("Hello")

async def setup(bot: commands.Bot):
    await bot.add_cog(MyCog(bot))
```

Add to `bot.py`:

```python
self.initial_extensions = [
    ...,
    "cogs.mycog",
]
```

## Deployment

### Local

Data files stored in `backend/data/`:
- `fortune.json`
- `giveaway.json`
- `games.json`

### Docker/Render

Data files copied into image at `/app/data/` during build.

## Configuration

**Data Directory Detection**:
- Docker: `/app/data`
- Local: `backend/data/`

**Command Sync**:
- With `DISCORD_GUILD_ID`: Instant sync to test server
- Without: Global sync (up to 1 hour)

## Logging

Uses Rich for enhanced terminal logging:
- Colored output
- Timestamp display
- Exception tracebacks
- UTF-8 support on Windows
