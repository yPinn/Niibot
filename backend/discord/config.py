"""Discord Bot configuration"""

import logging
import os
from pathlib import Path

import discord

logger = logging.getLogger(__name__)

DISCORD_DIR = Path(__file__).parent
BACKEND_DIR = DISCORD_DIR.parent

if str(DISCORD_DIR) == "/app":
    DATA_DIR = Path("/app/data")
else:
    DATA_DIR = BACKEND_DIR / "data"


class BotConfig:
    STATUS: str = os.getenv("DISCORD_STATUS", "")
    ACTIVITY_TYPE: str = os.getenv("DISCORD_ACTIVITY_TYPE", "")
    ACTIVITY_NAME: str = os.getenv("DISCORD_ACTIVITY_NAME", "")
    ACTIVITY_URL: str = os.getenv("DISCORD_ACTIVITY_URL", "")

    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_WARNING_THRESHOLD: float = float(os.getenv("RATE_LIMIT_WARNING_THRESHOLD", "0.7"))
    RATE_LIMIT_CRITICAL_THRESHOLD: float = float(os.getenv("RATE_LIMIT_CRITICAL_THRESHOLD", "0.9"))

    @classmethod
    def get_status(cls) -> discord.Status:
        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }
        return status_map.get(cls.STATUS.lower(), discord.Status.online)

    @classmethod
    def get_activity(cls) -> discord.Activity | discord.Streaming | None:
        """Get bot activity from environment variables

        Supports: playing, listening, watching, competing, streaming
        For streaming: DISCORD_ACTIVITY_URL must be a valid Twitch URL
        """
        if not cls.ACTIVITY_NAME:
            return None

        activity_type_lower = cls.ACTIVITY_TYPE.lower()

        if activity_type_lower == "streaming":
            if not cls.ACTIVITY_URL:
                logger.warning(
                    "Streaming activity requires DISCORD_ACTIVITY_URL to be set. "
                    "Falling back to 'playing' activity."
                )
                return discord.Activity(
                    type=discord.ActivityType.playing,
                    name=cls.ACTIVITY_NAME
                )

            if not cls.ACTIVITY_URL.startswith("https://twitch.tv/"):
                logger.warning(
                    f"Streaming activity URL must be a valid Twitch URL (https://twitch.tv/*). "
                    f"Got: {cls.ACTIVITY_URL}. Falling back to 'playing' activity."
                )
                return discord.Activity(
                    type=discord.ActivityType.playing,
                    name=cls.ACTIVITY_NAME
                )

            return discord.Streaming(name=cls.ACTIVITY_NAME, url=cls.ACTIVITY_URL)

        activity_map = {
            "playing": discord.ActivityType.playing,
            "listening": discord.ActivityType.listening,
            "watching": discord.ActivityType.watching,
            "competing": discord.ActivityType.competing,
        }

        activity_type = activity_map.get(
            activity_type_lower, discord.ActivityType.playing)
        return discord.Activity(type=activity_type, name=cls.ACTIVITY_NAME)
