"""Discord test configuration — mirrors the discord bot's runtime sys.path."""

import sys
from pathlib import Path

# The discord bot runs from backend/discord/ with that directory in sys.path,
# so modules like `core`, `cogs`, and `database` are importable as top-level.
DISCORD_DIR = Path(__file__).parent.parent.parent / "discord"

if str(DISCORD_DIR) not in sys.path:
    sys.path.insert(0, str(DISCORD_DIR))
