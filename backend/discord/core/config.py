"""Discord Bot configuration"""

import logging
import os
import re
from functools import lru_cache
from pathlib import Path

import discord
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from shared.config_base import DATA_DIR, RUNTIME_DIR, BaseServiceSettings, dev_env_files

__all__ = ["DATA_DIR", "RUNTIME_DIR", "BotConfig", "DiscordBotSettings", "get_settings"]

LOGGER: logging.Logger = logging.getLogger(__name__)

_TWITCH_URL_RE = re.compile(
    r"^https://(?:www\.)?twitch\.tv/[a-zA-Z0-9][a-zA-Z0-9_]{2,23}[a-zA-Z0-9]$"
)

# Bot version — injected at build time via Docker ARG → ENV
BOT_VERSION = os.getenv("APP_VERSION", "dev")
GIT_COMMIT = os.getenv("GIT_COMMIT", "unknown")
BOT_NAME = "Niibot"

# === Path Configuration ===
CORE_DIR = Path(__file__).resolve().parent
DISCORD_DIR = CORE_DIR.parent
BACKEND_DIR = DISCORD_DIR.parent
COGS_DIR = DISCORD_DIR / "cogs"


class DiscordBotSettings(BaseServiceSettings):
    """Discord bot settings"""

    model_config = SettingsConfigDict(
        env_file=dev_env_files("discord"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Discord
    discord_bot_token: str = Field(..., description="Discord bot token")
    frontend_url: str = Field(
        default="http://localhost:3000",
        description="Public frontend URL used for static assets in Discord embeds",
    )

    # Server
    port: int = Field(default=8080, description="Health server port")

    # Presence
    discord_status: str = Field(default="online", description="Bot status")
    discord_activity_type: str = Field(
        default="playing",
        description="Activity type (playing/listening/watching/competing/streaming)",
    )
    discord_activity_name: str = Field(default="", description="Activity name")
    discord_activity_url: str = Field(
        default="", description="Streaming URL (twitch.tv only, required for streaming type)"
    )
    # Instagram (Social Preview) — instafix_host now lives on BaseServiceSettings
    instagram_session_id: str = Field(
        default="", description="Instagram session cookie for profile embeds"
    )

    # Threads (Social Preview — Scrapling sidecar for JS-rendered captions)
    scrapling_host: str = Field(
        default="",
        description="Scrapling sidecar host (Docker: scrapling:3001, local: localhost:3001). Empty = disabled.",
    )

    # Twitch (Social Preview — clip embeds)
    twitch_client_id: str = Field(default="", description="Twitch app Client ID (Helix API)")
    twitch_client_secret: str = Field(
        default="", description="Twitch app Client Secret (Helix API)"
    )

    # AI providers
    groq_api_key: str = Field(default="", description="Groq API key (free tier, no billing)")
    groq_model: str = Field(default="", description="Groq model; required when GROQ_API_KEY is set")
    gemini_api_key: str = Field(
        default="", description="Gemini AI Studio API key (free, no billing)"
    )
    gemini_model: str = Field(
        default="", description="Gemini model; required when GEMINI_API_KEY is set"
    )
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openrouter_model: str = Field(
        default="", description="OpenRouter model; required when OPENROUTER_API_KEY is set"
    )


@lru_cache
def get_settings() -> DiscordBotSettings:
    """Get cached settings instance"""
    return DiscordBotSettings()  # type: ignore[call-arg]


class BotConfig:
    """Discord presence configuration — backed by DiscordBotSettings."""

    @classmethod
    def get_status(cls) -> discord.Status:
        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }
        return status_map.get(get_settings().discord_status.lower(), discord.Status.online)

    @classmethod
    def get_activity(cls) -> discord.Activity | discord.Streaming | discord.CustomActivity | None:
        """Get bot activity from settings.

        Supports: playing, listening, watching, competing, streaming
        For streaming: discord_activity_url must be a valid Twitch URL
        """
        s = get_settings()
        if not s.discord_activity_name:
            return None

        activity_type_lower = s.discord_activity_type.lower()

        if activity_type_lower == "streaming":
            if not s.discord_activity_url:
                LOGGER.warning(
                    "Streaming activity requires DISCORD_ACTIVITY_URL to be set. "
                    "Falling back to 'playing' activity."
                )
                return discord.Activity(
                    type=discord.ActivityType.playing, name=s.discord_activity_name
                )

            if not _TWITCH_URL_RE.match(s.discord_activity_url):
                LOGGER.warning(
                    f"Streaming activity URL must be a valid Twitch channel URL "
                    f"(https://twitch.tv/<username>). "
                    f"Got: {s.discord_activity_url}. Falling back to 'playing' activity."
                )
                return discord.Activity(
                    type=discord.ActivityType.playing, name=s.discord_activity_name
                )

            return discord.Streaming(name=s.discord_activity_name, url=s.discord_activity_url)

        if activity_type_lower == "custom":
            return discord.CustomActivity(name=s.discord_activity_name)

        activity_map = {
            "playing": discord.ActivityType.playing,
            "listening": discord.ActivityType.listening,
            "watching": discord.ActivityType.watching,
            "competing": discord.ActivityType.competing,
        }
        activity_type = activity_map.get(activity_type_lower, discord.ActivityType.playing)
        return discord.Activity(type=activity_type, name=s.discord_activity_name)
