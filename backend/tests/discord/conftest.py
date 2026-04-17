"""Discord test configuration — mirrors the discord bot's runtime sys.path.

Both backend/api/ and backend/discord/ expose a top-level `core` package.
pytest collects api/ before discord/ (alphabetical order), so api's `core` may
already be cached in sys.modules when discord tests are collected. We evict the
stale entries after inserting discord/ at the front of sys.path so the next
import resolves to discord/core/ instead.
"""

import os
import sys
from pathlib import Path

# Provide required env vars before any discord module is imported.
# DiscordBotSettings has discord_bot_token as a required Field; without this
# the module-level settings call in social_preview/constants.py would raise.
os.environ.setdefault("DISCORD_BOT_TOKEN", "test_token_ci")

# The discord bot runs from backend/discord/ with that directory in sys.path,
# so modules like `core`, `cogs`, and `database` are importable as top-level.
DISCORD_DIR = Path(__file__).parent.parent.parent / "discord"

if str(DISCORD_DIR) not in sys.path:
    sys.path.insert(0, str(DISCORD_DIR))

# Evict any api/core that was cached before this conftest ran.
for _key in list(sys.modules):
    if _key == "core" or _key.startswith("core."):
        del sys.modules[_key]
